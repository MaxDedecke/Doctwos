"""
backend/core/teams.py
=======================
Team-Sichtbarkeits-Helfer — die einzige Stelle, die "welche Teams darf dieser
Nutzer sehen" beantwortet. Jeder Router, der Repository/KnowledgeSource o.ä.
anfasst, filtert/prüft darüber statt eigene team_id-Logik zu duplizieren.

Admin = User.role == 'superuser' (F-004). is_admin(user) == True bedeutet
überall "ungefiltert sehen".
"""

from typing import Optional

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from core.auth_dependency import get_current_user
from models.database import TeamMembership, User

# Team, dem der Erststart-Superuser beitritt und auf das `_resolve_team_id`
# (knowledge_sources.py) für Admins ohne explizite Team-Wahl zurückfällt —
# ein Name an beiden Stellen, damit der Fallback nie ins Leere greift.
DEFAULT_TEAM_NAME = "Default Team"


def is_admin(user: User) -> bool:
    return (user.role or "user") == "superuser"


def get_visible_team_ids(user: User, db: Session) -> Optional[list[int]]:
    """None = unrestricted (admin). Otherwise the list of team_ids this user is a member of."""
    if is_admin(user):
        return None
    rows = db.query(TeamMembership.team_id).filter(TeamMembership.user_id == user.id).all()
    return [r[0] for r in rows]


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Nur für Administratoren")
    return user


def assert_team_visible(team_id: int, user: User, db: Session, not_found_detail: str) -> None:
    """Raises 404 if the user cannot see this team_id (mirrors the existing 404 wording
    instead of a 403 — knowing a resource exists in a team you're not on is itself a
    small leak of org structure across team boundaries)."""
    visible = get_visible_team_ids(user, db)
    if visible is not None and team_id not in visible:
        raise HTTPException(status_code=404, detail=not_found_detail)
