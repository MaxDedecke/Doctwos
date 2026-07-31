"""
backend/core/auth_dependency.py
================================
Eigene, signierte Session-Cookie (statt das IdP-Token direkt an die SPA
durchzureichen) — entkoppelt die App-Session-Lebensdauer vom IdP-Token und
hält den IdP-Token aus dem Browser-JS heraus.
"""

import logging

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

import core.config as cfg
from core.db_setup import get_db
from models.database import User

SESSION_COOKIE_NAME = "doctus_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 14  # 14 Tage

_serializer = URLSafeTimedSerializer(cfg.SESSION_SECRET_KEY, salt="doctus-session")


def create_session_cookie_value(user_id: int) -> str:
    return _serializer.dumps({"user_id": user_id})


logger = logging.getLogger(__name__)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie_value:
        logger.warning("401 – kein '%s' Cookie. Alle Cookies: %s", SESSION_COOKIE_NAME, list(request.cookies.keys()))
        raise HTTPException(status_code=401, detail="Nicht angemeldet")

    try:
        payload = _serializer.loads(cookie_value, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired) as exc:
        logger.warning("401 – Cookie-Signatur ungültig/abgelaufen: %s", exc)
        raise HTTPException(status_code=401, detail="Session ungültig oder abgelaufen")

    user = db.query(User).filter(User.id == payload["user_id"]).first()
    if not user:
        logger.warning("401 – user_id %s nicht in DB", payload.get("user_id"))
        raise HTTPException(status_code=401, detail="Nutzer nicht gefunden")
    return user
