"""Fähigkeitsprüfung je KI-Profil (``services/profile_capabilities.py``); nur für Admins."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import core.config as cfg
from core.db_setup import get_db
from core.teams import require_admin
from doctus_models.database import AIProfile, User
from services.ai_settings import get_settings, serialize_profile
from services.profile_capabilities import probe_capabilities

router = APIRouter(tags=["ai-profiles"])


@router.post("/ai-profiles/{profile_id}/capabilities")
async def check_ai_profile_capabilities(
    profile_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """Prüft Werkzeugaufruf, Argumente, Ergebnisnutzung, Streaming und Denken mit einem kleinen Lauf.

    Ein fehlgeschlagener Aufruf (Server nicht erreichbar) wird mit Fehler gespeichert und lässt die
    Fähigkeiten offen, statt den Agenten für das Profil abzuschalten.
    """
    profile = db.query(AIProfile).filter(AIProfile.id == profile_id).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="AI-Profil nicht gefunden")
    if profile.kind == "cloud" and not cfg.cloud_llm_allowed():
        raise HTTPException(status_code=403, detail="Cloud-LLM-Provider sind deaktiviert")
    profile.capabilities_json = await probe_capabilities(profile)
    db.commit()
    return serialize_profile(profile, active_id=get_settings(db).active_profile_id)
