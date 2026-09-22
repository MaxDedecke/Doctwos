from uuid import uuid4

import pytest

from models.database import Insight, Project, ProjectMembership, TeamMembership, User
from core.auth_dependency import SESSION_COOKIE_NAME, create_session_cookie_value


def _add_project_admin(db_session, project_id: int, username: str) -> User:
    project = db_session.query(Project).filter(Project.id == project_id).one()
    user = User(
        username=f"{username}-{uuid4().hex}",
        email=f"{username}-{uuid4().hex}@example.com",
        password_hash="$argon2id$fixture",
        role="user",
    )
    db_session.add(user)
    db_session.commit()
    db_session.add(ProjectMembership(project_id=project_id, user_id=user.id, role="admin"))
    db_session.add(TeamMembership(team_id=project.team_id, user_id=user.id))
    db_session.commit()
    return user


def _as_user(client, user: User) -> None:
    client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value(user.id))


@pytest.fixture
def insight_admin_factory(db_session, test_project):
    created_ids = []

    def create(username: str) -> User:
        user = _add_project_admin(db_session, test_project, username)
        created_ids.append(user.id)
        return user

    yield create

    if created_ids:
        db_session.query(Insight).filter(Insight.project_id == test_project).delete(
            synchronize_session=False
        )
        db_session.commit()
        db_session.query(User).filter(User.id.in_(created_ids)).delete(synchronize_session=False)
        db_session.commit()


def test_insight_requires_evidence_and_is_created_as_draft(client, db_session, test_project):
    missing_evidence = client.post(
        f"/projects/{test_project}/insights",
        json={"title": "Regel", "content": "Eine Aussage", "origin_kind": "chat", "evidence": []},
    )
    assert missing_evidence.status_code == 422

    response = client.post(
        f"/projects/{test_project}/insights",
        json={
            "title": "  Zahlungsregel  ",
            "content": "  Zahlung wird vor dem Buchen validiert.  ",
            "origin_kind": "chat",
            "evidence": [{"chat_message_id": 42}, {"file": "PAYMENT.cbl", "start_line": 15}],
        },
    )
    assert response.status_code == 201
    insight = response.json()
    assert insight["status"] == "draft"
    assert insight["title"] == "Zahlungsregel"
    assert insight["verified_by_id"] is None

    stored = db_session.query(Insight).filter(Insight.id == insight["id"]).one()
    assert stored.evidence_json[0]["chat_message_id"] == 42


def test_insight_needs_a_different_project_admin_for_verification(
    client, db_session, test_project, insight_admin_factory
):
    author = insight_admin_factory("insight-author")
    reviewer = insight_admin_factory("insight-reviewer")
    member = insight_admin_factory("insight-member")
    db_session.query(ProjectMembership).filter(
        ProjectMembership.project_id == test_project,
        ProjectMembership.user_id == member.id,
    ).update({"role": "member"})
    db_session.commit()

    _as_user(client, author)
    created = client.post(
        f"/projects/{test_project}/insights",
        json={
            "title": "Codepfad",
            "content": "Der Pfad ruft die Buchung auf.",
            "origin_kind": "code",
            "evidence": [{"entity_id": 12, "file": "PAYMENT.cbl", "start_line": 15}],
        },
    )
    assert created.status_code == 201
    insight_id = created.json()["id"]

    own_approval = client.post(
        f"/projects/{test_project}/insights/{insight_id}/verify", json={"confirm": True}
    )
    assert own_approval.status_code == 403

    _as_user(client, member)
    member_approval = client.post(
        f"/projects/{test_project}/insights/{insight_id}/verify", json={"confirm": True}
    )
    assert member_approval.status_code == 403

    _as_user(client, reviewer)
    verified = client.post(
        f"/projects/{test_project}/insights/{insight_id}/verify", json={"confirm": True}
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "verified"
    assert verified.json()["verified_by_id"] == reviewer.id
    assert verified.json()["verified_at"] is not None

    duplicate = client.post(
        f"/projects/{test_project}/insights/{insight_id}/verify", json={"confirm": True}
    )
    assert duplicate.status_code == 409

    _as_user(client, author)
    listed = client.get(f"/projects/{test_project}/insights", params={"status": "verified"})
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [insight_id]
