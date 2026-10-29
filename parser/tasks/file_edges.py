"""Dateikanten der Graph-Übersicht nach Änderungen an den Code-Beziehungen neu berechnen."""

import logging
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from doctus_models.code_file_edges import rebuild_code_file_edges

logger = logging.getLogger(__name__)


def refresh_code_file_edges(db: Session, project_id: Optional[int]) -> Optional[int]:
    """Neu berechnen im Savepoint: Abgeleitete Daten dürfen den umgebenden Sync nicht scheitern
    lassen. Bei einem Fehler bleibt der alte Stand stehen und `None` kommt zurück."""
    try:
        with db.begin_nested():
            return rebuild_code_file_edges(db, project_id)
    except SQLAlchemyError:
        logger.exception("Dateikanten für Projekt %s konnten nicht berechnet werden", project_id)
        return None
