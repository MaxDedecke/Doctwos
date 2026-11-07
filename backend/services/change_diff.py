"""Resolve indexed Git revisions and map changed head lines to code objects."""

import os
import re
import subprocess
from pathlib import Path, PurePosixPath

import core.config as cfg
from doctus_models.database import CodeEntity, KnowledgeSource
from doctus_models.language_profile import ROUTINE_TYPES
from sqlalchemy.orm import Session
from services.change_impact import inspect_change_impact, MAX_IMPACT_NODES

MAX_DIFF_FILES = 20
MAX_DIFF_OUTPUT_BYTES = 64_000
MAX_DIFF_REPORTED_FILES = 100


def _git_worktree(repos_root: Path, source_id: int) -> Path | None:
    """Return one configured Git worktree without accepting caller-controlled paths."""
    worktree = (repos_root / "wt" / f"ks_{source_id}").resolve()
    if os.path.commonpath((str(repos_root), str(worktree))) != str(repos_root):
        return None
    return worktree if worktree.is_dir() else None


def _git_commit(worktree: Path, revision: str) -> tuple[str | None, str | None]:
    if not isinstance(revision, str) or not revision.strip() or len(revision) > 256:
        return None, "Git revision must be a non-empty ref of at most 256 characters."
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(worktree),
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{revision}^{{commit}}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, "The local Git worktree could not resolve the requested revision."
    commit = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"[0-9a-f]{40}", commit):
        return None, f"Git revision {revision!r} is not available in the local worktree."
    return commit, None


def _diff_targets(
    db: Session, project_id: int, source_id: int | None, base_ref: str, head_ref: str
) -> dict:
    """Resolve a bounded Git diff to indexed files from one project source."""
    sources_query = db.query(KnowledgeSource).filter(
        KnowledgeSource.project_id == project_id, KnowledgeSource.type.ilike("git")
    )
    if source_id is not None:
        sources_query = sources_query.filter(KnowledgeSource.id == source_id)
    sources = sources_query.order_by(KnowledgeSource.id).limit(2).all()
    if not sources:
        return {"error": "No matching Git source is available in the current project."}
    if source_id is None and len(sources) > 1:
        return {
            "error": "source_id is required for diff analysis when the project has multiple Git sources."
        }
    source = sources[0]
    repos_root = Path(getattr(cfg, "REPOS_ROOT", "/repos")).resolve()
    worktree = _git_worktree(repos_root, source.id)
    if not worktree:
        return {
            "error": "The local Git worktree for this source is unavailable; diff analysis needs a synced worktree."
        }
    base_commit, error = _git_commit(worktree, base_ref)
    if error:
        return {"error": error}
    head_commit, error = _git_commit(worktree, head_ref)
    if error:
        return {"error": error}
    cursor = source.sync_cursor if isinstance(source.sync_cursor, dict) else {}
    indexed_commit = cursor.get("last_commit")
    if source.sync_status != "completed" or not indexed_commit:
        return {
            "error": "Diff analysis requires a completed Git source sync with a recorded indexed commit."
        }
    if indexed_commit != head_commit:
        return {
            "error": "The requested head revision differs from the indexed source revision; sync that revision before analyzing its impact."
        }
    worktree_commit, error = _git_commit(worktree, "HEAD")
    if error or worktree_commit != head_commit:
        return {
            "error": "The local Git worktree differs from the indexed head revision; sync the source before analyzing its impact."
        }
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(worktree),
                "diff",
                "--name-only",
                "--no-ext-diff",
                "-z",
                base_commit,
                head_commit,
                "--",
            ],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"error": "The local Git worktree could not calculate the requested diff."}
    if result.returncode:
        return {"error": "The local Git worktree rejected the requested diff."}
    diff_bytes = result.stdout
    output_truncated = len(diff_bytes) > MAX_DIFF_OUTPUT_BYTES
    bounded_bytes = diff_bytes[:MAX_DIFF_OUTPUT_BYTES]
    if output_truncated:
        bounded_bytes = bounded_bytes.rsplit(b"\0", 1)[0] + b"\0" if b"\0" in bounded_bytes else b""
    raw_paths = bounded_bytes.decode("utf-8", errors="replace").split("\0")
    paths = [PurePosixPath(path).as_posix() for path in raw_paths if _safe_diff_path(path)]
    indexed_paths = (
        {
            path
            for (path,) in db.query(CodeEntity.file_path)
            .filter(
                CodeEntity.project_id == project_id,
                CodeEntity.source_id == source.id,
                CodeEntity.file_path.in_(paths),
            )
            .distinct()
        }
        if paths
        else set()
    )
    selected = [path for path in paths if path in indexed_paths][:MAX_DIFF_FILES]
    return {
        "source_id": source.id,
        "base_commit": base_commit,
        "head_commit": head_commit,
        "changed_files": paths[:MAX_DIFF_REPORTED_FILES],
        "changed_file_count": len(paths) if not output_truncated else None,
        "indexed_files": selected,
        "unindexed_files": [path for path in paths if path not in indexed_paths][
            :MAX_DIFF_REPORTED_FILES
        ],
        "truncated": (
            output_truncated
            or len(paths) > MAX_DIFF_REPORTED_FILES
            or len([path for path in paths if path in indexed_paths]) > MAX_DIFF_FILES
        ),
    }


def _safe_diff_path(value: str) -> bool:
    path = PurePosixPath(value.replace("\\", "/"))
    return (
        bool(value) and not path.is_absolute() and ".." not in path.parts and path.as_posix() != "."
    )


