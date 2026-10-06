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
    → link_builder_dirty_items erfasst Änderungen (Link-Build erfordert expliziten Nutzerauftrag, O-315)
"""

import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import NotRequired, TypedDict

import redis

from chunk_reindex import reindex_chunks_preserving_links
from connectors.tls import resolve_verify
from code_parser import CodeParser
from core import config
from db import SessionLocal, REDIS_URL
from models.database import DocumentChunk, KnowledgeSource
from insight_review import mark_source_insights_outdated
from ollama_client import ensure_model_pulled, get_embedding, get_embeddings_batch

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
        line_sections
                    O-082/O-083: optional, 1:1 mit den Zeilen von `content`
                    (Index i beschreibt die für content-Zeile i+1 zuletzt
                    gültige Überschrift). Nur vom Confluence-Connector
                    befüllt, der als einziger strukturierte Section-Grenzen
                    aus der Quelle kennt. Dient zwei Zwecken in
                    _process_document(): (1) jedem Chunk nach dem Chunking
                    seine Section als metadata_json beizugeben (analog zu
                    meta["section"] bei COBOL), (2) über
                    _section_boundaries() bevorzugte Chunk-Schnittgrenzen an
                    CodeParser.chunk_file() zu übergeben, statt ausschließlich
                    nach Zeichenzahl zu schneiden.
    """

    title: str
    content: str
    url: str | None
    source_type: str
    storage_key: str
    extra_meta: dict
    line_sections: NotRequired[list[str | None]]


