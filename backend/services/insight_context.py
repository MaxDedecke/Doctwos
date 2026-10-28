"""Bounded retrieval of approved project insights, with provenance snapshots."""

import json
import re
from xml.sax.saxutils import escape

from sqlalchemy import or_

from core.projects import assert_project_visible
from models.database import Insight


def retrieve_insight_context(db, user, project_id, message):
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
        payload = json.dumps(
            {
                "insight_id": insight.id,
                "title": insight.title,
                "content": insight.content,
                "status": insight.status,
                "evidence": insight.evidence_json,
            },
            ensure_ascii=False,
        )
        if len(payload) > budget:
            continue
        parts.append(escape(payload))
        budget -= len(payload)
    if not parts:
        return ""
    return (
        "\nApproved project insights (human-reviewed claims, not independent code evidence). "
        "Use only when relevant; cite their underlying evidence only if available in source context.\n"
        "<untrusted_insights>\n" + "\n".join(parts) + "\n</untrusted_insights>\n"
    )
