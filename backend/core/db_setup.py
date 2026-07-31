import logging
import os
import secrets

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:password@db:5432/doctus")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def bootstrap_superuser() -> None:
    """
    Legt beim ersten Start genau einen Superuser an (F-001).

    Ohne gesetztes BOOTSTRAP_SUPERUSER_PASSWORD wird ein Passwort generiert und
    EINMALIG ins Startlog geschrieben — die Software ist damit ohne DB-Zugriff in
    Betrieb zu nehmen. must_change_password erzwingt den Wechsel beim ersten Login.

    Idempotent: existiert bereits irgendein Nutzer, passiert nichts.
    """
    from core import config as cfg
    from core.passwords import hash_password
    from models.database import User

    # Vor der ersten Migration existiert die Tabelle noch nicht — dann still zurück,
    # der nächste Start nach `alembic upgrade head` legt den Nutzer an.
    if not inspect(engine).has_table("users"):
        logger.warning("[bootstrap] Tabelle 'users' existiert noch nicht — Superuser-Anlage übersprungen.")
        return

    db = SessionLocal()
    try:
        if db.query(User).first() is not None:
            return

        password = cfg.BOOTSTRAP_SUPERUSER_PASSWORD or secrets.token_urlsafe(18)
        generated = not cfg.BOOTSTRAP_SUPERUSER_PASSWORD

        db.add(User(
            username=cfg.BOOTSTRAP_SUPERUSER,
            email=cfg.BOOTSTRAP_SUPERUSER_EMAIL or None,
            name="Administrator",
            password_hash=hash_password(password),
            role="superuser",
            is_active=True,
            must_change_password=True,
        ))
        db.commit()

        if generated:
            logger.warning(
                "\n"
                "=================================================================\n"
                " Erster Start: Superuser angelegt.\n"
                "   Benutzer:  %s\n"
                "   Passwort:  %s\n"
                " Dieses Passwort wird NUR EINMAL angezeigt und muss beim ersten\n"
                " Login geändert werden.\n"
                "=================================================================",
                cfg.BOOTSTRAP_SUPERUSER, password,
            )
        else:
            logger.info(
                "[bootstrap] Superuser '%s' angelegt (Passwort aus BOOTSTRAP_SUPERUSER_PASSWORD).",
                cfg.BOOTSTRAP_SUPERUSER,
            )
    finally:
        db.close()
