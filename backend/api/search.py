"""
backend/api/search.py
======================
Globale, typenübergreifende Suche für die Suchleiste im Frontend-Header.
Entwickler kennen oft nur einen Programmnamen oder einen Confluence-Seitentitel —
dieser Endpunkt findet beides (plus Repositories und Wissensquellen) in einem Aufruf.

Endpoints:
    GET /search — Suche über Repository, Entity, Dokument, Wissensquelle
"""

from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.db_setup import get_db
from models.database import User
from core.auth_dependency import get_current_user
from core.teams import get_visible_team_ids
from core.projects import get_visible_project_ids
from services.search import search_nodes, ALL_TYPES

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search(
    q: str = "",
    types: str = ALL_TYPES,
    project_id: Optional[int] = None,
    source_id: Optional[int] = None,
    limit: int = 8,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    team_ids = get_visible_team_ids(user, db)
    project_ids = get_visible_project_ids(user, db)
    results, counts = search_nodes(
        db, q=q, types=types, project_id=project_id, source_id=source_id, limit=limit,
        visible_team_ids=team_ids, visible_project_ids=project_ids
    )
    return {"query": q, "counts": counts, "results": results}
