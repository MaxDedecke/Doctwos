"""Source-scoped CI upload credentials, independent of personal MCP access."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from core.db_setup import get_db
from core.projects import get_project_role
from doctus_models.database import CIBuildToken, User
from services.ci_builds import repository_identity

PREFIX = "dct_ci_"


def public_token(row):
    return {
        "id": row.id,
        "name": row.name,
        "source_id": row.source_id,
        "prefix": row.token_prefix,
        "created_at": row.created_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }


def issue_token(db, user, source, name, days):
    secret = PREFIX + secrets.token_urlsafe(32)
    row = CIBuildToken(
        project_id=source.project_id,
        source_id=source.id,
        user_id=user.id,
        name=name,
        token_hash=hashlib.sha256(secret.encode()).hexdigest(),
        token_prefix=secret[:16],
        repository=repository_identity(source),
        branch=source.branch,
        expires_at=datetime.now(timezone.utc) + timedelta(days=days),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {**public_token(row), "token": secret}


def validate_token(db, row):
    expires = (
        row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    )
    if row.revoked_at or expires <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="CI token expired or revoked")
    user = db.query(User).filter_by(id=row.user_id, is_active=True).first()
    if not user or get_project_role(row.project_id, user, db) != "admin":
        raise HTTPException(
            status_code=403, detail="CI token owner no longer has project admin access"
        )


def require_ci_token(request: Request, db: Session = Depends(get_db)):
    parts = request.headers.get("Authorization", "").split()
    if (
        len(parts) != 2
        or parts[0].lower() != "bearer"
        or not parts[1].startswith(PREFIX)
        or len(parts[1]) > 128
    ):
        raise HTTPException(status_code=401, detail="CI bearer token required")
    row = (
        db.query(CIBuildToken)
        .filter_by(token_hash=hashlib.sha256(parts[1].encode()).hexdigest())
        .first()
    )
    if not row:
        raise HTTPException(status_code=401, detail="Invalid CI token")
    validate_token(db, row)
    return row
