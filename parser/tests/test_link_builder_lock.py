import pytest
from sqlalchemy import text
from db import SessionLocal
from models.database import LinkBuilderRun
from tasks.link_builder import compute_entity_links_async, redis_client

@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def test_project(db_session):
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": "lock-test-team"},
    ).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"),
        {"name": "lock-test-project", "team_id": team_id},
    ).scalar_one()
    db_session.commit()

    yield project_id

    # Cleanup
    db_session.query(LinkBuilderRun).filter(LinkBuilderRun.project_id == project_id).delete()
    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
    db_session.commit()

@pytest.mark.anyio
async def test_compute_entity_links_stale_lock_override(db_session, test_project):
    project_id = test_project
    lock_key = f"lock:compute_entity_links:{project_id}"
    
    # Clean any potential leftover locks
    redis_client.delete(lock_key)

    # 1. Create a "stale" Run that has status "completed" but left the lock standing (e.g. crash)
    stale_run = LinkBuilderRun(
        project_id=project_id,
        task_type="entity_links",
        status="completed"
    )
    db_session.add(stale_run)
    db_session.commit()
    db_session.refresh(stale_run)

    # Manually populate the Redis lock with the stale run ID
    redis_client.set(lock_key, str(stale_run.id))

    # 2. Create the current pending run that should override the stale lock
    current_run = LinkBuilderRun(
        project_id=project_id,
        task_type="entity_links",
        status="pending"
    )
    db_session.add(current_run)
    db_session.commit()
    db_session.refresh(current_run)

    # No mocks/patches needed, empty entities will naturally exit and complete the run
    await compute_entity_links_async(current_run.id, project_id)

    # 3. Assertions
    db_session.refresh(current_run)
    # The current run should have completed successfully instead of being skipped!
    assert current_run.status == "completed"
    
    # The lock should have been released cleanly
    assert redis_client.get(lock_key) is None
