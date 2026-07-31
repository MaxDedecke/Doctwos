"""
backend/api/users.py
====================
Nutzerverwaltung für Administratoren (F-004): anlegen, deaktivieren, Rolle
ändern, Passwort zurücksetzen, Sperre aufheben.

Alles hier ist `superuser`-only (Router-weite `require_admin`-Dependency).
Gelöscht wird nie — ein Nutzer hängt an Chatverläufen, Projekt- und
Teammitgliedschaften; `is_active=False` ist die Deaktivierung, die den Login
sperrt und die Historie erhält.

Ein neu vergebenes Passwort wird genau einmal in der Antwort zurückgegeben und
nirgends gespeichert oder geloggt (F-005). Der Passwort-Hash verlässt diesen
Router nie — der CI-Job `no-password-leak` prüft das.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.db_setup import get_db
from core.passwords import MIN_PASSWORD_LENGTH
from core.teams import require_admin
from core.users import create_local_user, set_password, unlock
from models.database import User

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])

Role = Literal["superuser", "user"]


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    name: Optional[str] = None
    email: Optional[str] = None
    role: Role = "user"
    # Ohne Angabe wird eines generiert — der übliche Weg, damit der Administrator
    # kein Passwort erfindet, das er anschließend per Mail verschickt.
    password: Optional[str] = Field(default=None, min_length=MIN_PASSWORD_LENGTH)


class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[Role] = None
    is_active: Optional[bool] = None


class ResetPasswordRequest(BaseModel):
    password: Optional[str] = Field(default=None, min_length=MIN_PASSWORD_LENGTH)


def _serialize(u: User) -> dict:
    locked_until = u.locked_until
    if locked_until is not None and locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "name": u.name,
        "role": u.role,
        "is_active": u.is_active,
        "must_change_password": bool(u.must_change_password),
        "failed_login_count": u.failed_login_count or 0,
        "locked_until": locked_until,
        "is_locked": bool(locked_until and locked_until > datetime.now(timezone.utc)),
        "last_login_at": u.last_login_at,
    }


def _get_user(user_id: int, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Nutzer nicht gefunden.")
    return user


def _assert_not_last_superuser(target: User, db: Session) -> None:
    """Verhindert, dass sich die Installation selbst aussperrt: die letzte aktive
    Superuser-Zeile darf weder deaktiviert noch zurückgestuft werden."""
    if target.role != "superuser" or not target.is_active:
        return
    remaining = (
        db.query(User)
        .filter(User.role == "superuser", User.is_active.is_(True), User.id != target.id)
        .count()
    )
    if remaining == 0:
        raise HTTPException(
            status_code=400,
            detail="Der letzte aktive Administrator kann weder deaktiviert noch zurückgestuft werden.",
        )


@router.get("")
def list_users(db: Session = Depends(get_db)):
    """Nutzerliste. Der Passwort-Hash wird hier bewusst NICHT serialisiert (F-005) —
    ein CI-Job prüft, dass das Feld in keinem Serializer auftaucht."""
    users = db.query(User).order_by(User.username).all()
    return [_serialize(u) for u in users]


@router.post("", status_code=201)
def create_user(payload: CreateUserRequest, db: Session = Depends(get_db)):
    username = payload.username.strip()
    if db.query(User).filter(User.username == username).first() is not None:
        raise HTTPException(status_code=409, detail="Dieser Benutzername ist bereits vergeben.")

    user, password = create_local_user(
        db,
        username=username,
        password=payload.password,
        name=(payload.name or None),
        email=(payload.email or None),
        role=payload.role,
    )

    # Einmalige Ausgabe: ab hier existiert das Klartextpasswort nur noch im Browser
    # des Administrators.
    return {**_serialize(user), "initial_password": password}


@router.patch("/{user_id}")
def update_user(user_id: int, payload: UpdateUserRequest, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = _get_user(user_id, db)

    if payload.is_active is False or (payload.role is not None and payload.role != "superuser"):
        if user.id == admin.id:
            raise HTTPException(
                status_code=400,
                detail="Das eigene Konto kann nicht deaktiviert oder zurückgestuft werden.",
            )
        _assert_not_last_superuser(user, db)

    if payload.name is not None:
        user.name = payload.name or None
    if payload.email is not None:
        user.email = payload.email or None
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
        # Reaktivieren hebt eine noch laufende Sperre mit auf — sonst wäre der
        # Nutzer formal aktiv und käme trotzdem nicht herein.
        if payload.is_active:
            user.failed_login_count = 0
            user.locked_until = None

    db.commit()
    db.refresh(user)
    return _serialize(user)


@router.post("/{user_id}/reset-password")
def reset_password(user_id: int, payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = _get_user(user_id, db)
    password = set_password(db, user, payload.password)
    return {**_serialize(user), "initial_password": password}


@router.post("/{user_id}/unlock")
def unlock_user(user_id: int, db: Session = Depends(get_db)):
    """Hebt die DB-Sperre auf. Der Redis-Zähler pro (Name, IP) läuft davon
    unberührt ab (Fenster: 15 Minuten) — er kennt keine Nutzer-ID."""
    user = _get_user(user_id, db)
    unlock(db, user)
    return _serialize(user)
