"""Textbasierte Referenzsuche für Dokumente und Dateien innerhalb eines Projekts."""

import re

from models.database import DocumentChunk


def _ilike_to_regex(pattern: str) -> re.Pattern:
    """Ersetzt SQL-ILIKE, weil verschlüsselte Inhalte in Python entschlüsselt werden."""
    return re.compile(
        ".*".join(re.escape(part) for part in pattern.split("%")), re.IGNORECASE | re.DOTALL
    )


def refs_for_document(project_id: int, file_path: str, base_name: str, db) -> list[dict]:
    """Findet Code-Stellen, die ein Dokument (PDF, Word, ...) erwähnen."""
    patterns = [_ilike_to_regex(f"%{base_name}%"), _ilike_to_regex(f"%{file_path}%")]
    candidates = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.project_id == project_id, DocumentChunk.source_id.is_(None))
        .all()
    )
    results = [
        chunk
        for chunk in candidates
        if any(pattern.search(chunk.content or "") for pattern in patterns)
    ]
    return _extract_line_refs(
        results, lambda line: base_name.upper() in line.upper() or file_path.upper() in line.upper()
    )


def refs_for_file(project_id: int, file_path: str, base_name: str, db) -> list[dict]:
    """Findet Stellen, die per COPY/import/from/require auf eine Datei verweisen."""
    patterns = [
        _ilike_to_regex(pattern)
        for pattern in (
            f'%COPY%"{base_name}"%',
            f"%COPY%'{base_name}'%",
            f"%COPY% {base_name}%",
            f"%import %{base_name}%",
            f"%from %{base_name}%",
            f'%from %"{base_name}"%',
            f"%from %'{base_name}'%",
            f'%require(%"{base_name}"%',
            f"%require(%'{base_name}'%",
        )
    ]
    candidates = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.project_id == project_id, DocumentChunk.file_path != file_path)
        .all()
    )
    results = [
        chunk
        for chunk in candidates
        if any(pattern.search(chunk.content or "") for pattern in patterns)
    ]
    return _deduplicate_refs(
        _extract_line_refs(
            results,
            lambda line: (
                base_name.upper() in line.upper()
                and any(
                    keyword in line.upper() for keyword in ["COPY", "IMPORT", "FROM", "REQUIRE"]
                )
            ),
        )
    )


def _deduplicate_refs(references: list[dict]) -> list[dict]:
    seen: set[tuple[str, int]] = set()
    unique_references = []
    for reference in references:
        key = (reference["file_path"], reference["line"])
        if key not in seen:
            seen.add(key)
            unique_references.append(reference)
    return unique_references


def _extract_line_refs(chunks, line_predicate) -> list[dict]:
    result = []
    seen = set()
    for chunk in chunks:
        lines = chunk.content.splitlines()
        matching = [
            chunk.start_line + index for index, line in enumerate(lines) if line_predicate(line)
        ]
        for line_num in matching or [chunk.start_line]:
            key = (chunk.file_path, line_num)
            if key not in seen:
                seen.add(key)
                index = line_num - chunk.start_line
                preview = (
                    lines[index].strip() if 0 <= index < len(lines) else chunk.content[:60].strip()
                )
                result.append({"file_path": chunk.file_path, "line": line_num, "preview": preview})
    return result
