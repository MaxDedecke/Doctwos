import pytest
from fastapi.testclient import TestClient

from core.auth_dependency import SESSION_COOKIE_NAME, create_session_cookie_value
from core.db_setup import SessionLocal, get_db
from main import app
from models.database import Team, TeamMembership, User, Project, ProjectMembership

TEST_USERNAME = "test-fixture-user"
TEST_USER_EMAIL = "fixture-user@example.com"
# Kein echtes Passwort nötig: die Fixture setzt die Session-Cookie direkt.
TEST_USER_PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$unused-fixture-hash"


@pytest.fixture
def db_session():
    """
    Real session against the configured Postgres+pgvector DB.

    Endpoint code under test calls db.commit() directly, so a wrapping
    rollback-on-teardown transaction would not undo anything (SQLAlchemy
    only rolls back what hasn't been committed). Tests are responsible for
    deleting what they create — Repository rows cascade-delete their
    KnowledgeSource children, so deleting the repo is usually enough.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def unauthenticated_client(db_session):
    """TestClient with no session cookie — for asserting auth is actually enforced."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def client(unauthenticated_client, db_session):
    """
    Authenticated TestClient (most endpoints require a session since Phase 2).
    Creates a throwaway test user and a valid signed session cookie for it.
    """
    user = db_session.query(User).filter(User.username == TEST_USERNAME).first()
    if not user:
        user = User(
            username=TEST_USERNAME,
            email=TEST_USER_EMAIL,
            name="Fixture User",
            password_hash=TEST_USER_PASSWORD_HASH,
            role="superuser",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

    # Ensure the user is a member of the Default Team for general endpoint access
    default_team = db_session.query(Team).filter(Team.name == "Default Team").first()
    if not default_team:
        default_team = Team(name="Default Team")
        db_session.add(default_team)
        db_session.commit()
        db_session.refresh(default_team)

    membership = db_session.query(TeamMembership).filter(
        TeamMembership.user_id == user.id,
        TeamMembership.team_id == default_team.id
    ).first()
    if not membership:
        db_session.add(TeamMembership(user_id=user.id, team_id=default_team.id))
        db_session.commit()

    unauthenticated_client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value(user.id))
    yield unauthenticated_client

    db_session.query(TeamMembership).filter(TeamMembership.user_id == user.id).delete()
    db_session.query(User).filter(User.id == user.id).delete()
    db_session.commit()


@pytest.fixture
def test_team(client, db_session):
    """
    A team the `client` fixture's user is a member of. team_id is a required column
    on Repository/KnowledgeSource, so any test creating one — directly via the ORM or
    through the API — needs a real team to point at.
    """
    team = Team(name="Test Team")
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)

    user = db_session.query(User).filter(User.username == TEST_USERNAME).first()
    db_session.add(TeamMembership(user_id=user.id, team_id=team.id))
    db_session.commit()

    yield team.id

    db_session.query(TeamMembership).filter(TeamMembership.team_id == team.id).delete()
    db_session.query(Team).filter(Team.id == team.id).delete()
    db_session.commit()


@pytest.fixture
def test_project(test_team, db_session):
    user = db_session.query(User).filter(User.username == TEST_USERNAME).first()
    proj = Project(name="Test Project", team_id=test_team, creator_id=user.id)
    db_session.add(proj)
    db_session.commit()
    db_session.refresh(proj)

    membership = ProjectMembership(project_id=proj.id, user_id=user.id, role="admin")
    db_session.add(membership)
    db_session.commit()

    yield proj.id

    db_session.query(ProjectMembership).filter(ProjectMembership.project_id == proj.id).delete()
    db_session.query(Project).filter(Project.id == proj.id).delete()
    db_session.commit()
