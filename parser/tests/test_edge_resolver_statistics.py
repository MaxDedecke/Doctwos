import uuid

import pytest
from sqlalchemy import event

from db import SessionLocal
from doctus_models.database import KnowledgeSource, Project, Team
from tasks.edge_resolver import resolve_global_edges


@pytest.fixture
def workspace():
    db = SessionLocal()
    team = Team(name="stats-" + uuid.uuid4().hex)
    db.add(team)
    db.flush()
    project = Project(name="stats", team_id=team.id)
    db.add(project)
    db.flush()
    source = KnowledgeSource(name="stats", type="Git", team_id=team.id, project_id=project.id)
    db.add(source)
    db.commit()
    try:
        yield db, source
    finally:
        db.delete(project)
        db.commit()
        db.delete(team)
        db.commit()
        db.close()


def test_statistics_are_refreshed_before_edges_of_a_new_source_are_read(workspace):
    db, source = workspace
    statements = []
    engine = db.get_bind()

    def record(conn, cursor, statement, *args):
        statements.append(statement.lstrip().upper())

    event.listen(engine, "before_cursor_execute", record)
    try:
        resolve_global_edges(db, source.id)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    analyze = next(i for i, s in enumerate(statements) if s.startswith("ANALYZE"))
    assert "CODE_ENTITIES" in statements[analyze] and "CODE_EDGES" in statements[analyze]
    first_edge_read = next(
        i for i, s in enumerate(statements) if s.startswith("SELECT") and "CODE_EDGES" in s
    )
    assert analyze < first_edge_read
