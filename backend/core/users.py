"""
backend/core/users.py
=====================
Der einzige Pfad, auf dem ein Nutzerkonto entsteht oder ein Passwort gesetzt wird
(Plan §11, "Kapselung für v2"). Die Nutzerverwaltung (`api/users.py`) und der
Erststart (`core/db_setup.py`) rufen hier hinein statt selbst zu hashen.

Ein späterer IdP-Anschluss ergänzt hier einen zweiten Zweig (Konto aus
IdP-Claims anlegen, Passwortfelder leer lassen) und **ergänzt** damit die lokale
users-Tabelle, statt sie zu ersetzen.

Klartextpasswörter werden zurückgegeben, aber nie geloggt und nie gespeichert
(F-005).
"""

from typing import Optional

from sqlalchemy.orm import Session

from core.login_throttle import clear_user
from core.passwords import generate_password, hash_password
from models.database import User


def create_local_user(
    db: Session,
    *,
    username: str,
    password: Optional[str] = None,
    name: Optional[str] = None,
    email: Optional[str] = None,
    role: str = "user",
    commit: bool = True,
) -> tuple[User, str]:
    """Legt ein lokales Konto an und liefert (Nutzer, Klartextpasswort).

    Ohne `password` wird eines generiert. `must_change_password` ist immer True:
    ein von jemand anderem gesetztes Passwort gilt nur bis zum ersten Login.
    """
    plain = password or generate_password()
    user = User(
        username=username,
        name=name,
        email=email,
        password_hash=hash_password(plain),
        role=role,
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    if commit:
        db.commit()
        db.refresh(user)
    return user, plain


def set_password(db: Session, user: User, password: Optional[str] = None, commit: bool = True) -> str:
    """Setzt das Passwort neu und liefert den Klartext.

    Zugleich Entsperrung: der übliche Anlass eines Resets ist ein Nutzer, der sich
    ausgesperrt hat. `must_change_password` verhindert, dass das vom Administrator
    gesetzte Passwort dauerhaft in Benutzung bleibt.
    """
    plain = password or generate_password()
    user.password_hash = hash_password(plain)
    user.must_change_password = True
    user.failed_login_count = 0
    user.locked_until = None
    clear_user(user.username)
    if commit:
        db.commit()
        db.refresh(user)
    return plain


def unlock(db: Session, user: User, commit: bool = True) -> None:
    """Hebt die Sperre auf — beide Seiten.

    Nur die DB-Spalten zu leeren genügt nicht: die Redis-Sperre läuft pro
    (Benutzername, IP) unabhängig weiter, der Nutzer bekäme bis zum Ablauf der TTL
    weiter 423. Das Entsperren sähe erfolgreich aus und wäre es nicht.
    """
    user.failed_login_count = 0
    user.locked_until = None
    clear_user(user.username)
    if commit:
        db.commit()
        db.refresh(user)
