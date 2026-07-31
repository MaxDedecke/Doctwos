"""
parser/connectors/base.py
=========================
Abstrakte Basisklasse für alle Wissensquellen-Connectoren.

Architektur-Prinzip
-------------------
Jeder Connector (Confluence, Notion, Jira, ...) implementiert ausschließlich
fetch_documents() und liefert Document-Objekte. Chunking, Embedding und
Datenbank-Speicherung sind einmalig in dieser Basisklasse definiert.

Neuen Connector hinzufügen:
    1. Klasse erstellen, die BaseConnector erbt
    2. fetch_documents() als async generator implementieren
    3. In connectors/registry.py unter dem passenden source_type eintragen

Ablauf eines sync()-Aufrufs
----------------------------
    source.sync_status = "syncing"
    → ensure_model_pulled()           # Embedding-Modell bereitstellen
    → async for doc in fetch_documents():
          delete old chunks            # Delta-Sync: stale Daten entfernen
          chunk content
          embed each chunk
          store DocumentChunk
    → source.last_synced_at = sync_start_time
    → source.sync_status = "completed"
    → celery: compute_entity_links     # Verknüpfungen neu berechnen
"""

import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TypedDict

import redis
from celery import current_app as celery_app

from chunk_reindex import reindex_chunks_preserving_links
from code_parser import CodeParser
from core import config
from db import SessionLocal, REDIS_URL
from models.database import DocumentChunk, KnowledgeSource
from ollama_client import ensure_model_pulled, get_embedding

logger = logging.getLogger(__name__)

redis_client = redis.from_url(REDIS_URL)

# Verhindert einen parallelen Sync derselben Quelle (z. B. Celery-Beat-Scan und ein
# manueller "Jetzt synchronisieren"-Klick treffen sich): der bloße
# source.sync_status=="syncing"-Check in der DB war ein ungeschütztes
# Check-then-Set — zwei Worker-Prozesse (der Celery-Worker läuft ohne
# --concurrency-Limit, also standardmäßig mit einem Prozess pro CPU-Kern) können
# beide "nicht syncing" lesen, bevor einer von beiden committet, und denselben
# storage_key parallel löschen+neu einfügen → doppelte Chunks. Redis SET NX EX ist
# atomar und schließt das Rennen; Lease wird analog zu tasks/link_builder.py als
# Heartbeat pro verarbeitetem Dokument erneuert, damit ein legitim langer Download
# (große BIM-Modelle) die Sperre nicht verliert.
_SYNC_LOCK_LEASE_SECONDS = 3600


class Document(TypedDict):
    """
    Einheitliches Transfer-Format zwischen Connector und Basis-Klasse.

    Felder:
        title       Anzeige-Titel (Confluence-Seitentitel, Jira-Key + Summary, ...)
        content     Volltext-Inhalt, der in Chunks aufgeteilt und eingebettet wird
        url         Link zur Originalseite / zum Original-Ticket (für das Frontend)
        source_type "Confluence" | "Notion" | "Jira" (Anzeige-Label im Frontend)
        storage_key Wird als DocumentChunk.file_path gespeichert; muss pro Dokument
                    eindeutig sein, damit alte Chunks bei Delta-Sync gezielt gelöscht
                    werden können
        extra_meta  Beliebige Zusatz-Felder für metadata_json (page_id, issue_key, ...)
    """
    title: str
    content: str
    url: str | None
    source_type: str
    storage_key: str
    extra_meta: dict


