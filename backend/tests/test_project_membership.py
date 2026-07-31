import pytest
from core.auth_dependency import SESSION_COOKIE_NAME, create_session_cookie_value
from models.database import Team, TeamMembership, User, Project, ProjectMembership, ProjectAccessRequest


@pytest.fixture
def second_team_member(test_project, db_session):
    """A second user, member (not admin) of the same team+project as `test_project`."""
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    user = User(username="second-member", email="second-member@example.com", name="Second Member",
                password_hash="x", role="user")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    db_session.add(TeamMembership(user_id=user.id, team_id=proj.team_id))
    db_session.add(ProjectMembership(user_id=user.id, project_id=proj.id, role="member"))
    db_session.commit()

    yield user

    db_session.query(ProjectMembership).filter(ProjectMembership.user_id == user.id).delete()
    db_session.query(TeamMembership).filter(TeamMembership.user_id == user.id).delete()
    db_session.query(User).filter(User.id == user.id).delete()
    db_session.commit()


def test_approving_access_request_creates_membership(client, db_session, test_project):
    requester = User(username="approve-req", email="approve-req@example.com", name="Requester",
                    password_hash="x", role="user")
    db_session.add(requester)
    db_session.commit()
    db_session.refresh(requester)

    req = ProjectAccessRequest(project_id=test_project, user_id=requester.id, status="pending")
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)

    try:
        res = client.post(f"/projects/{test_project}/access-requests/{req.id}/resolve", json={"status": "approved"})
        assert res.status_code == 200

        membership = db_session.query(ProjectMembership).filter(
            ProjectMembership.project_id == test_project,
            ProjectMembership.user_id == requester.id
        ).first()
        assert membership is not None
        assert membership.role == "member"
    finally:
        db_session.query(ProjectMembership).filter(ProjectMembership.user_id == requester.id).delete()
        db_session.query(ProjectAccessRequest).filter(ProjectAccessRequest.id == req.id).delete()
        db_session.query(User).filter(User.id == requester.id).delete()
        db_session.commit()


def test_non_admin_member_cannot_add_or_remove_members(unauthenticated_client, db_session, test_project, second_team_member):
    unauthenticated_client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value(second_team_member.id))

    res = unauthenticated_client.post(f"/projects/{test_project}/members", json={"user_id": second_team_member.id, "role": "member"})
    assert res.status_code == 403

    res = unauthenticated_client.delete(f"/projects/{test_project}/members/{second_team_member.id}")
    assert res.status_code == 403


def test_non_admin_member_cannot_view_or_resolve_access_requests(unauthenticated_client, db_session, test_project, second_team_member):
    unauthenticated_client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value(second_team_member.id))

    res = unauthenticated_client.get(f"/projects/{test_project}/access-requests")
    assert res.status_code == 403

    res = unauthenticated_client.post(f"/projects/{test_project}/access-requests/999999/resolve", json={"status": "approved"})
    assert res.status_code == 403


def test_project_creator_cannot_be_removed(client, db_session, test_project):
    user = db_session.query(User).filter(User.username == "test-fixture-user").first()
    res = client.delete(f"/projects/{test_project}/members/{user.id}")
    assert res.status_code == 400


def test_admin_can_change_member_role_to_admin(client, db_session, test_project, second_team_member):
    res = client.patch(
        f"/projects/{test_project}/members/{second_team_member.id}",
        json={"role": "admin"}
    )
    assert res.status_code == 200
    assert res.json()["role"] == "admin"

    db_session.refresh(second_team_member)
    membership = db_session.query(ProjectMembership).filter(
        ProjectMembership.project_id == test_project,
        ProjectMembership.user_id == second_team_member.id
    ).first()
    assert membership.role == "admin"


def test_change_member_role_rejects_unknown_role(client, test_project, second_team_member):
    res = client.patch(
        f"/projects/{test_project}/members/{second_team_member.id}",
        json={"role": "superadmin"}
    )
    assert res.status_code == 400


def test_non_admin_member_cannot_change_role(unauthenticated_client, test_project, second_team_member):
    unauthenticated_client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value(second_team_member.id))
    res = unauthenticated_client.patch(
        f"/projects/{test_project}/members/{second_team_member.id}",
        json={"role": "admin"}
    )
    assert res.status_code == 403


def test_request_access_rejects_project_from_foreign_team(client, db_session):
    """Regression test: request-access must not leak/accept requests for a
    project whose team the user isn't a member of (team membership is the
    only access primitive, per docs/TEAM_ACCESS_CONTROL.md)."""
    foreign_team = Team(name="TestForeignTeamX")
    db_session.add(foreign_team)
    db_session.commit()
    db_session.refresh(foreign_team)

    foreign_project = Project(name="Foreign Project X", team_id=foreign_team.id)
    db_session.add(foreign_project)
    db_session.commit()
    db_session.refresh(foreign_project)

    try:
        res = client.post(f"/projects/{foreign_project.id}/request-access")
        assert res.status_code == 404

        pending = db_session.query(ProjectAccessRequest).filter(
            ProjectAccessRequest.project_id == foreign_project.id
        ).first()
        assert pending is None
    finally:
        db_session.query(ProjectAccessRequest).filter(
            ProjectAccessRequest.project_id == foreign_project.id
        ).delete()
        db_session.delete(foreign_project)
        db_session.delete(foreign_team)
        db_session.commit()


def test_discoverable_lists_own_team_projects_without_membership(client, db_session):
    """GET /projects/discoverable should surface same-team projects the user
    hasn't joined, and must not leak project ids as a route match before the
    literal /{id} handler (the classic FastAPI int-converter ordering bug)."""
    from models.database import User

    user = db_session.query(User).filter(User.email == "fixture-user@example.com").first()
    default_team = db_session.query(TeamMembership).filter(TeamMembership.user_id == user.id).first()
    own_team_id = default_team.team_id

    discoverable_project = Project(name="Discoverable Project X", team_id=own_team_id)
    joined_project = Project(name="Already Joined Project X", team_id=own_team_id)
    db_session.add_all([discoverable_project, joined_project])
    db_session.commit()
    db_session.refresh(discoverable_project)
    db_session.refresh(joined_project)
    db_session.add(ProjectMembership(user_id=user.id, project_id=joined_project.id, role="member"))
    db_session.commit()

    foreign_team = Team(name="TestForeignTeamY")
    db_session.add(foreign_team)
    db_session.commit()
    db_session.refresh(foreign_team)
    foreign_project = Project(name="Foreign Project Y", team_id=foreign_team.id)
    db_session.add(foreign_project)
    db_session.commit()
    db_session.refresh(foreign_project)

    try:
        res = client.get("/projects/discoverable")
        assert res.status_code == 200
        ids = {p["id"] for p in res.json()}
        assert discoverable_project.id in ids
        assert joined_project.id not in ids
        assert foreign_project.id not in ids

        # the literal /{id} route must still work normally
        res = client.get(f"/projects/{discoverable_project.id}")
        assert res.status_code in (403, 404, 200)
    finally:
        db_session.query(ProjectMembership).filter(
            ProjectMembership.project_id == joined_project.id
        ).delete()
        db_session.delete(discoverable_project)
        db_session.delete(joined_project)
        db_session.delete(foreign_project)
        db_session.delete(foreign_team)
        db_session.commit()