def _section_boundaries(line_sections: list[str | None]) -> frozenset[int]:
    """O-083: 1-basierte Zeilennummern, an denen line_sections gegenüber der
    Vorzeile wechselt -- also die jeweils erste Zeile einer neuen Section
    (typischerweise die Überschriftenzeile selbst). Wird
    CodeParser.chunk_file() als bevorzugte, aber nicht harte Schnittgrenze
    übergeben: chunk_size bleibt die Obergrenze, ein neuer Chunk beginnt aber
    lieber hier als erst beim Erreichen der Zeichenzahl-Schwelle.
    """
    return frozenset(
        i + 1 for i in range(1, len(line_sections)) if line_sections[i] != line_sections[i - 1]
    )


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
        self.embedding_model = config.EMBED_MODEL
        self._sync_start_time: datetime | None = None
        self.has_changes = False
        # Dokumente, deren Chunks nicht vollständig eingebettet werden konnten (Schlüssel -> Chunk-Anzahl).
        # Sie werden nicht als erledigt gewertet, damit der nächste Lauf sie erneut versucht.
        self._embed_failures: dict[str, int] = {}

    # ── Logging ──────────────────────────────────────────────────────────────

    def _log(self, message: str) -> None:
        """Schreibt eine Zeile ins sync_log der KnowledgeSource und auf stdout."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}\n"
        logger.info(message)
        if self.source:
            self.source.sync_log = (self.source.sync_log or "") + line
            self.db.commit()

    def _update_progress(
        self, current: int, total: int | None = None, message: str | None = None
    ) -> None:
        """Aktualisiert den Fortschritt in der Datenbank."""
        if self.source:
            if total and total > 0:
                self.source.progress = min(100, int((current / total) * 100))
            if message:
                self.source.progress_message = message
            self.db.commit()

    # ── Hilfs-Methoden ────────────────────────────────────────────────────────

    def _spaces_config(self) -> dict:
        """Die als Objekt gespeicherte Quell-Konfiguration (``spaces``), sonst ein leeres Dict.

        Neben den Space-/Projekt-IDs trägt sie Verbindungsoptionen wie ``verify_ssl``/``ca_bundle``.
        """
        spaces = self.source.spaces if self.source else None
        if isinstance(spaces, str):
            try:
                spaces = json.loads(spaces)
            except Exception:
                spaces = None
        return spaces if isinstance(spaces, dict) else {}

    def _http_verify(self):
        """TLS-Prüfung für HTTP-Clients dieser Quelle (siehe connectors/tls.py)."""
        return resolve_verify(self._spaces_config())

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

        # O-083: line_sections (nur Confluence) liefert nebenbei auch die
        # bevorzugten Chunk-Schnittgrenzen -- ein neuer Chunk beginnt lieber an
        # einer erkannten Section-Überschrift als ausschließlich an der
        # Zeichenzahl-Schwelle. chunk_size bleibt die harte Obergrenze.
        line_sections = doc.get("line_sections")
        boundary_lines = _section_boundaries(line_sections) if line_sections else None
        chunks = parser.chunk_file(
            doc["content"], chunk_size=config.CHUNK_SIZE, boundary_lines=boundary_lines
        )

        # O-082: reine Metadaten-Anreicherung. line_sections ist 1:1 mit den
        # content-Zeilen indiziert, chunk["start_line"] ist 1-basiert.
        if line_sections:
            for chunk in chunks:
                idx = chunk["start_line"] - 1
                if 0 <= idx < len(line_sections) and line_sections[idx]:
                    chunk["meta"] = {"section": line_sections[idx]}

        def build_chunk(chunk, embedding):
            return DocumentChunk(
                project_id=self.source.project_id,
                source_id=self.source.id,
                file_path=doc["storage_key"],
                content=chunk["content"],
                start_line=chunk["start_line"],
                end_line=chunk["end_line"],
                embedding=embedding,
                embedding_model=self.embedding_model,
                metadata_json={
                    **doc["extra_meta"],
                    "url": doc["url"],
                    "title": doc["title"],
                    "source_type": doc["source_type"],
                    "embedding_model": self.embedding_model,
                    **(chunk.get("meta") or {}),
                },
            )

        async def embed_content(content):
            return await get_embedding(content, model=self.embedding_model)

        failures = 0

        def on_embed_error(chunk, e):
            nonlocal failures
            failures += 1
            # str(e) ist bei httpx.TimeoutException & Co. oft leer -- der
            # Exception-Typname macht die Meldung erst brauchbar.
            self._log(f"Embedding-Fehler für '{doc['title']}': {type(e).__name__}: {e}")

        # Alle Chunks eines Dokuments gebündelt einbetten (ein Aufruf je Batch statt je Chunk). Schlägt das fehl,
        # versucht reindex_chunks_preserving_links es unten einzeln und meldet jeden fehlgeschlagenen Chunk.
        if chunks:
            try:
                vectors = await get_embeddings_batch(
                    [chunk["content"] for chunk in chunks], model=self.embedding_model
                )
                if len(vectors) == len(chunks) and all(vectors):
                    for chunk, vector in zip(chunks, vectors):
                        chunk["embedding"] = vector
            except Exception as exc:
                logger.info(f"Gebündeltes Embedding für '{doc['title']}' fehlgeschlagen, wechsle auf Einzelaufrufe: {exc}")

        count = await reindex_chunks_preserving_links(
            self.db,
            source_id=self.source.id,
            file_path=doc["storage_key"],
            chunks=chunks,
            build_chunk=build_chunk,
            embed_content=embed_content,
            on_embed_error=on_embed_error,
        )
        if failures:
            # Alles oder nichts je Dokument: Ein Dokument mit fehlenden Chunks würde sonst von der
            # zeitbasierten Änderungserkennung als erledigt gelten und nie vervollständigt.
            self._embed_failures[doc["storage_key"]] = failures
            self.db.query(DocumentChunk).filter(
                DocumentChunk.source_id == self.source.id,
                DocumentChunk.file_path == doc["storage_key"],
            ).delete(synchronize_session=False)
            self.db.commit()
            return 0
        return count

    # ── Aufräumen ─────────────────────────────────────────────────────────────

    # Schutz vor einer leeren oder abgeschnittenen Antwort der Quelle ohne Fehlermeldung: Würde ein
    # großer Teil des Index auf einmal verschwinden, wird nichts gelöscht und stattdessen gewarnt.
    _ORPHAN_MAX_SHARE = 0.5
    _ORPHAN_MIN_COUNT = 20

    def _remove_orphans(self, seen_keys: set[str]) -> int:
        """Entfernt Chunks dieser Quelle, deren Dokument in der Quelle nicht mehr vorkommt.

        Nur nach einem vollständig durchlaufenen Crawl aufrufen. Läuft nach ``sync()`` (die dortige
        Session ist dann geschlossen) und nutzt deshalb eine eigene.
        """
        db = SessionLocal()
        try:
            known = {
                key
                for (key,) in db.query(DocumentChunk.file_path)
                .filter(DocumentChunk.source_id == self.source_id)
                .distinct()
            }
            stale = known - seen_keys
            if not stale:
                return 0
            if not seen_keys or (
                len(stale) >= self._ORPHAN_MIN_COUNT and len(stale) > len(known) * self._ORPHAN_MAX_SHARE
            ):
                self._append_log(
                    db,
                    f"[WARNUNG] {len(stale)} von {len(known)} indizierten Dokumenten kamen im Crawl nicht mehr vor. "
                    "Aus Sicherheit wird nichts gelöscht; prüfe Zugriffsrechte und Quelle.",
                )
                db.commit()
                return 0
            stale_list = sorted(stale)
            for offset in range(0, len(stale_list), 500):
                db.query(DocumentChunk).filter(
                    DocumentChunk.source_id == self.source_id,
                    DocumentChunk.file_path.in_(stale_list[offset : offset + 500]),
                ).delete(synchronize_session=False)
            self._append_log(db, f"{len(stale)} Dokument(e) nicht mehr in der Quelle — aus dem Index entfernt.")
            db.commit()
            return len(stale)
        except Exception as exc:
            db.rollback()
            logger.error(f"[Connector] Aufräumen für Quelle {self.source_id} fehlgeschlagen: {exc}")
            return 0
        finally:
            db.close()

    def _append_log(self, db, message: str) -> None:
        source = db.query(KnowledgeSource).filter(KnowledgeSource.id == self.source_id).first()
        if source is not None:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            source.sync_log = (source.sync_log or "") + f"[{timestamp}] {message}\n"

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

    async def sync(self, force_reindex: bool = False) -> None:
        """
        Orchestriert den vollständigen Sync-Ablauf für eine KnowledgeSource.
        Wird von der Celery-Task in tasks/sync.py aufgerufen.
        """
        lock_key = f"lock:sync_source:{self.source_id}"
        lock_owner = uuid.uuid4().hex
        if not redis_client.set(lock_key, lock_owner, nx=True, ex=_SYNC_LOCK_LEASE_SECONDS):
            logger.warning(
                f"[Connector] Sync für KnowledgeSource {self.source_id} läuft bereits (Lock aktiv), überspringe."
            )
            return

        try:
            self.source = (
                self.db.query(KnowledgeSource).filter(KnowledgeSource.id == self.source_id).first()
            )
            if not self.source:
                logger.error(f"[Connector] KnowledgeSource {self.source_id} nicht gefunden.")
                return
            had_previous_sync = self.source.last_synced_at is not None
            self.embedding_model = self.source.embedding_model or config.EMBED_MODEL

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
            self._log(f"Stelle sicher, dass Embedding-Modell '{self.embedding_model}' bereit ist...")
            await ensure_model_pulled(self.embedding_model)

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

            if self._embed_failures:
                # Zeitstempel bleibt stehen: der nächste Lauf prüft diese Dokumente erneut.
                total_failed = sum(self._embed_failures.values())
                self.source.sync_status = "error"
                self.source.last_error = (
                    f"{total_failed} Chunk(s) in {len(self._embed_failures)} Dokument(en) konnten nicht eingebettet "
                    "werden (Embedding-Dienst prüfen). Betroffene Dokumente fehlen im Index; der nächste Sync "
                    "versucht sie erneut."
                )
                self.source.progress_message = "Mit Fehlern abgeschlossen"
            else:
                # Sync-Zeitstempel erst nach erfolgreichem Durchlauf setzen, damit
                # bei einem Abbruch der nächste Sync alle Dokumente erneut prüft
                self.source.last_synced_at = self._sync_start_time
                self.source.sync_status = "completed"
                self.source.progress_message = "Synchronisierung abgeschlossen"
            self.source.progress = 100
            if self.has_changes and had_previous_sync:
                escalated = mark_source_insights_outdated(self.db, self.source)
                if escalated:
                    self._log(f"{escalated} Erkenntnis(se) wegen Quellenänderung zur Prüfung markiert.")
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
