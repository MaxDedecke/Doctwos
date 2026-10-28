"""Bounded retrieval of approved project insights, with provenance snapshots."""

import json
import re
from xml.sax.saxutils import escape

from sqlalchemy import or_

from core.projects import assert_project_visible
from models.database import Insight


def retrieve_insight_context(db, user, project_id, message, sources=None):
    if project_id is None:
        return ""
    assert_project_visible(project_id, user, db)
    terms = list(dict.fromkeys(re.findall(r"[^\W_]{4,}", message.lower())))[:12]
    if not terms:
        return ""
    matches = (
        db.query(Insight)
        .filter(
            Insight.project_id == project_id,
            Insight.status == "verified",
            Insight.outdated_at.is_(None),
            or_(
                *(
                    or_(Insight.title.ilike(f"%{term}%"), Insight.content.ilike(f"%{term}%"))
                    for term in terms
                )
            ),
        )
        .order_by(Insight.verified_at.desc(), Insight.id.desc())
        .limit(5)
        .all()
    )
    budget = 8000
    parts = []
    for insight in matches:
        if not insight.evidence_json:
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
    by_id = {source["insight_id"]: source for source in candidates}
    seen = set()
    result = []
    for match in re.finditer(r"\[(?:Insight|Erkenntnis):([0-9]+)\]", scan, re.IGNORECASE):
        insight_id = int(match.group(1))
        if insight_id in by_id and insight_id not in seen:
            seen.add(insight_id)
            result.append(dict(by_id[insight_id]))
    return result
