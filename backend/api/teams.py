from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from core.db_setup import get_db
from core.teams import require_admin
from models.database import Team, TeamMembership, User, Project, KnowledgeSource

router = APIRouter(prefix="/teams", tags=["teams"], dependencies=[Depends(require_admin)])

@router.get("")
def list_teams(db: Session = Depends(get_db)):
    teams = db.query(Team).all()
    return [{"id": t.id, "name": t.name, "created_at": t.created_at} for t in teams]

@router.post("")
def create_team(name: str, db: Session = Depends(get_db)):
    # Check if team name already exists
    existing = db.query(Team).filter(Team.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Team-Name existiert bereits")
    
    team = Team(name=name)
    db.add(team)
    db.commit()
    db.refresh(team)
    return {"id": team.id, "name": team.name, "created_at": team.created_at}

@router.patch("/{team_id}")
def update_team(team_id: int, name: str, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team nicht gefunden")
    
    # Check if name is already taken
    existing = db.query(Team).filter(Team.name == name, Team.id != team_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Team-Name existiert bereits")
    
    team.name = name
    db.commit()
    db.refresh(team)
    return {"id": team.id, "name": team.name, "created_at": team.created_at}

@router.delete("/{team_id}")
def delete_team(team_id: int, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team nicht gefunden")
    
    # Check sharp edge 2: Team deletion blocked if resources attached
    projects_count = db.query(Project).filter(Project.team_id == team_id).count()
    sources_count = db.query(KnowledgeSource).filter(KnowledgeSource.team_id == team_id).count()
    
    if projects_count > 0 or sources_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Team kann nicht gelöscht werden — {projects_count} Projekte und {sources_count} Wissensquellen sind noch zugeordnet"
        )
    
    # Team memberships cascade-delete automatically
    db.delete(team)
    db.commit()
    return {"message": "Team erfolgreich gelöscht"}

@router.get("/{team_id}/members")
def get_team_members(team_id: int, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team nicht gefunden")
    
    memberships = db.query(TeamMembership).filter(TeamMembership.team_id == team_id).all()
    return [{"id": m.user.id, "email": m.user.email, "name": m.user.name} for m in memberships if m.user]

@router.post("/{team_id}/members")
def add_team_member(team_id: int, user_id: int, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team nicht gefunden")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    
    # Check duplicate membership
    existing = db.query(TeamMembership).filter(
        TeamMembership.team_id == team_id,
        TeamMembership.user_id == user_id
    ).first()
    if existing:
        return {"message": "Benutzer ist bereits Mitglied dieses Teams"}
        
    membership = TeamMembership(team_id=team_id, user_id=user_id)
    db.add(membership)
    db.commit()
    return {"message": "Mitglied erfolgreich hinzugefügt"}

@router.delete("/{team_id}/members/{user_id}")
def remove_team_member(team_id: int, user_id: int, db: Session = Depends(get_db)):
    membership = db.query(TeamMembership).filter(
        TeamMembership.team_id == team_id,
        TeamMembership.user_id == user_id
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Mitgliedschaft nicht gefunden")
    
    db.delete(membership)
    db.commit()
    return {"message": "Mitglied erfolgreich entfernt"}
