"""USES_MAP: Dialogprogramm → BMS-Maske, nur bei genau einem Treffer."""

import pytest
from sqlalchemy import text

from db import SessionLocal
from doctus_models.database import CodeEdge, CodeEntity, KnowledgeSource
from tasks.cics_resolver import resolve_map_edges


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_a_map_resolves_by_name_and_mapset_and_an_ambiguous_one_stays_open(db_session):
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES ('bms-team', now()) RETURNING id")
    ).scalar_one()
    project_id = db_session.execute(
        text(
            "INSERT INTO projects (name, team_id, created_at) "
            "VALUES ('bms-proj', :t, now()) RETURNING id"
        ),
        {"t": team_id},
    ).scalar_one()
    source = KnowledgeSource(name="bms", type="git", project_id=project_id, team_id=team_id)
    db_session.add(source)
    db_session.flush()
    try:

        def entity(type_, name, path, meta=None):
            row = CodeEntity(
                project_id=project_id,
                source_id=source.id,
                file_path=path,
                name=name,
                type=type_,
                qualified_name=f"{path}::{name}",
                start_line=1,
                end_line=2,
                meta_json=meta,
            )
            db_session.add(row)
            db_session.flush()
            return row

        program = entity("program", "SIGNON", "app/cbl/SIGNON.cbl")
        login = entity("bms_map", "LOGIN1A", "app/bms/LOGIN1.bms", {"mapset": "LOGIN1"})
        entity("bms_map", "HELPA", "app/bms/HELP1.bms", {"mapset": "HELP1"})
        entity("bms_map", "HELPA", "app/bms/HELP2.bms", {"mapset": "HELP2"})
        help2 = db_session.query(CodeEntity).filter_by(file_path="app/bms/HELP2.bms").one()

        def uses_map(dst, mapset=None):
            row = CodeEdge(
                project_id=project_id,
                source_id=source.id,
                src_entity_id=program.id,
                dst_name=dst,
                type="USES_MAP",
                resolution="unresolved",
                meta_json={"mapset": mapset} if mapset else {},
                src_start_line=5,
            )
            db_session.add(row)
            db_session.flush()
            return row

        by_mapset = uses_map("LOGIN1A", "LOGIN1")
        chosen = uses_map("HELPA", "HELP2")
        ambiguous = uses_map("HELPA")
        wrong_mapset = uses_map("LOGIN1A", "OTHER")

        assert resolve_map_edges(db_session, source.id) == 2
        assert (by_mapset.resolution, by_mapset.dst_entity_id) == ("resolved", login.id)
        assert (chosen.resolution, chosen.dst_entity_id) == ("resolved", help2.id)
        assert (ambiguous.resolution, ambiguous.dst_entity_id) == ("unresolved", None)
        assert (wrong_mapset.resolution, wrong_mapset.dst_entity_id) == ("unresolved", None)
        assert resolve_map_edges(db_session, source.id) == 0
    finally:
        db_session.rollback()
