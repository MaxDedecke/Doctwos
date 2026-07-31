import pytest

from core.teams import get_visible_team_ids, is_admin
from models.database import Team, TeamMembership, User


@pytest.fixture
def two_teams(db_session):
    a = Team(name="Helper Test Team A")
    b = Team(name="Helper Test Team B")
    db_session.add_all([a, b])
    db_session.commit()
    db_session.refresh(a)
    db_session.refresh(b)
    yield a, b
    db_session.query(Team).filter(Team.id.in_([a.id, b.id])).delete(synchronize_session=False)
    db_session.commit()


def test_is_admin_true_for_superuser_role():
    user = User(username="helper-admin", email="admin@example.com", name="Admin", role="superuser")
    assert is_admin(user) is True


def test_is_admin_false_for_regular_user():
    user = User(username="helper-nonadmin", email="nobody@example.com", name="Nobody", role="user")
    assert is_admin(user) is False


def test_get_visible_team_ids_returns_none_for_admin(db_session):
    user = User(username="helper-admin-2", email="admin2@example.com", name="Admin", role="superuser")
    assert get_visible_team_ids(user, db_session) is None


def test_get_visible_team_ids_returns_only_member_teams(db_session, two_teams):
    team_a, team_b = two_teams
    user = User(username="helper-member", email="member@example.com", name="Member",
                password_hash="x", role="user")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    db_session.add(TeamMembership(user_id=user.id, team_id=team_a.id))
    db_session.commit()

    try:
        visible = get_visible_team_ids(user, db_session)
        assert visible == [team_a.id]
        assert team_b.id not in visible
    finally:
        db_session.query(TeamMembership).filter(TeamMembership.user_id == user.id).delete()
        db_session.query(User).filter(User.id == user.id).delete()
        db_session.commit()


def test_get_visible_team_ids_empty_list_for_user_with_no_teams(db_session):
    user = User(username="helper-orphan", email="orphan@example.com", name="Orphan",
                password_hash="x", role="user")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    try:
        assert get_visible_team_ids(user, db_session) == []
    finally:
        db_session.query(User).filter(User.id == user.id).delete()
        db_session.commit()
