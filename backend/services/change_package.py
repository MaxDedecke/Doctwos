"""Build a bounded evidence package around the existing change-impact graph."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path, PurePosixPath

from sqlalchemy import or_
from sqlalchemy.orm import Session

import core.config as cfg
from models.database import (
    CodeEdge,
    CodeEntity,
    DocumentChunk,
    EntityDocLink,
    KnowledgeLink,
    KnowledgeSource,
    Project,
)
from services.change_impact import inspect_change_impact


MAX_PACKAGE_LINKS = 40
MAX_PACKAGE_TESTS = 50
MAX_CODEOWNERS_BYTES = 128_000
MAX_CODEOWNERS_RULES = 2_000
MAX_DIFF_FILES = 20
MAX_DIFF_OUTPUT_BYTES = 64_000
MAX_DIFF_REPORTED_FILES = 100
_TEST_PATH = re.compile(r"(?:^|[/_.-])(?:test|tests|spec|specs)(?:[/_.-]|$)", re.IGNORECASE)
_BUG_WORD = re.compile(r"\b(?:bug|defect|incident|regression|fehler|störung|stoerung)\b", re.IGNORECASE)
_RULE_WORD = re.compile(r"\b(?:fachregel|business rule|geschäftsregel|geschaeftsregel|regelwerk)\b", re.IGNORECASE)


def _chunk_document(db: Session, chunk_id: int | None, project_id: int) -> DocumentChunk | None:
    if chunk_id is None:
        return None
    chunk = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.id == chunk_id, DocumentChunk.project_id == project_id)
        .first()
    )
    if not chunk:
        return None
    if chunk.source_id:
        project_team_id = db.query(Project.team_id).filter(Project.id == project_id).scalar()
        source = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.id == chunk.source_id,
                KnowledgeSource.project_id == project_id,
                KnowledgeSource.team_id == project_team_id,
            )
            .first()
        )
        if not source:
            return None
    return chunk


def _doc_metadata(chunk: DocumentChunk | None) -> dict:
    return chunk.metadata_json if chunk and isinstance(chunk.metadata_json, dict) else {}


def _source_type(db: Session, chunk: DocumentChunk | None, preferred: str | None) -> str | None:
    if preferred:
        return preferred
    if not chunk:
        return None
    metadata_type = _doc_metadata(chunk).get("source_type")
    if metadata_type:
        return str(metadata_type)
    if chunk.source_id:
        value = db.query(KnowledgeSource.type).filter(KnowledgeSource.id == chunk.source_id).scalar()
        return str(value) if value else None
    return "Git" if chunk.project_id is not None else "Local"


def _excerpt(chunk: DocumentChunk | None) -> str | None:
    if not chunk or not chunk.content:
        return None
    return " ".join(str(chunk.content).split())[:360]


def _linked_documents(db: Session, project_id: int, entity_ids: set[int]) -> tuple[list[dict], bool]:
    if not entity_ids:
        return [], False

    records: list[dict] = []
    seen: set[tuple[str, int | str]] = set()
    truncated = False

    entity_links = (
        db.query(EntityDocLink)
        .filter(
            EntityDocLink.project_id == project_id,
            EntityDocLink.status == "approved",
            EntityDocLink.entity_id.in_(entity_ids),
        )
        .order_by(EntityDocLink.id)
        .limit(MAX_PACKAGE_LINKS + 1)
        .all()
    )
    if len(entity_links) > MAX_PACKAGE_LINKS:
        truncated = True
        entity_links = entity_links[:MAX_PACKAGE_LINKS]

    for link in entity_links:
        chunk = _chunk_document(db, link.chunk_id, project_id)
        metadata = _doc_metadata(chunk)
        source_type = _source_type(db, chunk, link.source_type)
        if str(source_type or "").casefold() == "git":
            continue
        item = {
            "kind": "approved_entity_document_link",
            "entity_id": link.entity_id,
            "title": link.doc_title or metadata.get("title") or (chunk.file_path if chunk else "Linked document"),
            "url": link.doc_url or metadata.get("url"),
            "source_type": source_type,
            "evidence": {
                "link_id": link.id,
                "status": link.status,
                "link_type": link.link_type,
                "score": link.score,
                "created_by": link.created_by,
                "reviewed_at": link.reviewed_at.isoformat() if link.reviewed_at else None,
                "context": (link.context or "")[:400] or None,
                "chunk_id": chunk.id if chunk else None,
                "source_id": chunk.source_id if chunk else None,
                "file_path": chunk.file_path if chunk else None,
                "start_line": chunk.start_line if chunk else None,
                "end_line": chunk.end_line if chunk else None,
                "page": metadata.get("page"),
                "section": metadata.get("section"),
                "url_anchor": metadata.get("url_anchor") or metadata.get("anchor"),
                "excerpt": _excerpt(chunk),
            },
            "issue_key": metadata.get("issue_key") or _issue_key(link.doc_title),
        }
        key = ("chunk", chunk.id) if chunk else ("entity_doc", link.id)
        if key not in seen:
            records.append(item)
            seen.add(key)

    knowledge_links = (
        db.query(KnowledgeLink)
        .filter(
            KnowledgeLink.status == "approved",
            or_(
                KnowledgeLink.source_a_entity_id.in_(entity_ids),
                KnowledgeLink.source_b_entity_id.in_(entity_ids),
            ),
            or_(
                KnowledgeLink.source_a_type == "entity",
                KnowledgeLink.source_b_type == "entity",
            ),
        )
        .order_by(KnowledgeLink.id)
        .limit(MAX_PACKAGE_LINKS + 1)
        .all()
    )
    if len(knowledge_links) > MAX_PACKAGE_LINKS:
        truncated = True
        knowledge_links = knowledge_links[:MAX_PACKAGE_LINKS]

    for link in knowledge_links:
        sides = (
            ("a", link.source_a_type, link.source_a_entity_id, link.source_a_chunk_id, link.source_a_title, link.source_a_url, link.source_a_source_type),
            ("b", link.source_b_type, link.source_b_entity_id, link.source_b_chunk_id, link.source_b_title, link.source_b_url, link.source_b_source_type),
        )
        entity_side = next((side for side in sides if side[1] == "entity" and side[2] in entity_ids), None)
        document_side = next((side for side in sides if side[1] == "document"), None)
        if not entity_side or not document_side:
            continue
        chunk = _chunk_document(db, document_side[3], project_id)
        # A cross-project/global document is not included through a generic
        # graph edge. The evidence package stays within this project's scope.
        if not chunk:
            continue
        metadata = _doc_metadata(chunk)
        source_type = _source_type(db, chunk, document_side[6])
        if str(source_type or "").casefold() == "git":
            continue
        item = {
            "kind": "approved_knowledge_link",
            "entity_id": entity_side[2],
            "title": document_side[4] or metadata.get("title") or chunk.file_path,
            "url": document_side[5] or metadata.get("url"),
            "source_type": source_type,
            "evidence": {
                "link_id": link.id,
                "status": link.status,
                "link_type": link.link_type,
                "direction": link.direction,
                "score": link.score,
                "created_by": link.created_by,
                "reviewed_at": link.reviewed_at.isoformat() if link.reviewed_at else None,
                "context": (link.context or "")[:400] or None,
                "chunk_id": chunk.id,
                "source_id": chunk.source_id,
                "file_path": chunk.file_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "page": metadata.get("page"),
                "section": metadata.get("section"),
                "url_anchor": metadata.get("url_anchor") or metadata.get("anchor"),
                "excerpt": _excerpt(chunk),
            },
            "issue_key": metadata.get("issue_key") or _issue_key(document_side[4]),
        }
        key = ("chunk", chunk.id)
        if key not in seen:
            records.append(item)
            seen.add(key)

    records.sort(key=lambda item: (item["title"].casefold(), item["kind"], str(item["evidence"].get("link_id"))))
    return records[:MAX_PACKAGE_LINKS], truncated or len(records) > MAX_PACKAGE_LINKS


def _issue_key(title: str | None) -> str | None:
    match = re.match(r"\s*([A-Z][A-Z0-9]{1,15}-\d+)\b", title or "")
    return match.group(1) if match else None


def _relationship_paths(impact: dict) -> dict[int, dict]:
    """Return shortest, line-backed paths from changed entities to impacted nodes."""
    nodes = {node["id"]: node for node in impact.get("nodes", []) if isinstance(node, dict) and isinstance(node.get("id"), int)}
    target = impact.get("target") or {}
    starts = [entity_id for entity_id in target.get("entity_ids", []) if entity_id in nodes]
    direction = impact.get("direction", "incoming")
    adjacency: dict[int, list[tuple[int, dict, bool]]] = {}
    for edge in impact.get("edges", []):
        source, destination = edge.get("source"), edge.get("target")
        if source not in nodes or destination not in nodes:
            continue
        if direction in {"incoming", "both"}:
            adjacency.setdefault(destination, []).append((source, edge, True))
        if direction in {"outgoing", "both"}:
            adjacency.setdefault(source, []).append((destination, edge, False))

    paths: dict[int, dict] = {}
    queue: list[int] = []
    for entity_id in starts:
        paths[entity_id] = {"root_entity_id": entity_id, "hops": 0, "edges": []}
        queue.append(entity_id)
    while queue:
        current = queue.pop(0)
        for neighbor, edge, reverse in sorted(adjacency.get(current, []), key=lambda row: row[1].get("id", 0)):
            if neighbor in paths:
                continue
            step = {
                "edge_id": edge["id"],
                "from_entity_id": current,
                "to_entity_id": neighbor,
                "relationship": edge["type"],
                "resolution": edge["resolution"],
                "persisted_source_entity_id": edge["source"],
                "persisted_target_entity_id": edge["target"],
                "evidence_file": nodes[edge["source"]].get("file_path"),
                "evidence_start_line": edge.get("start_line"),
                "evidence_end_line": edge.get("end_line"),
                "traversed_against_relationship": reverse,
            }
            paths[neighbor] = {
                "root_entity_id": paths[current]["root_entity_id"],
                "hops": paths[current]["hops"] + 1,
                "edges": [*paths[current]["edges"], step],
            }
            queue.append(neighbor)
    return paths


def _test_evidence(db: Session, project_id: int, impacted_ids: set[int]) -> dict:
    if not impacted_ids:
        return {"status": "unknown", "items": [], "coverage_claim": "none"}
    candidates = (
        db.query(CodeEdge, CodeEntity)
        .join(CodeEntity, CodeEntity.id == CodeEdge.src_entity_id)
        .filter(
            CodeEdge.project_id == project_id,
            CodeEdge.resolution == "resolved",
            CodeEdge.dst_entity_id.in_(impacted_ids),
            CodeEntity.project_id == project_id,
            or_(
                CodeEntity.file_path.ilike("%test%"),
                CodeEntity.file_path.ilike("%spec%"),
                CodeEntity.name.ilike("%test%"),
                CodeEntity.name.ilike("%spec%"),
            ),
        )
        .order_by(CodeEdge.id)
        .limit(MAX_PACKAGE_TESTS * 3 + 1)
        .all()
    )
    candidates_truncated = len(candidates) > MAX_PACKAGE_TESTS * 3
    candidates = candidates[: MAX_PACKAGE_TESTS * 3]
    items = []
    seen = set()
    for edge, test_entity in candidates:
        if not _TEST_PATH.search(test_entity.file_path or "") and not _TEST_PATH.search(test_entity.name or ""):
            continue
        key = (test_entity.id, edge.dst_entity_id)
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "entity": {
                "id": test_entity.id,
                "name": test_entity.qualified_name or test_entity.name,
                "file_path": test_entity.file_path,
                "source_id": test_entity.source_id,
                "start_line": test_entity.start_line,
                "end_line": test_entity.end_line,
            },
            "related_entity_id": edge.dst_entity_id,
            "relationship": edge.type,
            "evidence": {
                "edge_id": edge.id,
                "resolution": edge.resolution,
                "file_path": test_entity.file_path,
                "start_line": edge.src_start_line,
                "end_line": edge.src_end_line,
            },
        })
        if len(items) >= MAX_PACKAGE_TESTS:
            break
    return {
        "status": "found" if items else "unknown",
        "items": items,
        "truncated": candidates_truncated or len(items) >= MAX_PACKAGE_TESTS,
        "coverage_claim": "none",
        "note": (
            "Only statically resolved indexed relationships from conventionally named test/spec paths are listed."
            if items else "No test mapping was found in the bounded indexed relationships; this does not mean there are no tests."
        ),
    }


def _codeowners_regex(pattern: str) -> re.Pattern | None:
    """Compile the common CODEOWNERS glob subset; unsupported lines are skipped."""
    pattern = pattern.strip()
    if not pattern or pattern.startswith("!") or "[" in pattern or "]" in pattern:
        return None
    anchored = pattern.startswith("/")
    pattern = pattern.lstrip("/")
    directory = pattern.endswith("/")
    pattern = pattern.rstrip("/")
    parts = []
    i = 0
    while i < len(pattern):
        if pattern[i : i + 3] == "**/":
            parts.append(r"(?:.*/)?")
            i += 3
        elif pattern[i : i + 2] == "**":
            parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(pattern[i]))
            i += 1
    body = "".join(parts)
    if directory:
        body += r"(?:/.*)?"
    elif not anchored and "/" not in pattern:
        body = r"(?:.*/)?" + body
    return re.compile(r"^" + body + r"$")


def _load_codeowners(repo_root: Path) -> tuple[list[tuple[re.Pattern, list[str]]], str | None, bool]:
    for relative in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
        candidate = (repo_root / relative).resolve()
        if os.path.commonpath((str(repo_root.resolve()), str(candidate))) != str(repo_root.resolve()):
            continue
        if not candidate.exists():
            continue
        try:
            if not candidate.is_file():
                continue
            if candidate.stat().st_size > MAX_CODEOWNERS_BYTES:
                return [], relative, True
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return [], relative, True
        rules = []
        lines = text.splitlines()
        unsupported = len(lines) > MAX_CODEOWNERS_RULES
        for line in lines[:MAX_CODEOWNERS_RULES]:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            fields = stripped.split()
            if len(fields) < 2:
                unsupported = True
                continue
            expression = _codeowners_regex(fields[0])
            if expression is None:
                unsupported = True
                continue
            rules.append((expression, fields[1:]))
        return rules, relative, unsupported
    return [], None, False


def _ownership(db: Session, project_id: int, nodes: list[dict]) -> dict:
    source_ids = {node.get("source_id") for node in nodes if isinstance(node.get("source_id"), int)}
    by_source: dict[int, set[str]] = {}
    for node in nodes:
        source_id, file_path = node.get("source_id"), node.get("file_path")
        if not isinstance(source_id, int) or not isinstance(file_path, str):
            continue
        pure = PurePosixPath(file_path.replace("\\", "/"))
        if pure.is_absolute() or ".." in pure.parts:
            continue
        by_source.setdefault(source_id, set()).add(pure.as_posix())

    assignments: dict[tuple[int, str, tuple[str, ...]], set[str]] = {}
    unassigned: list[dict] = []
    partial = False
    sources = {
        source.id: source
        for source in db.query(KnowledgeSource).filter(
            KnowledgeSource.id.in_(source_ids),
            KnowledgeSource.project_id == project_id,
            KnowledgeSource.type.ilike("git"),
        ).all()
    } if source_ids else {}
    repos_root = Path(getattr(cfg, "REPOS_ROOT", "/repos")).resolve()
    for source_id, paths in by_source.items():
        source = sources.get(source_id)
        repo_root = (repos_root / "wt" / f"ks_{source_id}").resolve()
        if not source or os.path.commonpath((str(repos_root), str(repo_root))) != str(repos_root) or not repo_root.is_dir():
            unassigned.extend({"source_id": source_id, "file_path": path, "status": "unknown"} for path in sorted(paths))
            continue
        rules, codeowners_file, unsupported = _load_codeowners(repo_root)
        partial = partial or unsupported
        for path in sorted(paths):
            owners: list[str] = []
            for expression, rule_owners in rules:
                if expression.fullmatch(path):
                    owners = rule_owners
            if owners:
                assignments.setdefault((source_id, codeowners_file or "CODEOWNERS", tuple(owners)), set()).add(path)
            else:
                unassigned.append({"source_id": source_id, "file_path": path, "status": "unknown"})
    items = [
        {
            "source_id": source_id,
            "owners": list(owners),
            "files": sorted(paths)[:20],
            "source": {"type": "CODEOWNERS", "file_path": codeowners_file, "matching": "last matching supported rule"},
            "indexed_source_last_synced_at": sources[source_id].last_synced_at.isoformat() if sources.get(source_id) and sources[source_id].last_synced_at else None,
        }
        for (source_id, codeowners_file, owners), paths in sorted(assignments.items())
    ]
    return {
        "status": "found" if items else "unknown",
        "items": items[:MAX_PACKAGE_TESTS],
        "unknown_files": unassigned[:MAX_PACKAGE_TESTS],
        "partial": partial or len(items) > MAX_PACKAGE_TESTS or len(unassigned) > MAX_PACKAGE_TESTS,
        "note": "Owners come from the local Git worktree CODEOWNERS file using the supported glob subset; this is a routing hint, not verified business ownership." if items else "No CODEOWNERS owner could be read for the impacted files.",
    }


def _classify_knowledge(records: list[dict]) -> tuple[list[dict], list[dict]]:
    linked = []
    history = []
    for record in records:
        title = str(record.get("title") or "")
        evidence = record.get("evidence") or {}
        content = " ".join((title, str(evidence.get("context") or ""), str(evidence.get("excerpt") or "")))
        rule_match = _RULE_WORD.search(content)
        linked_record = {
            **record,
            "classification": "possible_domain_rule" if rule_match else "linked_document",
            "classification_basis": "title_or_excerpt_keyword" if rule_match else "approved_link_only",
            "classification_keyword": rule_match.group(0) if rule_match else None,
        }
        linked.append(linked_record)
        if str(record.get("source_type") or "").casefold() == "jira" or record.get("issue_key"):
            bug_match = _BUG_WORD.search(content)
            history.append({
                **record,
                "record_type": "jira_issue",
                "issue_key": record.get("issue_key"),
                "bug_candidate": bool(bug_match),
                "classification_keyword": bug_match.group(0) if bug_match else None,
                "classification_basis": f"keyword:{bug_match.group(0)}" if bug_match else "Jira source; issue type unavailable",
            })
    return linked, history


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
                "git", "-C", str(worktree), "rev-parse", "--verify", "--end-of-options",
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
        return {"error": "source_id is required for diff analysis when the project has multiple Git sources."}
    source = sources[0]
    repos_root = Path(getattr(cfg, "REPOS_ROOT", "/repos")).resolve()
    worktree = _git_worktree(repos_root, source.id)
    if not worktree:
        return {"error": "The local Git worktree for this source is unavailable; diff analysis needs a synced worktree."}
    base_commit, error = _git_commit(worktree, base_ref)
    if error:
        return {"error": error}
    head_commit, error = _git_commit(worktree, head_ref)
    if error:
        return {"error": error}
    try:
        result = subprocess.run(
            [
                "git", "-C", str(worktree), "diff", "--name-only", "--no-ext-diff",
                "-z", base_commit, head_commit, "--",
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
    raw_paths = diff_bytes[:MAX_DIFF_OUTPUT_BYTES].decode("utf-8", errors="replace").split("\0")
    paths = [PurePosixPath(path).as_posix() for path in raw_paths if _safe_diff_path(path)]
    output_truncated = len(diff_bytes) > MAX_DIFF_OUTPUT_BYTES
    indexed_paths = {
        path for (path,) in db.query(CodeEntity.file_path).filter(
            CodeEntity.project_id == project_id,
            CodeEntity.source_id == source.id,
            CodeEntity.file_path.in_(paths),
        ).distinct()
    } if paths else set()
    selected = [path for path in paths if path in indexed_paths][:MAX_DIFF_FILES]
    return {
        "source_id": source.id,
        "base_commit": base_commit,
        "head_commit": head_commit,
        "changed_files": paths[:MAX_DIFF_REPORTED_FILES],
        "changed_file_count": len(paths),
        "indexed_files": selected,
        "unindexed_files": [
            path for path in paths if path not in indexed_paths
        ][:MAX_DIFF_REPORTED_FILES],
        "truncated": (
            output_truncated or len(paths) > MAX_DIFF_REPORTED_FILES
            or len([path for path in paths if path in indexed_paths]) > MAX_DIFF_FILES
        ),
    }


def _safe_diff_path(value: str) -> bool:
    path = PurePosixPath(value.replace("\\", "/"))
    return bool(value) and not path.is_absolute() and ".." not in path.parts and path.as_posix() != "."


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
    impacts = [
        inspect_change_impact(
            db, project_id=project_id, file_path=path, direction=direction, hops=hops, limit=limit
        )
        for path in target["indexed_files"]
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
    return {
        "status": "ok" if nodes else "no_indexed_impact",
        "target": {"kind": "diff", "source_id": target["source_id"], "base_ref": base_ref, "head_ref": head_ref,
                   "base_commit": target["base_commit"], "head_commit": target["head_commit"],
                   "changed_files": target["changed_files"], "indexed_files": target["indexed_files"],
                   "unindexed_files": target["unindexed_files"], "changed_file_count": target["changed_file_count"],
                   "entity_ids": [entity_id for impact in impacts for entity_id in impact.get("target", {}).get("entity_ids", [])]},
        "direction": direction, "hops": hops,
        "nodes": list(nodes.values())[:limit], "edges": list(edges.values())[:limit],
        "unknown_edges": list(unknown_edges.values())[:limit],
        "truncated": target["truncated"] or len(nodes) > limit or len(edges) > limit
        or len(unknown_edges) > limit or any(impact.get("truncated") for impact in impacts),
        "impact_summary": {"limitations": [
            "The diff is read from the local synced Git worktree; it can only include revisions available there.",
            "Only changed files with indexed code entities are analyzed. Deleted, renamed-only, unindexed and non-code files are listed but have no code impact graph.",
        ]},
    }


def inspect_change_package(
    db: Session,
    *,
    project_id: int,
    entity_id: int | None = None,
    file_path: str | None = None,
    source_id: int | None = None,
    base_ref: str | None = None,
    head_ref: str | None = None,
    direction: str = "incoming",
    hops: int = 2,
    limit: int = 40,
) -> dict:
    """Combine O-196 impact results with approved linked records and bounded evidence."""
    diff_requested = base_ref is not None or head_ref is not None
    if diff_requested:
        if entity_id is not None or file_path is not None:
            return {"error": "Diff analysis cannot be combined with entity_id or file_path."}
        if not base_ref or not head_ref:
            return {"error": "Diff analysis requires both base_ref and head_ref."}
        impact = _diff_impact(
            db, project_id=project_id, source_id=source_id, base_ref=base_ref, head_ref=head_ref,
            direction=direction, hops=hops, limit=limit,
        )
    else:
        if source_id is not None:
            return {"error": "source_id is only valid together with base_ref and head_ref."}
        impact = inspect_change_impact(
            db,
            project_id=project_id,
            entity_id=entity_id,
            file_path=file_path,
            direction=direction,
            hops=hops,
            limit=limit,
        )
    if impact.get("error"):
        return impact

    nodes = impact.get("nodes", [])
    node_ids = {node["id"] for node in nodes if isinstance(node, dict) and isinstance(node.get("id"), int)}
    linked_documents, documents_truncated = _linked_documents(db, project_id, node_ids)
    linked_knowledge, issue_history = _classify_knowledge(linked_documents)
    tests = _test_evidence(db, project_id, node_ids)
    ownership = _ownership(db, project_id, nodes)
    relationship_paths = _relationship_paths(impact)
    for record in linked_knowledge:
        record["relationship_path_entity_id"] = record.get("entity_id")
        record["relationship_path_available"] = record.get("entity_id") in relationship_paths
    for record in issue_history:
        record["relationship_path_entity_id"] = record.get("entity_id")
        record["relationship_path_available"] = record.get("entity_id") in relationship_paths

    explained_nodes = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        relationship_path = relationship_paths.get(node.get("id"))
        unknown_candidates = [
            edge
            for edge in impact.get("unknown_edges", [])
            if edge.get("source_entity_id") == node.get("id")
        ]
        explained_nodes.append({
            **node,
            "relationship_path": relationship_path,
            "evidence": {
                "kind": "indexed_code_entity" if relationship_path else "unresolved_dynamic_name_match" if unknown_candidates else "indexed_target",
                "file_path": node.get("file_path"),
                "start_line": node.get("start_line"),
                "end_line": node.get("end_line"),
                "unresolved_candidates": [
                    {
                        "edge_id": edge.get("id"),
                        "relationship": edge.get("type"),
                        "target_name": edge.get("target_name"),
                        "resolution": edge.get("resolution"),
                        "start_line": edge.get("start_line"),
                    }
                    for edge in unknown_candidates[:5]
                ],
            },
        })

    gaps = [
        "No versioned, reviewed domain-rule objects are available yet; possible rule labels are keyword-based linked-document candidates."
    ]
    if not linked_knowledge:
        gaps.append("No approved code-to-document links were found for the returned code objects; pending semantic suggestions are excluded.")
    if not issue_history:
        gaps.append("No linked Jira history was found. Earlier bugs may exist outside the indexed or approved linked records.")
    if tests["status"] == "unknown":
        gaps.append("Test mapping is unknown. The result does not establish test coverage or the absence of tests.")
    if ownership["status"] == "unknown":
        gaps.append("No CODEOWNERS assignment could be established for the impacted files.")
    elif ownership["partial"] or ownership["unknown_files"]:
        gaps.append("Some CODEOWNERS patterns or impacted files could not be resolved by the bounded matcher.")
    if tests.get("truncated"):
        gaps.append("The linked test/spec list was truncated at its relationship limit.")
    if documents_truncated:
        gaps.append("Linked documentation was truncated at the package relationship limit.")
    gaps.extend(impact.get("impact_summary", {}).get("limitations", []))

    return {
        "schema_version": 1,
        "status": "ok",
        "impact_status": impact.get("status", "no_indexed_impact"),
        "target": impact.get("target"),
        "scope": {
            "input_mode": "diff" if diff_requested else "entity_or_file",
            "direction": impact.get("direction"),
            "hops": impact.get("hops"),
            "truncated": impact.get("truncated", False),
            "limits": {"max_hops": 3, "max_nodes": 80, "max_linked_records": MAX_PACKAGE_LINKS},
        },
        "change_impact": impact,
        "affected_code": explained_nodes,
        "linked_knowledge": linked_knowledge,
        "historical_issues": issue_history,
        "tests": tests,
        "responsibility": ownership,
        "evidence_gaps": list(dict.fromkeys(gaps)),
        "limitations": [
            "This is a bounded read-only package based on the current index and approved links; it is not a complete impact analysis.",
            "Domain-rule labels and Jira bug candidates use visible title/excerpt keywords and require human review.",
            "KnowledgeLink and EntityDocLink records are supporting references, not a versioned approved-knowledge lifecycle.",
            "Tests are listed only when an indexed statically resolved relationship points from a test/spec path; coverage is never inferred.",
        ],
    }
