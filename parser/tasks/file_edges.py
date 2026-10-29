"""Abgeleitete Daten der Graph-Übersicht (Grundgerüst, Gruppen) nach Änderungen neu berechnen."""

import logging
from typing import Callable, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from doctus_models.code_file_edges import rebuild_code_file_edges
from doctus_models.code_file_groups import rebuild_code_file_groups

logger = logging.getLogger(__name__)


def _in_savepoint(db: Session, rebuild: Callable, project_id: Optional[int]) -> Optional[int]:
    """Abgeleitete Daten dürfen den umgebenden Sync nicht scheitern lassen. Bei einem Fehler bleibt
    der alte Stand stehen und `None` kommt zurück."""
    try:
        with db.begin_nested():
            return rebuild(db, project_id)
    except SQLAlchemyError:
        logger.exception("%s für Projekt %s fehlgeschlagen", rebuild.__name__, project_id)
        return None


def refresh_code_file_edges(db: Session, project_id: Optional[int]) -> Optional[int]:
    """Grundgerüst und Gruppen neu berechnen; Rückgabe: Dateikanten im Grundgerüst."""
    built = _in_savepoint(db, rebuild_code_file_edges, project_id)
    _in_savepoint(db, rebuild_code_file_groups, project_id)
    return built


def refresh_code_file_groups(db: Session, project_id: Optional[int]) -> Optional[int]:
    """Nur die Gruppen neu berechnen (z. B. nach einer Topic-Änderung)."""
    return _in_savepoint(db, rebuild_code_file_groups, project_id)
