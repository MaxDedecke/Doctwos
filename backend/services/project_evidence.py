"""Select the same version-bound project evidence for chat and MCP."""

import json
import re
from xml.sax.saxutils import escape

from core.projects import assert_project_visible, assert_knowledge_source_visible
from doctus_models.database import CodeEntity, KnowledgeSource
from services.ci_builds import matching_builds
from services.insight_context import current_insights
from services.reviewed_evidence import (
    NOTICE,
    compact_builds,
    compact_insights,
    fit_result,
    insight_record,
    record_sources,
)


def project_evidence(db, user, project_id, question, *, nodes=None, source_id=None, max_chars=6000):
    if project_id is None:
        return {"insights": [], "ci_builds": {"status": "missing", "items": [], "truncated": False}}
    assert_project_visible(project_id, user, db)
    if source_id is not None:
        source = db.query(KnowledgeSource).filter_by(id=source_id, project_id=project_id).first()
        if source is None:
            raise ValueError("Source does not belong to this project")
        assert_knowledge_source_visible(source, user, db)
    nodes = list(nodes or [])
    insights = current_insights(db, user, project_id, question, source_id, nodes, limit=6)
    source_ids = {node.get("source_id") for node in nodes if node.get("source_id") is not None}
    source_ids.update(
        binding["source_id"] for insight in insights for binding in insight.version_bindings or []
    )
    if not source_ids and source_id is None:
        # No code entity was resolved by the caller (e.g. a build-status question).
        terms = list(dict.fromkeys(re.findall(r"[^\W_]{4,}", question.lower())))[:12]
        if terms:
            from sqlalchemy import or_

            source_ids.update(
                row[0]
                for row in db.query(CodeEntity.source_id)
                .filter(
                    CodeEntity.project_id == project_id,
                    or_(*(CodeEntity.qualified_name.ilike(f"%{term}%") for term in terms)),
                )
                .distinct()
                .limit(20)
                .all()
                if row[0] is not None
            )
        if not source_ids and re.search(
            r"\b(ci|maven|build|pipeline|tests?|testergebnis\w*)\b", question, re.I
        ):
            source_ids.update(
                row.id
                for row in db.query(KnowledgeSource)
                .filter(
                    KnowledgeSource.project_id == project_id,
                    KnowledgeSource.type.ilike("git"),
                )
                .order_by(KnowledgeSource.id)
                .limit(21)
                .all()
            )
    if source_id is not None:
        source_ids = {source_id}
    scoped_sources = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.project_id == project_id,
            KnowledgeSource.id.in_(source_ids),
        )
        .order_by(KnowledgeSource.id)
        .limit(21)
        .all()
        if source_ids
        else []
    )
    # Project/source ACLs remain authoritative for all supplemental evidence.
    for source in scoped_sources:
        assert_knowledge_source_visible(source, user, db)
    builds = matching_builds(
        db,
        project_id,
        {},
        [{"source_id": source.id} for source in scoped_sources[:20]],
    )
    builds["truncated"] = builds["truncated"] or len(scoped_sources) > 20
    records = [insight_record(db, item) for item in insights]
    return fit_result(
        {
            "insights": compact_insights(records),
            "insights_truncated": len(records) > 5,
            "ci_builds": compact_builds(builds),
            "project_evidence_notice": NOTICE,
        },
        max_chars,
    )


def project_evidence_prompt(db, user, project_id, question, *, sources, source_id=None):
    result = project_evidence(db, user, project_id, question, source_id=source_id)
    if not result.get("insights") and not result.get("ci_builds", {}).get("items"):
        if not re.search(r"\b(ci|maven|build|pipeline|tests?|testergebnis\w*)\b", question, re.I):
            return ""
    encoded = escape(json.dumps(result, ensure_ascii=False))
    while len(encoded) > 7400:
        result = fit_result(result, len(json.dumps(result, ensure_ascii=False)) - 250)
        encoded = escape(json.dumps(result, ensure_ascii=False))
    sources.extend(record_sources(project_id, result))
    return (
        "\n"
        + NOTICE
        + "\n<untrusted_project_evidence>\n"
        + encoded
        + "\n</untrusted_project_evidence>\n"
    )


def augment_answer_context(db, user, project_id, question, result, max_chars):
    nodes = [
        entry["entity"]
        for entry in result.get("evidence", [])
        if isinstance(entry.get("entity"), dict)
    ]
    extra = project_evidence(db, user, project_id, question, nodes=nodes, max_chars=max_chars // 2)
    return fit_result({**result, **extra}, max_chars)
