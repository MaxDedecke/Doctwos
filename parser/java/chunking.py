"""Structure-aware, physical-line Java chunks for source retrieval."""

from __future__ import annotations

from core.model import Chunk, Entity


DEFAULT_CHUNK_SIZE = 1000


def _split_range(
    lines: list[str], start_line: int, end_line: int, chunk_size: int
) -> list[tuple[str, int, int]]:
    pieces: list[tuple[str, int, int]] = []
    line_index = start_line - 1
    end_index = min(end_line, len(lines))
    while line_index < end_index:
        start = line_index
        content_length = 0
        while line_index < end_index:
            line_length = len(lines[line_index]) + (1 if line_index > start else 0)
            if line_index > start and content_length + line_length > chunk_size:
                break
            content_length += line_length
            line_index += 1
        pieces.append(("\n".join(lines[start:line_index]), start + 1, line_index))
    return pieces


def _symbol_groups(entities: list[Entity]) -> list[tuple[Entity, list[Entity]]]:
    groups: list[tuple[Entity, list[Entity]]] = []
    fields: dict[tuple[str | None, int, int], list[Entity]] = {}
    for entity in entities:
        if entity.type in {"method", "constructor", "initializer"}:
            groups.append((entity, [entity]))
        elif entity.type == "field":
            key = (entity.parent_qualified_name, entity.start_line, entity.end_line)
            fields.setdefault(key, []).append(entity)
    for field_entities in fields.values():
        groups.append((field_entities[0], field_entities))
    return sorted(groups, key=lambda item: (item[0].start_line, item[0].end_line))


def _container_for_line(entities: list[Entity], line: int) -> Entity | None:
    containers = [
        entity
        for entity in entities
        if entity.type in {"class", "interface", "enum", "record", "annotation_type"}
        and entity.start_line <= line <= entity.end_line
    ]
    return (
        min(containers, key=lambda entity: entity.end_line - entity.start_line)
        if containers
        else None
    )


def chunk_java_source(
    source: str,
    entities: list[Entity],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[Chunk]:
    """Prefer one chunk per method/constructor/initializer and field group.

    Uncovered source lines (package/imports, type headers and comments) are
    kept as context chunks. Invalid files without extracted declarations use
    explicit whole-source fallback chunks. Splits happen only at line edges.
    """

    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    lines = source.splitlines()
    if not lines:
        return []

    symbols = _symbol_groups(entities)
    has_declarations = any(entity.type != "compilation_unit" for entity in entities)
    covered: set[int] = set()
    chunks: list[Chunk] = []

    for representative, group in symbols:
        start_line = max(1, representative.start_line)
        end_line = min(len(lines), representative.end_line)
        if end_line < start_line:
            continue
        for line in range(start_line, end_line + 1):
            covered.add(line)
        if len(group) > 1:
            symbol_type = "fields"
            symbol_name = ", ".join(item.name for item in group)
            symbol_qname: str | list[str] = [item.qualified_name or item.name for item in group]
        else:
            symbol_type = representative.type
            symbol_name = representative.name
            symbol_qname = representative.qualified_name or representative.name

        pieces = _split_range(lines, start_line, end_line, chunk_size)
        for piece_index, (content, piece_start, piece_end) in enumerate(pieces, start=1):
            meta = {
                "language": "java",
                "symbol_type": symbol_type,
                "symbol_name": symbol_name,
                "symbol_qualified_name": symbol_qname,
                "container_path": representative.parent_qualified_name,
                "start_line": piece_start,
                "end_line": piece_end,
            }
            if len(pieces) > 1:
                meta.update({"part": piece_index, "parts": len(pieces)})
            chunks.append(Chunk(content, piece_start, piece_end, meta))

    if not has_declarations:
        return [
            Chunk(
                content,
                start_line,
                end_line,
                {
                    "language": "java",
                    "symbol_type": "source",
                    "fallback": True,
                    "start_line": start_line,
                    "end_line": end_line,
                },
            )
            for content, start_line, end_line in _split_range(lines, 1, len(lines), chunk_size)
            if content.strip()
        ]

    line = 1
    while line <= len(lines):
        if line in covered:
            line += 1
            continue
        start_line = line
        while line <= len(lines) and line not in covered:
            line += 1
        end_line = line - 1
        for content, piece_start, piece_end in _split_range(
            lines, start_line, end_line, chunk_size
        ):
            if not content.strip():
                continue
            container = _container_for_line(entities, piece_start)
            chunks.append(
                Chunk(
                    content,
                    piece_start,
                    piece_end,
                    {
                        "language": "java",
                        "symbol_type": "context",
                        "symbol_qualified_name": container.qualified_name if container else None,
                        "container_path": container.qualified_name if container else None,
                        "start_line": piece_start,
                        "end_line": piece_end,
                    },
                )
            )

    return sorted(chunks, key=lambda chunk: (chunk.start_line, chunk.end_line))
