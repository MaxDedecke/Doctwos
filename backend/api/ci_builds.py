"""CI report ingestion and browser-managed source credentials."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from core.auth_dependency import get_current_user
from core.db_setup import get_db
from core.projects import assert_project_visible, get_project_role
from doctus_models.database import CIBuildToken, KnowledgeSource, User
from services.ci_builds import CIBuildUpload, store_upload
from services.ci_tokens import issue_token, public_token, require_ci_token, validate_token

router = APIRouter(tags=["ci-builds"])


class NewCIToken(BaseModel):
    source_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=100)
    expires_in_days: int = Field(default=90, ge=1, le=365)


def _require_admin(db, user, project_id):
    assert_project_visible(project_id, user, db)
    if get_project_role(project_id, user, db) != "admin":
        raise HTTPException(status_code=403, detail="Projekt-Admin erforderlich")


@router.get("/projects/{project_id}/ci-tokens")
def list_ci_tokens(
    project_id: int,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_project_visible(project_id, user, db)
    response.headers["Cache-Control"] = "no-store"
    can_manage = get_project_role(project_id, user, db) == "admin"
    sources = (
        db.query(KnowledgeSource)
        .filter(KnowledgeSource.project_id == project_id, KnowledgeSource.type.ilike("git"))
        .order_by(KnowledgeSource.id)
        .all()
    )
    tokens = (
        db.query(CIBuildToken)
        .filter_by(project_id=project_id)
        .order_by(CIBuildToken.id.desc())
        .limit(100)
        .all()
        if can_manage
        else []
    )
    return {
        "can_manage": can_manage,
        "sources": [{"id": s.id, "name": s.name, "branch": s.branch} for s in sources],
        "tokens": [public_token(row) for row in tokens],
    }


@router.post("/projects/{project_id}/ci-tokens", status_code=201)
def create_ci_token(
    project_id: int,
    body: NewCIToken,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(db, user, project_id)
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="Passwortwechsel erforderlich")
    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id == body.source_id,
            KnowledgeSource.project_id == project_id,
            KnowledgeSource.type.ilike("git"),
        )
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Git-Quelle nicht gefunden")
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Name erforderlich")
    response.headers["Cache-Control"] = "no-store"
    return issue_token(db, user, source, body.name.strip(), body.expires_in_days)


@router.delete("/projects/{project_id}/ci-tokens/{token_id}", status_code=204)
def revoke_ci_token(
    project_id: int,
    token_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(db, user, project_id)
    row = (
        db.query(CIBuildToken)
        .filter_by(id=token_id, project_id=project_id)
        .with_for_update()
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="CI token not found")
    row.revoked_at = row.revoked_at or datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)


def _store(db, token, body):
    db.refresh(token, with_for_update=True)
    validate_token(db, token)
    try:
        result, duplicate = store_upload(db, token, body)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(
        {"build": result, "duplicate": duplicate}, status_code=200 if duplicate else 201
    )


@router.post("/ci/builds")
async def ingest_ci_build(
    request: Request, db: Session = Depends(get_db), token: CIBuildToken = Depends(require_ci_token)
):
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 8_000_000:
            raise HTTPException(status_code=413, detail="CI report exceeds 8 MB")
    try:
        body = CIBuildUpload.model_validate_json(bytes(payload))
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()],
        ) from exc
    return await run_in_threadpool(_store, db, token, body)
