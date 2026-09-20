"""Shared read-only API for evidence-backed change packages (O-273)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.auth_dependency import get_current_user
from core.db_setup import get_db
from core.projects import assert_project_visible
from core.teams import assert_team_visible
from models.database import Project, User
from services.change_package import inspect_change_package


router = APIRouter(tags=["change-packages"])


@router.get("/projects/{project_id}/change-package")
def get_change_package(
    project_id: int,
    entity_id: int | None = Query(default=None, ge=1),
    file_path: str | None = Query(default=None, min_length=1, max_length=1000),
    source_id: int | None = Query(default=None, ge=1),
    base_ref: str | None = Query(default=None, min_length=1, max_length=256),
    head_ref: str | None = Query(default=None, min_length=1, max_length=256),
    direction: str = Query(default="incoming", pattern="^(incoming|outgoing|both)$"),
    hops: int = Query(default=2, ge=0, le=3),
    limit: int = Query(default=40, ge=10, le=80),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return bounded code, knowledge, issue, test and ownership evidence."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_team_visible(project.team_id, user, db, "Projekt nicht gefunden")
    assert_project_visible(project_id, user, db)
    diff_requested = base_ref is not None or head_ref is not None
    if diff_requested and (not base_ref or not head_ref):
        raise HTTPException(status_code=422, detail="base_ref und head_ref müssen zusammen angegeben werden")
    if diff_requested and (entity_id is not None or file_path is not None):
        raise HTTPException(status_code=422, detail="Diff-Eingabe kann nicht mit entity_id oder file_path kombiniert werden")
    if not diff_requested and (entity_id is None and file_path is None):
        raise HTTPException(status_code=422, detail="entity_id, file_path oder ein Git-Diff ist erforderlich")

    result = inspect_change_package(
        db,
        project_id=project_id,
        entity_id=entity_id,
        file_path=file_path,
        source_id=source_id,
        base_ref=base_ref,
        head_ref=head_ref,
        direction=direction,
        hops=hops,
        limit=limit,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result
