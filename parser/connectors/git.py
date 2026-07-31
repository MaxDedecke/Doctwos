"""
parser/connectors/git.py
=========================
Connector für Git-Repositories (AP-3, Plan §7) — monorepo-tauglich, resumable.

Ablauf:
    1. Bare-Mirror unter /repos/bare/<fingerprint>.git anlegen/aktualisieren
       (geteilt über alle Wissensquellen desselben Repos), Worktree unter
       /repos/wt/ks_<source_id>/ anlegen oder per reset --hard FETCH_HEAD
       aktualisieren (§7.1/7.2, parser/git_utils.py).
    2. Geänderte Dateien bestimmen: beim allerersten Sync per `git ls-files`
       (voller Baum), danach per `git diff --name-status` gegen den zuletzt
       gesehenen Commit (source.sync_cursor).
    3. Vor dem Einbetten: Blob-SHA gegen SourceScanFile.content_hash prüfen —
       unverändert seit dem letzten (ggf. abgebrochenen) Sync = überspringen.
       Das ist der günstigste Resume-Mechanismus (NF-004): git kennt den
       Content-Hash über den Blob-SHA bereits, kein erneutes Hashen nötig.
    4. Chunking + Embedding parallel (Semaphore), DB-Schreiben sequenziell.
       Nach jedem persistierten Dokument wird SourceScanFile im selben Commit
       aktualisiert — ein Abbruch mitten im Lauf lässt den nächsten Sync exakt
       dort fortsetzen.
"""

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

import redis

import git_utils
from connectors.base import BaseConnector, Document, _SYNC_LOCK_LEASE_SECONDS
from db import SessionLocal, REPOS_ROOT
from models.database import DocumentChunk, KnowledgeSource, SourceScanFile
from ollama_client import ensure_model_pulled, get_embeddings_batch, get_embedding
from code_parser import CodeParser
from chunk_reindex import reindex_chunks_preserving_links
from tasks.shared import get_authenticated_url
from core import config

logger = logging.getLogger(__name__)
redis_client = redis.from_url(config.REDIS_URL)

# F-016: grobe Dateiklassifikation fürs generische Chunking (CodeParser ist
# language-agnostisch, siehe code_parser.py — das Feld landet nur informativ
# in metadata_json). Die eigentliche COBOL-Strukturanalyse (parser/cobol/)
# hängt AP-4 an, hier geht es nur um den Ingestion-Layer.
_DEFAULT_EXTENSIONS: dict[str, set[str]] = {
    "cobol": {".cbl", ".cob", ".cobol"},
    "copybook": {".cpy", ".copy"},
    "jcl": {".jcl", ".proc", ".prc"},  # v1: nur Text-Index, keine Strukturanalyse (F-026)
}

MAX_READ_BYTES = 2 * 1024 * 1024

# Nur der Fetch/Worktree-Schritt läuft unter diesem Lock, nicht das komplette
# Einbetten — sonst blockiert ein langer Embed-Lauf jeden anderen Sync
# desselben Bare-Mirrors unnötig lange.
_GIT_FETCH_LOCK_SECONDS = 600


def _resolve_extension_config(spaces: dict) -> dict[str, set[str]]:
    """Konfigurierbar über DOCTUS_COBOL_EXTENSIONS (Env, Worker-weiter Default)
    und optional spaces.cobol_extensions (überschreibt pro Wissensquelle).
    Beide erwarten {"cobol": [...], "copybook": [...], "jcl": [...]}."""
    cfg = dict(_DEFAULT_EXTENSIONS)

    raw_env = os.environ.get("DOCTUS_COBOL_EXTENSIONS")
    if raw_env:
        try:
            cfg.update({k: set(v) for k, v in json.loads(raw_env).items()})
        except Exception:
            logger.warning("DOCTUS_COBOL_EXTENSIONS ist kein gültiges JSON, ignoriere.")

    override = spaces.get("cobol_extensions") if isinstance(spaces, dict) else None
    if override:
        cfg.update({k: set(v) for k, v in override.items()})

    return {k: {e.lower() for e in exts} for k, exts in cfg.items()}


