"""Formatting of indexed source excerpts in chat context."""

from doctus_models.database import DocumentChunk


def chunk_header(chunk: DocumentChunk) -> str:
    """Format an indexed chunk's location for an LLM context header."""
    page = (chunk.metadata_json or {}).get("page")
    location = (
        f"Seite {page}, Zeile {chunk.start_line}-{chunk.end_line}"
        if page
        else f"Zeile {chunk.start_line}-{chunk.end_line}"
    )
    return f"{chunk.file_path} ({location})"


def _format_chunk_context(chunk: DocumentChunk, label: str) -> str:
    """Render one retrieved chunk as explicitly untrusted model context."""
    source_id = f' source_id="{chunk.source_id}"' if chunk.source_id is not None else ""
    lines = ""
    if chunk.start_line is not None:
        lines += f' start_line="{chunk.start_line}"'
    if chunk.end_line is not None:
        lines += f' end_line="{chunk.end_line}"'
    return (
        f'<untrusted_source path="{chunk.file_path}" chunk_id="{chunk.id}"{source_id}{lines}>\n'
        f"{label}: {chunk_header(chunk)}\n"
        f"{chunk.content}\n"
        "</untrusted_source>"
    )
