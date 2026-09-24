"""Lifecycle and validation of personal MCP bearer tokens."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models.database import MCPAccessToken, User


TOKEN_PREFIX = "dct_mcp_"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def create_token(db: Session, *, user: User, name: str, days: int) -> tuple[MCPAccessToken, str]:
    secret = TOKEN_PREFIX + secrets.token_urlsafe(32)
    row = MCPAccessToken(
        user_id=user.id,
        name=name,
        token_hash=hashlib.sha256(secret.encode("ascii")).hexdigest(),
        token_prefix=secret[:16],
        expires_at=_now() + timedelta(days=days),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, secret


def find_token_user(db: Session, secret: str) -> User | None:
    if not secret.startswith(TOKEN_PREFIX) or len(secret) > 128:
        return None
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    row = db.query(MCPAccessToken).filter(MCPAccessToken.token_hash == digest).first()
    if not row or row.revoked_at or _utc(row.expires_at) <= _now():
        return None
    user = db.query(User).filter(User.id == row.user_id, User.is_active.is_(True)).first()
    return user


def public_token(row: MCPAccessToken) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "prefix": row.token_prefix,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "revoked_at": row.revoked_at,
    }
