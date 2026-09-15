"""COBOL-specific source-wide preparation hooks for structural parsing."""

from __future__ import annotations

import os

import git_utils
from cobol import copybook
from cobol.copybook import CopybookIndex
from cobol.names import canonical_identifier
from cobol.parse import parse_copybook
from core.model import ParseResult
from core.source_decoder import SourceDecodeError, decode_source
from cobol.profile import BuildProfile


def prepare_copybook_index(
    wt: str,
    extensions: dict[str, set[str]],
    profiles_by_path: dict[str, BuildProfile | None] | None = None,
) -> CopybookIndex:
    """Build the source-wide Copybook index, including inherited fields.

    This is the shared preparation hook for the COBOL and Copybook parser
    entries. It scans the entire tracked tree so changed programs can still
    resolve unchanged Copybooks during an incremental sync.
    """
    copybook_exts = extensions.get("copybook", set())
    if not copybook_exts:
        return CopybookIndex()
    tracked = git_utils.list_tracked_files(wt)
    index = CopybookIndex()
    for path in tracked:
        if os.path.splitext(path)[1].lower() not in copybook_exts:
            continue
        name = canonical_identifier(os.path.splitext(os.path.basename(path))[0])
        index.setdefault(name, []).append(path)
        full_path = os.path.join(wt, path)
        try:
            if os.path.getsize(full_path) > git_utils.MAX_READ_BYTES:
                continue
            with open(full_path, "rb") as f:
                content, _ = decode_source(
                    f.read(git_utils.MAX_READ_BYTES),
                    (profiles_by_path or {}).get(path).encoding
                    if (profiles_by_path or {}).get(path) is not None
                    else None,
                )
            parsed: ParseResult = parse_copybook(
                content, path, profile=(profiles_by_path or {}).get(path)
            )
            index.fields_by_path[path] = [
                {
                    "name": entity.name,
                    "parent": entity.parent_name,
                    "qualified_name": entity.qualified_name,
                    "path": path,
                }
                for entity in parsed.entities
                if entity.type == "data_item"
            ]
            index.copy_edges_by_path[path] = [edge for edge in parsed.edges if edge.type == "COPY"]
        except (OSError, SourceDecodeError):
            # Keep the name index usable when one source file cannot be read;
            # only field inheritance for that file is omitted.
            continue

    local_fields = {path: list(fields) for path, fields in index.fields_by_path.items()}
    expanded: dict[str, list[dict]] = {}

    def fields_for(path: str, ancestry: set[str]) -> list[dict]:
        if path in expanded:
            return expanded[path]
        result = list(local_fields.get(path, []))
        if path in ancestry:
            return result
        for edge in index.copy_edges_by_path.get(path, []):
            target = copybook.resolve_path(edge.dst_name, (edge.meta or {}).get("library"), index)
            if target is None or target in ancestry:
                continue
            target_index = CopybookIndex(
                index, fields_by_path={target: fields_for(target, ancestry | {path})}
            )
            result.extend(copybook.inherited_fields([edge], target_index))
        expanded[path] = result
        return result

    for path in local_fields:
        index.fields_by_path[path] = fields_for(path, set())
    return index
