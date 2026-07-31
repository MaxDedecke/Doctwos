"""
backend/api/auth.py
====================
Lokale Anmeldung gegen die eigene users-Tabelle (F-001) — kein IdP, kein
Netzzugang, keine Fremdkomponente im Betriebshandbuch.

    POST /auth/login            — Benutzername/Passwort, setzt die Session-Cookie
    POST /auth/logout           — Löscht die Session-Cookie
    POST /auth/change-password  — Passwortwechsel (erzwungen bei must_change_password)
    GET  /auth/me               — Aktueller Nutzer (401 wenn nicht angemeldet)

Die Session-Schicht darunter (signierte HTTP-only-Cookie, 14 Tage) ist unverändert
die des Templates — nur der Weg, wie ein Nutzer zu einer Session kommt, ist neu.

Kapselung für v2: Es gibt genau einen User-Provisioning-Pfad. Ein späterer
IdP-Anschluss ergänzt hier einen zweiten Zweig und ERGÄNZT die lokale
users-Tabelle, statt sie zu ersetzen.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import core.config as cfg
from core.auth_dependency import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    create_session_cookie_value,
    get_current_user,
)
from core.db_setup import get_db
from core.passwords import hash_password, needs_rehash, verify_password
from models.database import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=12)


def _set_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_cookie_value(user_id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        # Aus FRONTEND_URL abgeleitet statt hart True: Browser verwerfen Secure-Cookies
        # über plain HTTP, was lokale/CI-Setups still brechen würde. Sobald FRONTEND_URL
        # https:// ist, zieht die Cookie sich ohne eigene Konfiguration selbst an.
        secure=cfg.FRONTEND_URL.startswith("https://"),
    )


@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == payload.username).first()

    # Bewusst dieselbe Meldung für "Nutzer unbekannt" und "Passwort falsch":
    # sonst ist die Existenz eines Kontos über die Fehlermeldung abfragbar.
    invalid = HTTPException(status_code=401, detail="Benutzername oder Passwort ist falsch.")

    if user is None:
        # Dummy-Verify gegen Timing-Unterscheidung zwischen unbekanntem Nutzer
        # (kein Hash-Vergleich) und falschem Passwort (teurer Argon2-Vergleich).
        verify_password("", "$argon2id$v=19$m=65536,t=3,p=4$" + "A" * 22 + "$" + "B" * 43)
        raise invalid

    now = datetime.now(timezone.utc)
    locked_until = user.locked_until
    if locked_until is not None:
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            raise HTTPException(
                status_code=423,
                detail="Konto ist vorübergehend gesperrt. Bitte später erneut versuchen.",
            )

    if not user.is_active:
        raise invalid

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        db.commit()
        raise invalid

    # Argon2-Parameter können sich mit einer neuen Bibliotheksversion ändern —
    # dann beim nächsten erfolgreichen Login transparent neu hashen.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()

    _set_session_cookie(response, user.id)
    return {"must_change_password": bool(user.must_change_password)}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"status": "ok"}


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Das aktuelle Passwort ist falsch.")
    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=400, detail="Das neue Passwort muss sich vom alten unterscheiden.")

    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    db.commit()
    return {"status": "ok"}


@router.get("/me")
async def me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from core.teams import is_admin

    user_teams = []
    # User.team_memberships is populated via backref on TeamMembership model
    for m in user.team_memberships:
        if m.team:
            user_teams.append({"id": m.team.id, "name": m.team.name})
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "is_admin": is_admin(user),
        "must_change_password": bool(user.must_change_password),
        "teams": user_teams,
    }
