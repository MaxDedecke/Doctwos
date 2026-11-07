"""Version scopes for reviewed findings, shared by API, retrieval and workers."""

import hashlib
import json

from sqlalchemy import or_

from .database import CodeEdge, CodeEntity, Insight, KnowledgeSource, SourceScanFile


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def capture_versions(
    db, project_id, evidence, *, dependencies=False, strict=False, _seen=frozenset(), _budget=None
):
    """Capture current source identity without inventing versions for legacy evidence."""
    budget = [200] if _budget is None else _budget
    grouped = {}
    references = {}
    for item in evidence:
        budget[0] -= 1
        if budget[0] < 0:
            if strict:
                raise ValueError("Erkenntnisbelege überschreiten das Prüflimit")
            return []
        reference_id = item.get("insight_id")
        if reference_id is not None:
            if reference_id in _seen or len(_seen) >= 4:
                if strict:
                    raise ValueError("Zyklische oder zu tiefe Erkenntnisbelege")
                continue
            reference = db.query(Insight).filter_by(id=reference_id, project_id=project_id).first()
            if reference is None:
                if strict:
                    raise ValueError("Referenzierte Erkenntnis fehlt")
                continue
            child_versions = capture_versions(
                db,
                project_id,
                reference.evidence_json,
                strict=strict,
                _seen=_seen | {reference_id},
                _budget=budget,
            )
            if budget[0] < 0:
                return []
            if strict and (
                reference.status != "verified"
                or (
                    child_versions
                    and (
                        reference.version_bindings is None
                        or not versions_match(reference.version_bindings, child_versions)
                    )
                )
            ):
                raise ValueError(
                    "Referenzierte Erkenntnis muss zuerst für den aktuellen Stand freigegeben werden"
                )
            references[str(reference_id)] = reference.revision
            for version in child_versions:
                grouped.setdefault(version["source_id"], set()).update(version["files"])

        source_id = item.get("source_id")
        path = item.get("file")
        if source_id is None and item.get("entity_id") is not None:
            entity = (
                db.query(CodeEntity).filter_by(id=item["entity_id"], project_id=project_id).first()
            )
            if entity is not None:
                source_id, path = entity.source_id, entity.file_path
        if source_id is None and isinstance(path, str):
            matches = (
                db.query(CodeEntity.source_id)
                .filter(CodeEntity.project_id == project_id, CodeEntity.file_path == path)
                .distinct()
                .limit(2)
                .all()
            )
            if len(matches) == 1:
                source_id = matches[0][0]
        if source_id is not None:
            grouped.setdefault(source_id, set())
            if isinstance(path, str):
                grouped[source_id].add(path)
    result = []
    for source_id, paths in sorted(grouped.items()):
        source = db.query(KnowledgeSource).filter_by(id=source_id, project_id=project_id).first()
        if source is None:
            if strict:
                raise ValueError("Belegquelle fehlt im Projekt")
            continue
        git = (source.type or "").lower() == "git"
        commit = (source.sync_cursor or {}).get("last_commit") if git else None
        if strict and (source.sync_status != "completed" or (git and not commit)):
            raise ValueError("Die Belegquelle benötigt einen vollständig indizierten Stand")
        scans = (
            db.query(SourceScanFile.file_path, SourceScanFile.analysis_fingerprint)
            .filter(SourceScanFile.source_id == source_id, SourceScanFile.file_path.in_(paths))
            .all()
            if paths
            else []
        )
        context = {
            "scope": source.scope_json or {},
            "insight_revisions": references,
            "files": sorted((path, fingerprint) for path, fingerprint in scans),
        }
        document_revision = source.indexed_at or source.last_synced_at
        binding = {
            "source_id": source.id,
            "source_name": source.name,
            "kind": "git" if git else "document",
            "repository": source.repo_fingerprint or _digest(source.url or str(source.id)),
            "branch": source.branch,
            "commit": commit,
            "files": sorted(paths),
            "analysis_context": _digest(context),
            "document_revision": document_revision.isoformat()
            if document_revision and not git
            else None,
        }
        if dependencies and git and paths:
            origin_ids = db.query(CodeEntity.id).filter(
                CodeEntity.project_id == project_id,
                CodeEntity.source_id == source_id,
                CodeEntity.file_path.in_(paths),
            )
            targets = (
                db.query(CodeEntity.file_path)
                .join(CodeEdge, CodeEntity.id == CodeEdge.dst_entity_id)
                .filter(
                    CodeEdge.project_id == project_id,
                    CodeEdge.resolution == "resolved",
                    CodeEdge.src_entity_id.in_(origin_ids),
                    CodeEntity.project_id == project_id,
                    CodeEntity.source_id == source_id,
                    ~CodeEntity.file_path.in_(paths),
                )
                .distinct()
                .order_by(CodeEntity.file_path)
                .limit(101)
                .all()
            )
            binding["dependency_files"] = [path for (path,) in targets[:100]]
            binding["dependencies_truncated"] = len(targets) > 100
        result.append(binding)
    return result


def versions_match(bound, current):
    if any(
        not isinstance(row, dict) or type(row.get("source_id")) is not int
        for row in [*bound, *current]
    ):
        return False
    fields = (
        "source_id",
        "kind",
        "repository",
        "branch",
        "commit",
        "files",
        "analysis_context",
        "document_revision",
    )

    def normalize(rows):
        return [
            {key: row.get(key) for key in fields}
            for row in sorted(rows, key=lambda row: row["source_id"])
        ]

    return normalize(bound) == normalize(current)


def version_state(db, insight, current=None, source_id=None):
    bound = insight.version_bindings
    if bound is None:
        # Existing project-only knowledge retains its behavior in projects
        # without Git sources. Legacy findings in code projects need review.
        has_git = (
            db.query(KnowledgeSource.id)
            .filter(
                KnowledgeSource.project_id == insight.project_id,
                KnowledgeSource.type.ilike("git"),
            )
            .first()
        )
        return "unbound" if has_git else "project"
    if current is None:
        current = capture_versions(db, insight.project_id, insight.evidence_json)
    git_bindings = [row for row in bound if row.get("kind") == "git"]
    if (
        source_id is not None
        and git_bindings
        and source_id not in {row["source_id"] for row in git_bindings}
    ):
        return "other_source"
    source_ids = [row["source_id"] for row in current]
    if (
        source_ids
        and db.query(KnowledgeSource.id)
        .filter(
            KnowledgeSource.id.in_(source_ids),
            or_(KnowledgeSource.sync_status.is_(None), KnowledgeSource.sync_status != "completed"),
        )
        .first()
    ):
        return "index_unavailable"
    if not versions_match(bound, current):
        return "different_version"
    if any(row.get("kind") == "git" and not row.get("commit") for row in current):
        return "unbound"
    if not bound:
        has_git = (
            db.query(KnowledgeSource.id)
            .filter(
                KnowledgeSource.project_id == insight.project_id,
                KnowledgeSource.type.ilike("git"),
            )
            .first()
        )
        return "unbound" if has_git else "project"
    return "current"