def classify_extension(path: str, extensions: dict[str, set[str]]) -> str:
    ext = os.path.splitext(path)[1].lower()
    for lang, exts in extensions.items():
        if ext in exts:
            return lang
    return "text"


@asynccontextmanager
async def _git_fetch_lock(fingerprint: str, log=None):
    """Verhindert paralleles Fetch/Worktree-Setup auf demselben Bare-Mirror,
    wenn zwei Wissensquellen (verschiedene Branches) desselben Repos
    gleichzeitig synchronisieren. Anders als beim Sync-Lock ist Überspringen
    hier keine Option — der Fetch muss passieren — daher blockierendes Warten
    statt Verzicht."""
    lock_key = f"lock:git_fetch:{fingerprint}"
    owner = uuid.uuid4().hex
    waited = 0
    announced = False
    while not redis_client.set(lock_key, owner, nx=True, ex=_GIT_FETCH_LOCK_SECONDS):
        if not announced and log:
            log("Bare-Mirror wird gerade von einer anderen Wissensquelle aktualisiert, warte…")
            announced = True
        if waited >= _GIT_FETCH_LOCK_SECONDS:
            raise TimeoutError(f"Bare-Mirror-Lock für {fingerprint} nach {_GIT_FETCH_LOCK_SECONDS}s nicht frei geworden.")
        await asyncio.sleep(1)
        waited += 1
    try:
        yield
    finally:
        current = redis_client.get(lock_key)
        if current == owner.encode("utf-8"):
            redis_client.delete(lock_key)