class BaseConnector(ABC):
    """
    Basisklasse für alle Wissensquellen-Connectoren.

    Unterklassen überschreiben nur fetch_documents(). Der gesamte
    Embed+Store-Ablauf ist einmalig hier implementiert.

    Args:
        source_id: Primärschlüssel des KnowledgeSource-Eintrags in der DB
    """

    def __init__(self, source_id: int) -> None:
        self.source_id = source_id
        # DB-Session wird in sync() geöffnet und in finally geschlossen
        self.db = SessionLocal()
        self.source: KnowledgeSource | None = None
        self._sync_start_time: datetime | None = None
        self.has_changes = False

    # ── Logging ──────────────────────────────────────────────────────────────

    def _log(self, message: str) -> None:
        """Schreibt eine Zeile ins sync_log der KnowledgeSource und auf stdout."""
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        line = f"[{timestamp}] {message}\n"
        logger.info(message)
        if self.source:
            self.source.sync_log = (self.source.sync_log or "") + line
            self.db.commit()

    def _update_progress(self, current: int, total: int | None = None, message: str | None = None) -> None:
        """Aktualisiert den Fortschritt in der Datenbank."""
        if self.source:
            if total and total > 0:
                self.source.progress = min(100, int((current / total) * 100))
            if message:
                self.source.progress_message = message
            self.db.commit()

    # ── Hilfs-Methoden ────────────────────────────────────────────────────────

    def _parse_spaces(self) -> list[str]:
        """
        Liest source.spaces und normalisiert es zu einer Liste von Strings.
        Hintergrund: spaces wird als JSON-String oder als bereits geparste Liste
        gespeichert — dieser Helper vereinheitlicht beides.
        """
        spaces = self.source.spaces or ["ALL"]
        if isinstance(spaces, str):
            try:
                spaces = json.loads(spaces)
            except Exception:
                spaces = [spaces]
        if isinstance(spaces, dict):
            return spaces.get("ids", ["ALL"])
        return spaces

    # ── Embed + Store (gemeinsam für alle Connectoren) ────────────────────────

    async def _process_document(self, doc: Document) -> int:
        """
        Chunked, embeddet und speichert ein einzelnes Document in der Datenbank.

        Ersetzt bestehende Chunks für denselben storage_key (Delta-Sync), dabei
        bleiben EntityDocLinks auf unverändert gebliebene Passagen erhalten --
        siehe reindex_chunks_preserving_links für die Content-Fingerprint-Logik.

        Returns:
            Anzahl erfolgreich gespeicherter Chunks
        """
        lang = doc.get("extra_meta", {}).get("language", "text")
        parser = CodeParser(lang)
        chunks = parser.chunk_file(doc["content"], chunk_size=config.CHUNK_SIZE)

        def build_chunk(chunk, embedding):
            return DocumentChunk(
                project_id=self.source.project_id,
                source_id=self.source.id,
                file_path=doc["storage_key"],
                content=chunk["content"],
                start_line=chunk["start_line"],
                end_line=chunk["end_line"],
                embedding=embedding,
                metadata_json={
                    "url": doc["url"],
                    "title": doc["title"],
                    "source_type": doc["source_type"],
                    **doc["extra_meta"],
                }
            )

        async def embed_content(content):
            return await get_embedding(content, model=config.EMBED_MODEL)

        def on_embed_error(chunk, e):
            self._log(f"Embedding-Fehler für '{doc['title']}': {e}")

        count = await reindex_chunks_preserving_links(
            self.db,
            source_id=self.source.id,
            file_path=doc["storage_key"],
            chunks=chunks,
            build_chunk=build_chunk,
            embed_content=embed_content,
            on_embed_error=on_embed_error,
        )
        return count

    # ── Abstrakte Schnittstelle ───────────────────────────────────────────────

    @abstractmethod
    async def fetch_documents(self):
        """
        Async Generator: liefert alle zu indexierenden Dokumente aus der externen Quelle.

        Delta-Sync-Verantwortung liegt beim Connector: Dokumente, die sich seit
        self.source.last_synced_at nicht geändert haben, sollen NICHT geliefert
        werden. self.source ist zu diesem Zeitpunkt bereits gesetzt.

        Yields:
            Document
        """
        raise NotImplementedError

    # ── Öffentlicher Einstiegspunkt ──────────────────────────────────────────

    async def sync(self) -> None:
        """
        Orchestriert den vollständigen Sync-Ablauf für eine KnowledgeSource.
        Wird von der Celery-Task in tasks/sync.py aufgerufen.
        """
        lock_key = f"lock:sync_source:{self.source_id}"
        lock_owner = uuid.uuid4().hex
        if not redis_client.set(lock_key, lock_owner, nx=True, ex=_SYNC_LOCK_LEASE_SECONDS):
            logger.warning(f"[Connector] Sync für KnowledgeSource {self.source_id} läuft bereits (Lock aktiv), überspringe.")
            return

        try:
            self.source = self.db.query(KnowledgeSource).filter(
                KnowledgeSource.id == self.source_id
            ).first()
            if not self.source:
                logger.error(f"[Connector] KnowledgeSource {self.source_id} nicht gefunden.")
                return

            self._sync_start_time = datetime.now(timezone.utc)
            self.source.sync_status = "syncing"
            self.source.progress = 0
            self.source.progress_message = "Initialisiere..."
            self.source.last_error = None
            self.source.sync_log = ""
            self.db.commit()

            self._log(
                f"Starte Sync für '{self.source.name}' "
                f"(ID: {self.source_id}, Typ: {self.source.type})..."
            )
            self._log(f"Stelle sicher, dass Embedding-Modell '{config.EMBED_MODEL}' bereit ist...")
            await ensure_model_pulled(config.EMBED_MODEL)

            processed = 0
            total_chunks = 0

            async for doc in self.fetch_documents():
                # Heartbeat: Lease erneuern, solange sichtbar Fortschritt gemacht wird,
                # damit ein legitim langer Sync (viele/große BIM-Downloads) die Sperre
                # nicht mitten im Lauf verliert.
                redis_client.expire(lock_key, _SYNC_LOCK_LEASE_SECONDS)
                chunk_count = await self._process_document(doc)
                self.db.commit()
                total_chunks += chunk_count
                processed += 1
                self.has_changes = True
                self._log(f"'{doc['title']}' indexiert ({chunk_count} Chunks).")

            # Sync-Zeitstempel erst nach erfolgreichem Durchlauf setzen, damit
            # bei einem Abbruch der nächste Sync alle Dokumente erneut prüft
            self.source.last_synced_at = self._sync_start_time
            self.source.sync_status = "completed"
            self.source.progress = 100
            self.source.progress_message = "Synchronisierung abgeschlossen"
            self.db.commit()
            self._log(
                f"Sync abgeschlossen — {processed} Dokument(e), {total_chunks} Chunks gesamt."
            )

        except Exception as e:
            error_msg = str(e)
            self._log(f"Kritischer Fehler beim Sync: {error_msg}")
            if self.source:
                self.source.sync_status = "error"
                self.source.last_error = error_msg
                self.db.commit()
        finally:
            self.db.close()
            # Lock nur freigeben, wenn wir ihn noch besitzen (Schutz gegen den seltenen
            # Fall, dass die Lease während eines extrem langen Laufs abgelaufen und
            # zwischenzeitlich von einem neuen Sync übernommen wurde).
            current_owner = redis_client.get(lock_key)
            if current_owner == lock_owner.encode("utf-8"):
                redis_client.delete(lock_key)
