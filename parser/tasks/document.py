import logging
import os
from chunk_reindex import reindex_chunks_preserving_links
from connectors.folder import extract_docx_text, extract_pdf_pages
from connectors.textio import read_text_file
from core import config
from db import SessionLocal
from models.database import KnowledgeSource, DocumentChunk
from insight_review import mark_source_insights_outdated
from code_parser import CodeParser
from doc_structure import boundary_lines, markdown_outline, section_path
from ollama_client import get_embedding, ensure_model_pulled

logger = logging.getLogger(__name__)

# Hochgeladene Dokumente werden feiner geteilt als Code (1000): Ein Chunk soll etwa einen
# Absatz bis kleinen Abschnitt umfassen, damit ein Code-Doku-Link auf eine konkrete Stelle zeigt.
UPLOAD_CHUNK_SIZE = 600
UPLOAD_CHUNK_OVERLAP = 100


async def process_local_document_async(source_id: int, file_path: str):
    """
    Parses and indexes a locally uploaded file (PDF, Word, or plain text).

    1. Extracts text content depending on the file format (PDF parsing via the
       shared `connectors.folder.extract_pdf_pages` incl. OCR fallback for
       image-only PDFs, Word parsing with python-docx, or default raw text
       reading).
    2. Removes invalid characters (null bytes).
    3. Triggers embedding model pulling in Ollama.
    4. Chunks the document content using CodeParser.
    5. Clears previous chunks for this specific knowledge source.
    6. Generates vector embeddings for each chunk and saves them.
    """
    db = SessionLocal()
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
    if not source:
        logger.warning(f"Local document source {source_id} not found.")
        return

    if source.sync_status == "cancelled":
        logger.info(f"Local document source {source_id} was cancelled before processing.")
        db.close()
        return

    if source.sync_status == "syncing":
        logger.info(f"Verarbeitung für Quelle {source_id} läuft bereits, überspringe.")
        return

    embedding_model = source.embedding_model or config.EMBED_MODEL

    from datetime import datetime, timezone

    def log_event(message: str):
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{timestamp}] {message}\n"
        logger.info(message)
        source.sync_log = (source.sync_log or "") + full_msg
        db.commit()

    try:
        source.sync_status = "syncing"
        source.last_error = None
        source.sync_log = ""
        db.commit()

        log_event(f"Starte Verarbeitung der lokalen Datei '{file_path}' (ID: {source_id})...")

        # 1. Read and extract content depending on file type.
        # `pages` holds (page_number, text) tuples -- page_number is the 1-based
        # PDF page for formats that have one, None otherwise. Chunking per page
        # (instead of joining all pages into one blob first) keeps start_line/
        # end_line meaningful relative to an actual page, and lets us tag each
        # chunk with the page it came from -- needed to answer "was steht auf
        # Seite X" questions, which is otherwise structurally impossible once
        # pages are flattened into a single string.
        ext = os.path.splitext(file_path)[1].lower()
        pages = []

        if ext == ".pdf":
            try:
                log_event("Lese PDF-Dokument ein...")
                pages = [(page_no, text) for page_no, text in extract_pdf_pages(file_path) if text]
            except Exception as e:
                log_event(f"Fehler beim Lesen der PDF-Datei, versuche Plaintext-Fallback: {e}")
                try:
                    fallback = read_text_file(file_path)
                    if fallback:
                        pages.append((None, fallback))
                except Exception:
                    pass
        elif ext in [".docx", ".doc"]:
            try:
                log_event("Lese Word-Dokument (.docx) ein...")
                pages.append((None, extract_docx_text(file_path)))
            except Exception as e:
                log_event(f"Fehler beim Lesen des Word-Dokuments: {e}")
        else:
            try:
                log_event("Lese Textdatei ein...")
                pages.append((None, read_text_file(file_path)))
            except Exception as e:
                log_event(f"Fehler beim Lesen der Datei: {e}")

        # Clean null bytes
        pages = [(page_no, text.replace("\x00", "")) for page_no, text in pages]
        total_chars = sum(len(text) for _, text in pages)
        if not any(text.strip() for _, text in pages):
            log_event(f"Kein Textinhalt aus {file_path} extrahiert. Abort.")
            raise Exception("Kein Textinhalt extrahiert.")

        log_event(f"{total_chars} Zeichen Text erfolgreich extrahiert ({len(pages)} Seite(n)).")

        # 2. Ensure embedding model is pulled
        log_event(
            f"Stelle sicher, dass das Einbettungs-Modell '{embedding_model}' bereit ist..."
        )
        await ensure_model_pulled(embedding_model)

        # 3. Chunk and embed content, page by page so a chunk never blends text
        # from two different PDF pages together.
        lang = "markdown" if ext == ".md" else "text"
        parser = CodeParser(lang)
        chunks = []
        for page_no, text in pages:
            # Markdown: Überschriften sind Chunk-Grenzen und liefern den Abschnittspfad.
            outline = markdown_outline(text) if ext == ".md" else []
            for chunk in parser.chunk_file(
                text,
                chunk_size=UPLOAD_CHUNK_SIZE,
                overlap_size=UPLOAD_CHUNK_OVERLAP,
                boundary_lines=boundary_lines(outline) or None,
            ):
                chunk["page"] = page_no
                chunk["section"] = section_path(outline, chunk["start_line"])
                chunks.append(chunk)
        log_event(f"Datei in {len(chunks)} Chunks aufgeteilt. Starte Einbettung...")

        def build_chunk(chunk, embedding):
            return DocumentChunk(
                project_id=source.project_id,
                source_id=source.id,
                file_path=source.name,
                content=chunk["content"],
                start_line=chunk["start_line"],
                end_line=chunk["end_line"],
                embedding=embedding,
                embedding_model=embedding_model,
                metadata_json={
                    "language": lang,
                    "title": source.name,
                    "source_type": "Local",
                    "page": chunk.get("page"),
                    "section": chunk.get("section"),
                    "embedding_model": embedding_model,
                },
            )

        async def embed_content(content):
            return await get_embedding(content, model=embedding_model)

        def on_embed_error(chunk, e):
            # Kein stilles Überspringen: Sonst endete eine Quelle mit 0 oder zu wenigen Chunks als
            # "completed" (z.B. bei nicht erreichbarem Embedding-Dienst). Die Ausnahme bricht den
            # Austausch ab, bevor die bisherigen Chunks gelöscht werden; der äußere Handler
            # setzt den Fehlerstatus.
            raise RuntimeError(
                f"Embedding fehlgeschlagen ({type(e).__name__}: {e}); "
                f"die Datei wurde nicht indiziert."
            ) from e

        embedded_chunks_count = await reindex_chunks_preserving_links(
            db,
            source_id=source_id,
            file_path=source.name,
            chunks=chunks,
            build_chunk=build_chunk,
            embed_content=embed_content,
            on_embed_error=on_embed_error,
        )

        if not chunks or embedded_chunks_count != len(chunks):
            raise RuntimeError(
                f"Nur {embedded_chunks_count} von {len(chunks)} Chunks wurden indiziert."
            )
        db.commit()
        had_previous_sync = source.last_synced_at is not None
        source.sync_status = "completed"
        source.last_synced_at = datetime.now(timezone.utc)
        if had_previous_sync:
            mark_source_insights_outdated(db, source)
        db.commit()
        log_event(
            f"Datei '{file_path}' erfolgreich indiziert ({embedded_chunks_count} Vektor-Chuncks erzeugt)."
        )

    except Exception as e:
        # Halb geschriebene Chunks verwerfen, bevor der Fehlerstatus committet wird.
        db.rollback()
        error_msg = str(e)
        log_event(f"Kritischer Fehler bei Dateiverarbeitung: {error_msg}")
        source.sync_status = "error"
        source.last_error = error_msg
        db.commit()
    finally:
        db.close()
