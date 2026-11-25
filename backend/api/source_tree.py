"""Datei-Baum einer Wissensquelle ebenen- und seitenweise (``services/source_tree.py``)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.auth_dependency import get_current_user
from core.db_setup import get_db
from core.projects import assert_knowledge_source_visible
from codena_models.database import KnowledgeSource, User
from services.source_tree import MAX_PAGE, list_directory, scan_summary

router = APIRouter(prefix="/knowledge-sources", tags=["knowledge_sources"])


def _visible_source(db: Session, user: User, source_id: int) -> KnowledgeSource:
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Wissensquelle nicht gefunden")
    assert_knowledge_source_visible(source, user, db)
    return source


@router.get("/{source_id}/tree")
def get_source_tree(
    source_id: int,
    dir: str = Query(default="", max_length=2000),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=MAX_PAGE),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Direkte Einträge eines Ordners, seitenweise; ``next_offset`` ist gesetzt, solange weitere folgen."""
    _visible_source(db, user, source_id)
    return list_directory(db, source_id, dir, offset=offset, limit=limit)


@router.get("/{source_id}/scan-summary")
def get_source_scan_summary(
    source_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    _visible_source(db, user, source_id)
    return scan_summary(db, source_id)