class GitConnector(BaseConnector):
    """
    Connector für Git-Repositories. Bare-Mirror + Worktree statt Flat-Clone
    (F-019, monorepo-tauglich), resumable über SourceScanFile (NF-004).
    """

    def __init__(self, source_id: int) -> None:
        super().__init__(source_id)
        self._new_commit: str | None = None

    async def _embed_document(self, doc: Document, semaphore: asyncio.Semaphore):
        async with semaphore:
            lang = doc.get("extra_meta", {}).get("language", "text")
            parser = CodeParser(lang)
            chunks = await asyncio.to_thread(parser.chunk_file, doc["content"], chunk_size=config.CHUNK_SIZE)

            chunk_texts = [c["content"] for c in chunks]
            embeddings = []
            if chunk_texts:
                try:
                    embeddings = await get_embeddings_batch(chunk_texts, model=config.EMBED_MODEL)
                except Exception as e:
                    self._log(f"Embedding-Fehler für '{doc['title']}': {e}")

            for chunk, embedding in zip(chunks, embeddings):
                chunk["embedding"] = embedding

            return doc, chunks

    async def _save_document_chunks(self, doc: Document, chunks: list[dict]) -> int:
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

        count = await reindex_chunks_preserving_links(
            self.db,
            source_id=self.source.id,
            file_path=doc["storage_key"],
            chunks=chunks,
            build_chunk=build_chunk,
            embed_content=embed_content,
        )

        # NF-004: SourceScanFile wird im selben Commit wie die Chunks
        # aktualisiert — bricht der Sync danach ab, überspringt der Resume-Check
        # in fetch_documents() diese Datei beim nächsten Anlauf.
        path = doc["storage_key"]
        if doc["extra_meta"].get("deleted"):
            self.db.query(SourceScanFile).filter(
                SourceScanFile.source_id == self.source_id,
                SourceScanFile.file_path == path,
            ).delete()
        else:
            content_hash = doc["extra_meta"]["content_hash"]
            existing = self.db.query(SourceScanFile).filter(
                SourceScanFile.source_id == self.source_id,
                SourceScanFile.file_path == path,
            ).first()
            if existing:
                existing.content_hash = content_hash
            else:
                self.db.add(SourceScanFile(
                    source_id=self.source_id, file_path=path, content_hash=content_hash,
                ))

        self.db.commit()
        return count

    async def fetch_documents(self) -> AsyncIterator[Document]:
        spaces = self.source.spaces or {}
        if isinstance(spaces, str):
            try:
                spaces = json.loads(spaces)
            except Exception:
                spaces = {}

        branch = self.source.branch or spaces.get("branch") or "main"
        sparse_paths = spaces.get("sparse_paths")
        extensions = _resolve_extension_config(spaces)

        if not self.source.repo_fingerprint:
            self.source.repo_fingerprint = git_utils.compute_repo_fingerprint(self.source.url)
            self.db.commit()
        fingerprint = self.source.repo_fingerprint

        auth_url = get_authenticated_url(self.source.url, self.source.username, self.source.token)
        bare = git_utils.bare_path(REPOS_ROOT, fingerprint)
        wt = git_utils.worktree_path(REPOS_ROOT, self.source_id)

        async with _git_fetch_lock(fingerprint, log=self._log):
            await asyncio.to_thread(git_utils.ensure_bare_mirror, REPOS_ROOT, fingerprint, auth_url, self._log)
            await asyncio.to_thread(git_utils.fetch_branch, bare, branch, self._log)

            worktree_is_new = not os.path.isdir(wt)
            if worktree_is_new:
                await asyncio.to_thread(git_utils.ensure_worktree, bare, wt, branch, sparse_paths, self._log)
            else:
                await asyncio.to_thread(git_utils.reset_worktree_to_branch, wt, branch)

        new_commit = await asyncio.to_thread(git_utils.current_commit, wt)
        self._new_commit = new_commit
        cursor = self.source.sync_cursor or {}
        old_commit = cursor.get("last_commit")

        deleted_paths: list[str] = []
        additions: list[str] = []
        current_hashes: dict[str, str] = {}

        if worktree_is_new or not old_commit:
            self._log("Vollständige Ersteinlesung des Worktrees…")
            current_hashes = await asyncio.to_thread(git_utils.list_tracked_files, wt)
            additions = list(current_hashes.keys())
            existing_hashes = {
                r.file_path: r.content_hash
                for r in self.db.query(SourceScanFile).filter(SourceScanFile.source_id == self.source_id).all()
            }
            deleted_paths = sorted(set(existing_hashes.keys()) - set(current_hashes.keys()))
        else:
            if old_commit == new_commit:
                self._log("Repository ist bereits auf dem neuesten Stand.")
                return
            changes = await asyncio.to_thread(git_utils.diff_name_status, wt, old_commit, new_commit)
            for status, path in changes:
                if status == "D":
                    deleted_paths.append(path)
                else:
                    additions.append(path)
            tracked = await asyncio.to_thread(git_utils.list_tracked_files, wt)
            current_hashes = {path: tracked[path] for path in additions if path in tracked}
            existing_hashes = {
                r.file_path: r.content_hash
                for r in self.db.query(SourceScanFile).filter(
                    SourceScanFile.source_id == self.source_id,
                    SourceScanFile.file_path.in_(additions),
                ).all()
            } if additions else {}

        # Resumability (NF-004): unverändert seit dem letzten (ggf.
        # abgebrochenen) Sync -> überspringen, billigster Resume-Mechanismus.
        to_process: list[tuple[str, str]] = []
        for path in additions:
            blob_sha = current_hashes.get(path)
            if blob_sha is None:
                continue  # nicht (mehr) materialisiert, z.B. außerhalb des Sparse-Checkout-Kegels
            content_hash = git_utils.blob_content_hash(blob_sha)
            if existing_hashes.get(path) == content_hash:
                continue
            to_process.append((path, content_hash))

        total = len(to_process) + len(deleted_paths)
        self.source.total_files = total
        self.db.commit()

        processed = 0
        for path in deleted_paths:
            processed += 1
            self.source.parsed_files = processed
            self._update_progress(processed, total, f"{processed} von {total} Dateien verarbeitet")
            yield Document(
                title=os.path.basename(path),
                content="",
                url=None,
                source_type="Git",
                storage_key=path,
                extra_meta={"language": "text", "branch": branch, "deleted": True},
            )

        for path, content_hash in to_process:
            full_path = os.path.join(wt, path)
            try:
                file_size = os.path.getsize(full_path)
            except OSError:
                continue
            if file_size > MAX_READ_BYTES:
                self._log(f"[SKIP] '{path}' überschreitet {MAX_READ_BYTES // (1024 * 1024)} MB.")
                continue
            try:
                with open(full_path, "r", errors="ignore") as f:
                    content = f.read(MAX_READ_BYTES)
            except Exception as e:
                self._log(f"Fehler beim Lesen von '{path}': {e}")
                continue

            lang = classify_extension(path, extensions)
            processed += 1
            self.source.parsed_files = processed
            self._update_progress(processed, total, f"{processed} von {total} Dateien verarbeitet")
            yield Document(
                title=os.path.basename(path),
                content=content,
                url=None,
                source_type="Git",
                storage_key=path,
                extra_meta={"language": lang, "branch": branch, "content_hash": content_hash},
            )

    async def sync(self) -> None:
        """
        Orchestriert Chunking und Embedding parallel (Semaphore), DB-Schreiben
        sequenziell. Der Git-Fetch/Worktree-Schritt selbst läuft unter einem
        eigenen, engeren Lock (siehe _git_fetch_lock) innerhalb von
        fetch_documents().
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
            self.source.parse_started_at = self._sync_start_time
            self.source.progress = 0
            self.source.progress_message = "Initialisiere…"
            self.source.last_error = None
            self.source.sync_log = ""
            self.db.commit()

            self._log(
                f"Starte Sync für '{self.source.name}' "
                f"(ID: {self.source_id}, Typ: {self.source.type})…"
            )
            self._log(f"Stelle sicher, dass Embedding-Modell '{config.EMBED_MODEL}' bereit ist…")
            await ensure_model_pulled(config.EMBED_MODEL)

            semaphore = asyncio.Semaphore(config.EMBED_CONCURRENCY)
            pending_tasks = set()

            async def doc_producer():
                async for doc in self.fetch_documents():
                    task = asyncio.create_task(self._embed_document(doc, semaphore))
                    yield task

            total_chunks = 0
            processed = 0

            async for task in doc_producer():
                pending_tasks.add(task)
                redis_client.expire(lock_key, _SYNC_LOCK_LEASE_SECONDS)

                if len(pending_tasks) >= 50:
                    done, pending_tasks = await asyncio.wait(pending_tasks, return_when=asyncio.FIRST_COMPLETED)
                    for t in done:
                        doc, chunks = await t
                        chunk_count = await self._save_document_chunks(doc, chunks)
                        total_chunks += chunk_count
                        processed += 1
                        self.has_changes = True
                        self._log(f"'{doc['title']}' indexiert ({chunk_count} Chunks).")

            if pending_tasks:
                done, _ = await asyncio.wait(pending_tasks)
                for t in done:
                    doc, chunks = await t
                    chunk_count = await self._save_document_chunks(doc, chunks)
                    total_chunks += chunk_count
                    processed += 1
                    self.has_changes = True
                    self._log(f"'{doc['title']}' indexiert ({chunk_count} Chunks).")

            # sync_cursor erst nach erfolgreichem Durchlauf vorrücken, damit ein
            # Abbruch den nächsten Sync exakt denselben Diff neu berechnen lässt
            # (der Resume-Check in fetch_documents() überspringt dann alles
            # bereits persistierte).
            if self._new_commit:
                self.source.sync_cursor = {"last_commit": self._new_commit}

            self.source.last_synced_at = self._sync_start_time
            self.source.sync_status = "completed"
            self.source.parse_finished_at = datetime.now(timezone.utc)
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
            current_owner = redis_client.get(lock_key)
            if current_owner == lock_owner.encode("utf-8"):
                redis_client.delete(lock_key)
