"""Bounded retrieval of approved project insights, with provenance snapshots."""

import json
import re
from xml.sax.saxutils import escape

from sqlalchemy.orm import defer
from sqlalchemy import or_, cast
from sqlalchemy.dialects.postgresql import JSONB

from core.projects import assert_project_visible
from doctus_models.database import Insight, CodeEntity
from doctus_models.insight_versions import version_state


def related_insights(db, project_id, nodes, limit=40):
    """Match actual evidence locators within the project, including stale findings."""
    selectors = []
    evidence = cast(Insight.evidence_json, JSONB)
    for node in nodes:
        if node.get("id") is not None:
            selectors.append(evidence.contains([{"entity_id": node["id"]}]))
        if node.get("file_path") and node.get("source_id") is not None:
            selectors.append(
                evidence.contains([{"file": node["file_path"], "source_id": node["source_id"]}])
            )
    if not selectors:
        return []
    return (
        db.query(Insight)
        .options(defer(Insight.review_history), defer(Insight.workflow_history))
        .filter(Insight.project_id == project_id, or_(*selectors))
        .order_by(Insight.id.desc())
        .limit(limit)
        .all()
    )


def current_insights(
    db,
    user,
    project_id,
    message,
    source_id=None,
    nodes=None,
    limit=5,
    *,
    query_embedding=None,
    profile_key=None,
):
    if project_id is None:
        return []
    assert_project_visible(project_id, user, db)
    terms = list(dict.fromkeys(re.findall(r"[^\W_]{4,}", message.lower())))[:12]
    if not terms and not nodes:
        return []
    from services.insight_relevance import ranked_candidates

    matches = ranked_candidates(
        db, project_id, message, query_embedding=query_embedding, profile_key=profile_key
    )
    # A class or file named in the question can retrieve a finding whose prose
    # uses different words, through its evidence locator.
    entities = (
        db.query(CodeEntity)
        .filter(
            CodeEntity.project_id == project_id,
            or_(False, *(CodeEntity.qualified_name.ilike(f"%{term}%") for term in terms)),
        )
        .order_by(CodeEntity.id)
        .limit(20)
        .all()
    )
    related = related_insights(
        db,
        project_id,
        [
            *(nodes or []),
            *[{"id": e.id, "file_path": e.file_path, "source_id": e.source_id} for e in entities],
        ],
        limit=20,
    )
    eligible = [
        i for i in related if i.status == "verified" and getattr(i, "outdated_at", None) is None
    ]
    matches = list({i.id: i for i in [*eligible, *matches]}.values())
    return [
        i
        for i in matches
        if i.status == "verified"
        and getattr(i, "outdated_at", None) is None
        and i.evidence_json
        and version_state(db, i, source_id=source_id) in {"current", "project"}
    ][:limit]


def retrieve_insight_context(db, user, project_id, message, sources=None, source_id=None):
    matches = current_insights(db, user, project_id, message, source_id)
    budget = 8000
    parts = []
    for insight in matches:
        if not insight.evidence_json or version_state(db, insight, source_id=source_id) not in {
            "current",
            "project",
        }:
            continue
        citation = f"[Insight:{insight.id}]"
        payload = escape(
            json.dumps(
                {
                    "insight_id": insight.id,
                    "citation": citation,
                    "title": insight.title,
                    "content": insight.content,
                    "status": insight.status,
                    "version_bindings": insight.version_bindings,
                    "evidence": insight.evidence_json,
                },
                ensure_ascii=False,
            )
        )
        if len(payload) > budget:
            continue
        parts.append(payload)
        budget -= len(payload)
        if sources is not None:
            sources.append(
                {
                    "kind": "insight",
                    "file": f"insight:{insight.id}",
                    "lines": [],
                    "source_id": None,
                    "insight_id": insight.id,
                    "project_id": project_id,
                    "title": insight.title,
                    "content": insight.content,
                    "evidence": insight.evidence_json,
                    "status": insight.status,
                    "version_bindings": insight.version_bindings,
                }
            )
    if not parts:
        return ""
    return (
        "\nApproved project insights (human-reviewed claims, not independent code evidence). "
        "Use only when relevant. When using an insight, cite its exact citation marker "
        "(for example [Insight:10]) in your answer. Cite underlying evidence separately only "
        "if available in source context.\n"
        "<untrusted_insights>\n" + "\n".join(parts) + "\n</untrusted_insights>\n"
    )


def resolve_insight_sources(answer, candidates):
    """Only retrieved insight IDs explicitly cited outside code fences are sources."""
    scan = re.sub(r"```.*?```|~~~.*?~~~", " ", answer, flags=re.DOTALL)
    by_id = {
        source["insight_id"]: source
        for source in candidates
        if source.get("insight_id") is not None
    }
    seen = set()
    result = []
    for match in re.finditer(r"\[(?:Insight|Erkenntnis):([0-9]+)\]", scan, re.IGNORECASE):
        insight_id = int(match.group(1))
        if insight_id in by_id and insight_id not in seen:
            seen.add(insight_id)
            result.append(dict(by_id[insight_id]))
    return result


def related_insight_records(db, project_id, nodes):
    from services.reviewed_evidence import insight_record

    return [insight_record(db, i) for i in related_insights(db, project_id, nodes)]
