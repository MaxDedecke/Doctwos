"""Buildprofil, Sprachzuordnung und Preflight-Bericht einer Git-Quelle (O-151).

Das Profil liegt weiter in `KnowledgeSource.spaces` (`build_profile`, `language_paths`);
der Parser liest es von dort. Dieser Router ergänzt Eingangsprüfung und Lesesicht.
Änderungen wirken ab dem nächsten Sync und ändern den Analyse-Fingerprint, die
betroffenen Dateien werden dann neu analysiert.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth_dependency import get_current_user
from core.build_profile import (
    ProfileValidationError,
    validate_build_profile,
    validate_language_paths,
)
from core.db_setup import get_db
from core.projects import assert_knowledge_source_visible
from core.source_preflight import build_preflight
from core.teams import require_admin
from models.database import KnowledgeSource, User

router = APIRouter(prefix="/knowledge-sources", tags=["knowledge-sources"])


class BuildProfileUpdate(BaseModel):
    # Nur mitgesendete Felder ändern etwas; ein explizites null entfernt die Einstellung.
    build_profile: Optional[dict[str, Any]] = None
    language_paths: Optional[dict[str, str]] = None


def _git_source(db: Session, source_id: int, user: User) -> KnowledgeSource:
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Wissensquelle nicht gefunden")
    assert_knowledge_source_visible(source, user, db)
    if (source.type or "").lower() != "git":
        raise HTTPException(
            status_code=400, detail="Buildprofil und Preflight gibt es nur für Git-Quellen"
        )
    return source


def _spaces_of(source: KnowledgeSource) -> dict:
    spaces = source.spaces
    if isinstance(spaces, str):
        try:
            spaces = json.loads(spaces)
        except ValueError:
            spaces = {}
    return dict(spaces) if isinstance(spaces, dict) else {}


def _profile_view(source: KnowledgeSource) -> dict[str, Any]:
    spaces = _spaces_of(source)
    return {
        "source_id": source.id,
        "build_profile": spaces.get("build_profile"),
        "language_paths": spaces.get("language_paths"),
    }


@router.get("/{source_id}/build-profile")
def get_build_profile(
    source_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return _profile_view(_git_source(db, source_id, user))


@router.put("/{source_id}/build-profile")
def put_build_profile(
    source_id: int,
    update: BuildProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    source = _git_source(db, source_id, user)
    fields = update.model_fields_set
    spaces = _spaces_of(source)
    try:
        if "build_profile" in fields:
            if update.build_profile is None:
                spaces.pop("build_profile", None)
            else:
                spaces["build_profile"] = validate_build_profile(update.build_profile)
        if "language_paths" in fields:
            if update.language_paths is None:
                spaces.pop("language_paths", None)
            else:
                spaces["language_paths"] = validate_language_paths(update.language_paths)
    except ProfileValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    source.spaces = spaces
    db.commit()
    db.refresh(source)
    return {
        **_profile_view(source),
        "note": "Gilt ab dem nächsten Sync; betroffene Dateien werden dann neu analysiert.",
    }


@router.get("/{source_id}/preflight")
def get_preflight(
    source_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return build_preflight(db, _git_source(db, source_id, user))
