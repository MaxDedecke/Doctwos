"""Bounded AsciiDoc include traversal and source-preserving chunk excerpts."""

from dataclasses import dataclass

from models.database import CodeEntity, CodeEdge


def include_context(db, entity_ids, edges):
    include_edges = [
        e
        for e in edges
        if e.type == "INCLUDES" and (e.meta_json or {}).get("language") == "asciidoc"
    ]
    queue = [
        (e.dst_entity_id, e.project_id, e.source_id, e.variant_key)
        for e in include_edges
        if e.src_entity_id in entity_ids
    ]
    visited = set()
    while queue and len(visited) < 100:
        identity, project, source, variant = queue.pop(0)
        if identity is None or identity in visited:
            continue
        root = db.get(CodeEntity, identity)
        if root is None or (root.project_id, root.source_id, root.variant_key) != (
            project,
            source,
            variant,
        ):
            continue
        visited.add(identity)
        if root.type != "asciidoc_document":
            continue
        nested = (
            db.query(CodeEdge)
            .join(CodeEntity, CodeEntity.id == CodeEdge.src_entity_id)
            .filter(
                CodeEntity.project_id == root.project_id,
                CodeEntity.source_id == root.source_id,
                CodeEntity.variant_key == root.variant_key,
                CodeEntity.file_path == root.file_path,
                CodeEdge.type == "INCLUDES",
                CodeEdge.resolution == "resolved",
            )
            .order_by(CodeEdge.src_start_line, CodeEdge.id)
            .all()
        )
        for edge in nested:
            if (edge.meta_json or {}).get("language") == "asciidoc":
                include_edges.append(edge)
                queue.append(
                    (edge.dst_entity_id, root.project_id, root.source_id, root.variant_key)
                )
    selections = {}
    for edge in include_edges:
        ranges = (edge.meta_json or {}).get("selection_ranges") or []
        if edge.dst_entity_id not in selections:
            selections[edge.dst_entity_id] = ranges or None
        elif selections[edge.dst_entity_id] is not None:
            selections[edge.dst_entity_id] = (
                selections[edge.dst_entity_id] + ranges if ranges else None
            )
    return visited, selections


@dataclass(frozen=True)
class ChunkExcerpt:
    original: object
    content: str
    start_line: int
    end_line: int

    def __getattr__(self, name):
        return getattr(self.original, name)


def selected_excerpts(chunk, ranges):
    if not ranges or chunk.start_line is None or chunk.end_line is None:
        return [chunk]
    lines = (chunk.content or "").splitlines()
    intervals = sorted(
        (max(a, chunk.start_line), min(b, chunk.end_line))
        for a, b in ranges
        if a <= chunk.end_line and b >= chunk.start_line
    )
    merged = []
    for start, end in intervals:
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return [
        ChunkExcerpt(
            chunk,
            "\n".join(lines[start - chunk.start_line : end - chunk.start_line + 1]),
            start,
            end,
        )
        for start, end in merged
    ]
