import pytest
from models.database import Team, TeamMembership, User

def test_admin_teams_operations(client, db_session):
    # Der client-Fixture-Nutzer hat role="superuser" (siehe conftest).
    
    # Clean up any leftover team from previous runs
    from models.database import Team
    db_session.query(Team).filter(Team.name == "TestTeamX").delete()
    db_session.commit()
    
    try:
        # Create team
        res = client.post("/teams?name=TestTeamX")
        assert res.status_code == 200
        team_id = res.json()["id"]
        
        # List teams
        res = client.get("/teams")
        assert res.status_code == 200
        assert any(t["id"] == team_id for t in res.json())
        
        # Get members (initially empty)
        res = client.get(f"/teams/{team_id}/members")
        assert res.status_code == 200
        
        # Delete team
        res = client.delete(f"/teams/{team_id}")
        assert res.status_code == 200
        
    finally:
        db_session.query(Team).filter(Team.name == "TestTeamX").delete()
        db_session.commit()
