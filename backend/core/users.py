"""
backend/core/users.py
=====================
Der einzige Pfad, auf dem ein Nutzerkonto entsteht oder ein Passwort gesetzt wird
(Plan §11, "Kapselung für v2"). Die Nutzerverwaltung (`api/users.py`) und der
Erststart (`core/db_setup.py`) rufen hier hinein statt selbst zu hashen.

Der IdP-Anschluss (E-12, core/oidc.py) ergänzt hier einen zweiten Zweig
(`create_oidc_user`/`get_by_oidc_subject`: Konto aus IdP-Claims anlegen,
`password_hash=None`) und **ergänzt** damit die lokale users-Tabelle, statt sie
zu ersetzen.

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


def get_by_oidc_subject(db: Session, subject: str) -> Optional[User]:
    return db.query(User).filter(User.oidc_subject == subject).first()


def create_oidc_user(
    db: Session,
    *,
    username: str,
    subject: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    commit: bool = True,
) -> User:
    """Legt ein Konto aus IdP-Claims an (E-12, core/oidc.py::provision_or_link_user).

    Kein lokales Passwort (`password_hash=None`) — die feste IdP-Kennung `subject`
    ist ab jetzt der einzige Weg, wie dieser Nutzer sich anmeldet. Rolle bleibt der
    Default 'user': Rechte kommen weiterhin aus Doctus selbst, nicht aus
    IdP-Gruppen/-Claims, ein Administrator stuft bei Bedarf über die normale
    Nutzerverwaltung hoch. `must_change_password` bleibt False — es gibt kein
    lokales Passwort, das gewechselt werden könnte.
    """
    user = User(
        username=username,
        name=name,
        email=email,
        password_hash=None,
        oidc_subject=subject,
        role="user",
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    if commit:
        db.commit()
        db.refresh(user)
    return user


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
