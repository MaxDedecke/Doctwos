import os
import shutil
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
import redis

from connectors.base import BaseConnector, Document, _SYNC_LOCK_LEASE_SECONDS
from db import SessionLocal, REPOS_ROOT
from models.database import DocumentChunk, KnowledgeSource
from ollama_client import ensure_model_pulled, get_embeddings_batch, get_embedding
from utils import clone_repository, clone_repository_sparse, list_files_iter
from code_parser import CodeParser
from chunk_reindex import reindex_chunks_preserving_links
from tasks.shared import get_authenticated_url
from core import config

logger = logging.getLogger(__name__)
redis_client = redis.from_url(config.REDIS_URL if hasattr(config, "REDIS_URL") else "redis://redis:6379/0")

EXT_LANG_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".h": "cpp",
    ".hpp": "cpp",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".cs": "c_sharp",
    ".html": "html",
    ".css": "css",
}

MAX_READ_BYTES = 2 * 1024 * 1024


class GitConnector(BaseConnector):
    """
    Connector for Git repositories.
    Clones or pulls repositories, parses code files according to their extension,
    and indexes them with full parallel embedding support.
    """

    async def _embed_document(self, doc: Document, semaphore: asyncio.Semaphore):
        async with semaphore:
            lang = doc.get("extra_meta", {}).get("language", "text")
            parser = CodeParser(lang)
            # Run chunking in a thread pool to avoid blocking the event loop
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
        self.db.commit()
        return count

    async def fetch_documents(self):
        """
        Async Generator that clones/pulls the git repository and yields Documents.
        This follows the git delta sync or clean clone logic.
        """
        spaces = self.source.spaces or {}
        if isinstance(spaces, str):
            try:
                spaces = json.loads(spaces)
            except Exception:
                spaces = {}

        branch = spaces.get("branch", "main")
        sparse_paths = spaces.get("sparse_paths")
        last_commit_hash = spaces.get("last_commit_hash")

        repo_path = os.path.join(REPOS_ROOT, f"ks_{self.source_id}")
        auth_url = get_authenticated_url(self.source.url, self.source.username, self.source.token)

        is_update = False
        changed_files = []

        if os.path.exists(repo_path) and last_commit_hash:
            try:
                import git
                repo_git = git.Repo(repo_path)
                
                self._log("Neue Änderungen werden abgerufen…")
                origin = repo_git.remotes.origin
                origin.fetch()
                
                repo_git.git.checkout(branch)
                origin.pull()
                
                new_commit = repo_git.head.commit.hexsha
                if new_commit == last_commit_hash:
                    self._log("Repository ist bereits auf dem neuesten Stand.")
                    return

                diff = repo_git.commit(last_commit_hash).diff(repo_git.commit("HEAD"))
                
                DELTA_SYNC_MAX_FILES = 50_000
                if len(diff) > DELTA_SYNC_MAX_FILES:
                    self._log(f"Diff hat {len(diff)} Dateien — Full Clone statt Delta Sync.")
                    is_update = False
                else:
                    for d in diff:
                        change_type = d.change_type
                        if change_type == 'R':
                            changed_files.append(('D', d.a_path))
                            changed_files.append(('A', d.b_path))
                        else:
                            changed_files.append((change_type, d.b_path or d.a_path))
                    is_update = True
                    self._log(f"Delta Sync: {len(changed_files)} geänderte Dateien erkannt.")
            except Exception as e:
                self._log(f"Git pull fehlgeschlagen (Full Clone stattdessen): {e}")
                is_update = False

        if not is_update:
            if os.path.exists(repo_path):
                shutil.rmtree(repo_path)
            
            self._log("Repository wird geklont…")
            if sparse_paths:
                clone_repository_sparse(auth_url, repo_path, branch, sparse_paths)
            else:
                clone_repository(auth_url, repo_path, branch)

            self._log("Alte Indexdaten werden bereinigt…")
            self.db.query(DocumentChunk).filter(DocumentChunk.source_id == self.source_id).delete()
            self.db.commit()

            for f in list_files_iter(repo_path):
                rel_path = os.path.relpath(f, repo_path)
                changed_files.append(('A', rel_path))

        total_files = len(changed_files) if changed_files else 1
        
        # Save total files info on source
        if hasattr(self.source, "total_files"):
            self.source.total_files = total_files
            self.db.commit()

        processed_count = 0
        deletions = [f for f in changed_files if f[0] == 'D']
        additions_modifications = [f for f in changed_files if f[0] in ['A', 'M']]

        # Handle deletions
        for status, rel_path in deletions:
            yield Document(
                title=os.path.basename(rel_path),
                content="",
                url=None,
                source_type="Git",
                storage_key=rel_path,
                extra_meta={"language": "text"}
            )
            processed_count += 1
            if hasattr(self.source, "parsed_files"):
                self.source.parsed_files = processed_count
                self.db.commit()
            self._update_progress(processed_count, total_files, f"{processed_count} von {total_files} Dateien verarbeitet")

        # Handle additions/modifications
        for status, rel_path in additions_modifications:
            file_path = os.path.join(repo_path, rel_path)
            try:
                file_size = os.path.getsize(file_path)
            except OSError:
                continue

            if file_size > MAX_READ_BYTES:
                continue

            try:
                with open(file_path, "r", errors="ignore") as f:
                    content = f.read(MAX_READ_BYTES)
            except Exception as e:
                self._log(f"Fehler beim Lesen der Datei {rel_path}: {e}")
                continue

            ext = os.path.splitext(file_path)[1].lower()
            lang = EXT_LANG_MAP.get(ext, "text")

            yield Document(
                title=os.path.basename(rel_path),
                content=content,
                url=None,
                source_type="Git",
                storage_key=rel_path,
                extra_meta={"language": lang}
            )
            
            processed_count += 1
            if hasattr(self.source, "parsed_files"):
                self.source.parsed_files = processed_count
                self.db.commit()
            self._update_progress(processed_count, total_files, f"{processed_count} von {total_files} Dateien verarbeitet")

        # Update commit hash
        try:
            import git
            repo_git = git.Repo(repo_path)
            new_commit = repo_git.head.commit.hexsha
            spaces["last_commit_hash"] = new_commit
            self.source.spaces = spaces
            self.db.commit()
        except Exception as e:
            self._log(f"Fehler beim Speichern des letzten Commit-Hashs: {e}")

    async def sync(self) -> None:
        """
        Orchestrate sync using parallel chunking and embedding,
        but sequential database commits.
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
            if hasattr(self.source, "parse_started_at"):
                self.source.parse_started_at = self._sync_start_time
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

            semaphore = asyncio.Semaphore(20)
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

            self.source.last_synced_at = self._sync_start_time
            self.source.sync_status = "completed"
            if hasattr(self.source, "parse_finished_at"):
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
