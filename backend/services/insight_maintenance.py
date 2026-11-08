"""Evidence validation and task lifecycle; all writes share the insight transaction."""

from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import cast, func
from sqlalchemy.dialects.postgresql import JSONB
from doctus_models.database import Insight, InsightNotification, CodeEntity, DocumentChunk, CodeEdge
from doctus_models.insight_evidence import snapshot_evidence, project_chunk_scope
from doctus_models.insight_workflow import notify_insight, touched
from services.ci_builds import validate_insight_ci_evidence


def finish_notifications(db, insight):
    db.query(InsightNotification).filter(
        InsightNotification.insight_id == insight.id,
        InsightNotification.read_at.is_(None),
    ).update({"read_at": datetime.now(timezone.utc)}, synchronize_session=False)


def normalize_evidence(db, project_id, evidence):
    result = []
    for raw in evidence:
        item = dict(raw)
        if not item:
            raise HTTPException(status_code=422, detail="Ein Beleg benötigt eine Fundstelle")
        for key in ("entity_id", "chunk_id", "insight_id", "ci_build_id", "edge_id", "source_id"):
            if item.get(key) is not None and (type(item[key]) is not int or item[key] < 1):
                raise HTTPException(
                    status_code=422, detail="Belegkennungen müssen positive Zahlen sein"
                )
        located = False
        for key, model in (
            ("entity_id", CodeEntity),
            ("chunk_id", DocumentChunk),
            ("edge_id", CodeEdge),
            ("insight_id", Insight),
        ):
            if item.get(key) is None:
                continue
            row = (
                db.query(model)
                .filter(
                    model.id == item[key],
                    project_chunk_scope(project_id)
                    if model is DocumentChunk
                    else model.project_id == project_id,
                )
                .first()
            )
            if row is None:
                raise HTTPException(
                    status_code=422, detail="Beleg gehört nicht zum Projekt oder wurde entfernt"
                )
            located = True
            if key == "edge_id":
                row = (
                    db.query(CodeEntity)
                    .filter_by(id=row.src_entity_id, project_id=project_id)
                    .first()
                )
            if key in {"entity_id", "chunk_id", "edge_id"} and row is not None:
                item.update(source_id=row.source_id, file=row.file_path)
        if item.get("ci_build_id") is not None:
            try:
                validate_insight_ci_evidence(db, project_id, [item])
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            located = True
        if item.get("file") and not located:
            query = db.query(DocumentChunk.source_id).filter(
                project_chunk_scope(project_id), DocumentChunk.file_path == item["file"]
            )
            if item.get("source_id") is not None:
                query = query.filter_by(source_id=item["source_id"])
            sources = query.distinct().limit(2).all()
            if len(sources) != 1:
                raise HTTPException(
                    status_code=422, detail="Belegdatei fehlt oder ist ohne Quelle mehrdeutig"
                )
            item["source_id"] = sources[0][0]
            located = True
        if not located:
            raise HTTPException(
                status_code=422, detail="Code, Datei, Erkenntnis oder CI-Lauf als Beleg auswählen"
            )
        lines = item.get("lines")
        if lines is not None:
            if not isinstance(lines, list) or not 1 <= len(lines) <= 2:
                raise HTTPException(status_code=422, detail="Ungültiger Zeilenbereich")
            item["start_line"], item["end_line"] = lines[0], lines[-1]
        start, end = item.get("start_line"), item.get("end_line")
        if any(
            value is not None and (type(value) is not int or value < 1) for value in (start, end)
        ) or (start and end and start > end):
            raise HTTPException(status_code=422, detail="Ungültiger Zeilenbereich")
        if item.get("file") and (start or end):
            last_line = (
                db.query(func.max(DocumentChunk.end_line))
                .filter(
                    project_chunk_scope(project_id),
                    DocumentChunk.source_id == item.get("source_id"),
                    DocumentChunk.file_path == item["file"],
                )
                .scalar()
            )
            if last_line is not None and max(start or 1, end or 1) > last_line:
                raise HTTPException(
                    status_code=422, detail="Zeilenbereich liegt außerhalb der Belegdatei"
                )
        for key in ("file_fingerprint", "source_last_synced_at"):
            item.pop(key, None)
        if item.get("ci_build_id") is None:
            item.pop("source_commit", None)
        result.append(item)
    return snapshot_evidence(db, project_id, result)


def invalidate_dependents(db, insight):
    pending, seen = [insight.id], {insight.id}
    for _ in range(4):
        following = []
        for child in pending:
            parents = (
                db.query(Insight)
                .filter(
                    Insight.project_id == insight.project_id,
                    Insight.status == "verified",
                    cast(Insight.evidence_json, JSONB).contains([{"insight_id": child}]),
                )
                .order_by(Insight.id)
                .with_for_update()
                .yield_per(100)
            )
            for parent in parents:
                if parent.id in seen:
                    continue
                seen.add(parent.id)
                following.append(parent.id)
                parent.status = "outdated"
                parent.revision += 1
                parent.outdated_at = datetime.now(timezone.utc)
                touched(parent)
                notify_insight(db, parent, "dependency_changed")
        pending = following
        if not pending:
            break
