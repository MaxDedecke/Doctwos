"""Personal MCP tokens, managed through the regular browser session."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth_dependency import get_current_user
from core.db_setup import get_db
from models.database import MCPAccessToken, User
from services.mcp_tokens import create_token, public_token


router = APIRouter(prefix="/mcp-tokens", tags=["mcp-tokens"])


class NewToken(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expires_in_days: int = Field(default=30, ge=1, le=90)


@router.get("")
def list_tokens(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    response.headers["Cache-Control"] = "no-store"
    rows = (
        db.query(MCPAccessToken)
        .filter(MCPAccessToken.user_id == user.id)
        .order_by(MCPAccessToken.created_at.desc(), MCPAccessToken.id.desc())
        .limit(100)
        .all()
    )
    return [public_token(row) for row in rows]


@router.post("", status_code=201)
def issue_token(
    payload: NewToken,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="Passwortwechsel erforderlich")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name erforderlich")
    active_count = (
        db.query(MCPAccessToken)
        .filter(
            MCPAccessToken.user_id == user.id,
            MCPAccessToken.revoked_at.is_(None),
            MCPAccessToken.expires_at > datetime.now(timezone.utc),
        )
        .count()
    )
    if active_count >= 20:
        raise HTTPException(status_code=409, detail="Maximal 20 aktive MCP-Tokens pro Nutzer")
    row, secret = create_token(db, user=user, name=name, days=payload.expires_in_days)
    response.headers["Cache-Control"] = "no-store"
    return {**public_token(row), "token": secret}


@router.delete("/{token_id}", status_code=204)
def revoke_token(
    token_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (
        db.query(MCPAccessToken)
        .filter(MCPAccessToken.id == token_id, MCPAccessToken.user_id == user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Token nicht gefunden")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        db.commit()