def _changed_entities(db, project_id, target):
    worktree = _git_worktree(
        Path(getattr(cfg, "REPOS_ROOT", "/repos")).resolve(), target["source_id"]
    )
    changed, ranges = [], {}
    for path in target["indexed_files"]:
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(worktree),
                    "diff",
                    "--no-ext-diff",
                    "--no-textconv",
                    "--unified=0",
                    target["base_commit"],
                    target["head_commit"],
                    "--",
                    path,
                ],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None, {}
        if result.returncode or len(result.stdout) > MAX_DIFF_OUTPUT_BYTES:
            return None, {}
        raw_hunks = re.findall(
            r"^@@ -[^ ]+ \+(\d+)(?:,(\d+))? @@",
            result.stdout.decode("utf-8", errors="replace"),
            re.MULTILINE,
        )
        hunks = [
            {
                "start_line": max(1, int(start)),
                "end_line": max(1, int(start)) + max(int(count or "1"), 1) - 1,
                "deletion_anchor": count == "0",
            }
            for start, count in raw_hunks
        ]
        ranges[path] = hunks
        entities = (
            db.query(CodeEntity)
            .filter(
                CodeEntity.project_id == project_id,
                CodeEntity.source_id == target["source_id"],
                CodeEntity.file_path == path,
            )
            .order_by(CodeEntity.id)
            .all()
        )
        for hunk in hunks:
            if hunk["deletion_anchor"]:
                continue
            overlapping = [
                e
                for e in entities
                if e.start_line is not None
                and e.end_line is not None
                and e.start_line <= hunk["end_line"]
                and e.end_line >= hunk["start_line"]
            ]
            routines = [e for e in overlapping if e.type in ROUTINE_TYPES]
            overlapping = routines or overlapping
            # Keep the innermost indexed objects. A declaration outside a method
            # can still map to its owning class or compilation unit.
            innermost = [
                e
                for e in overlapping
                if not any(
                    e.start_line <= other.start_line
                    and e.end_line >= other.end_line
                    and (e.start_line, e.end_line) != (other.start_line, other.end_line)
                    for other in overlapping
                )
            ]
            changed.extend(e.id for e in innermost)
    return list(dict.fromkeys(changed)), ranges


def _diff_impact(
    db: Session,
    *,
    project_id: int,
    source_id: int | None,
    base_ref: str,
    head_ref: str,
    direction: str,
    hops: int,
    limit: int,
) -> dict:
    target = _diff_targets(db, project_id, source_id, base_ref, head_ref)
    if target.get("error"):
        return target
    changed_ids, line_ranges = _changed_entities(db, project_id, target)
    if changed_ids is None:
        return {"error": "The bounded Git line diff could not be read."}
    impacts = [
        inspect_change_impact(
            db,
            project_id=project_id,
            entity_id=entity_id,
            direction=direction,
            hops=hops,
            limit=limit,
        )
        for entity_id in changed_ids[:MAX_IMPACT_NODES]
    ]
    nodes = {
        node["id"]: node
        for impact in impacts
        for node in impact.get("nodes", [])
        if isinstance(node, dict) and "id" in node
    }
    edges = {
        edge["id"]: edge
        for impact in impacts
        for edge in impact.get("edges", [])
        if isinstance(edge, dict) and "id" in edge
    }
    unknown_edges = {
        edge["id"]: edge
        for impact in impacts
        for edge in impact.get("unknown_edges", [])
        if isinstance(edge, dict) and "id" in edge
    }
    visible_nodes = dict(list(nodes.items())[:limit])
    visible_edges = [
        edge
        for edge in edges.values()
        if edge.get("source") in visible_nodes and edge.get("target") in visible_nodes
    ][:limit]
    visible_unknown_edges = [
        edge for edge in unknown_edges.values() if edge.get("source_entity_id") in visible_nodes
    ][:limit]
    return {
        "status": "ok" if nodes else "no_indexed_impact",
        "target": {
            "kind": "diff",
            "source_id": target["source_id"],
            "base_ref": base_ref,
            "head_ref": head_ref,
            "base_commit": target["base_commit"],
            "head_commit": target["head_commit"],
            "changed_files": target["changed_files"],
            "changed_line_ranges": line_ranges,
            "changed_entity_ids": changed_ids,
            "indexed_files": target["indexed_files"],
            "unindexed_files": target["unindexed_files"],
            "changed_file_count": target["changed_file_count"],
            "entity_ids": sorted(
                {
                    entity_id
                    for impact in impacts
                    for entity_id in impact.get("target", {}).get("entity_ids", [])
                    if entity_id in visible_nodes
                }
            ),
        },
        "direction": direction,
        "hops": hops,
        "nodes": list(visible_nodes.values()),
        "edges": visible_edges,
        "unknown_edges": visible_unknown_edges,
        "truncated": len(changed_ids) > MAX_IMPACT_NODES
        or target["truncated"]
        or len(nodes) > limit
        or len(edges) > limit
        or len(unknown_edges) > limit
        or any(impact.get("truncated") for impact in impacts),
        "impact_summary": {
            "limitations": [
                "The diff is read from the local synced Git worktree; it can only include revisions available there.",
                "Changed head lines select the innermost indexed objects; deleted lines use a head-line anchor. Historical relationships of deleted objects are unavailable.",
                "Only changed files with indexed code entities are analyzed. Deleted, renamed-only, unindexed and non-code files are listed but have no code impact graph.",
            ]
        },
    }
