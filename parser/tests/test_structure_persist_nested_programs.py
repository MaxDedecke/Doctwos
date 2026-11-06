"""Reparse einer Datei, in der ein Programm von nebengeordnet zu verschachtelt wechselt (CobolCraft-Sync 06.11.2026).

Vorher hing ein weiterverwendeter Paragraph über seinen Elternverweis am alten Programmdatensatz; der wurde als
veraltet gelöscht, ON DELETE CASCADE nahm den Paragraphen mit, und die neue Kante verletzte den Fremdschlüssel.
"""

import uuid

import pytest
from sqlalchemy import text

from cobol.parse import parse_program
from db import SessionLocal
from doctus_models.database import CodeEdge, CodeEntity, KnowledgeSource
from structure_persist import persist_parse_result

SIBLINGS = """IDENTIFICATION DIVISION.
PROGRAM-ID. OUTER.
PROCEDURE DIVISION.
    CALL 'INNER'
    GOBACK.
END PROGRAM OUTER.
IDENTIFICATION DIVISION.
PROGRAM-ID. INNER.
PROCEDURE DIVISION.
    PERFORM WORK-PARA
    GOBACK.
WORK-PARA.
    DISPLAY 'W'.
END PROGRAM INNER.
"""

NESTED = """IDENTIFICATION DIVISION.
PROGRAM-ID. OUTER.
PROCEDURE DIVISION.
    CALL 'INNER'
    GOBACK.
IDENTIFICATION DIVISION.
PROGRAM-ID. INNER.
PROCEDURE DIVISION.
    PERFORM WORK-PARA
    GOBACK.
WORK-PARA.
    DISPLAY 'W'.
END PROGRAM INNER.
END PROGRAM OUTER.
"""


@pytest.fixture
def workspace():
    db = SessionLocal()
    team_id = db.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:n, now()) RETURNING id"),
        {"n": f"nested-{uuid.uuid4().hex[:8]}"},
    ).scalar_one()
    project_id = db.execute(
        text(
            "INSERT INTO projects (name, team_id, created_at) VALUES ('nested', :t, now()) RETURNING id"
        ),
        {"t": team_id},
    ).scalar_one()
    source = KnowledgeSource(name="repo", type="Git", team_id=team_id, project_id=project_id)
    db.add(source)
    db.commit()
    try:
        yield db, project_id, source.id
    finally:
        db.rollback()
        db.query(CodeEdge).filter(CodeEdge.source_id == source.id).delete()
        db.query(CodeEntity).filter(CodeEntity.source_id == source.id).delete()
        db.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db.execute(
            text("DELETE FROM link_builder_dirty_items WHERE project_id = :id"), {"id": project_id}
        )
        db.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
        db.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
        db.commit()
        db.close()


def _persist(db, project_id, source_id, source_text, content_hash):
    result = parse_program(source_text, "prog.cbl")
    persist_parse_result(
        db,
        project_id=project_id,
        source_id=source_id,
        file_path="prog.cbl",
        content_hash=content_hash,
        result=result,
    )
    db.commit()


def test_a_program_that_becomes_nested_keeps_its_children_and_edges(workspace):
    db, project_id, source_id = workspace
    _persist(db, project_id, source_id, SIBLINGS, "a" * 32)
    _persist(db, project_id, source_id, NESTED, "b" * 32)

    rows = {
        row.qualified_name: row
        for row in db.query(CodeEntity).filter(CodeEntity.source_id == source_id)
    }
    assert "INNER" not in rows
    inner = rows["OUTER.INNER"]
    assert inner.parent_id == rows["OUTER"].id
    work = rows["INNER.WORK-PARA"]
    assert work.parent_id == inner.id
    perform = (
        db.query(CodeEdge).filter(CodeEdge.source_id == source_id, CodeEdge.type == "PERFORM").one()
    )
    assert perform.src_entity_id == rows["INNER.PROCEDURE-START"].id
    assert perform.dst_entity_id == work.id


def test_a_nested_program_gets_its_parent_on_the_first_persist(workspace):
    db, project_id, source_id = workspace
    _persist(db, project_id, source_id, NESTED, "b" * 32)
    rows = {
        row.qualified_name: row
        for row in db.query(CodeEntity).filter(CodeEntity.source_id == source_id)
    }
    assert rows["OUTER.INNER"].parent_id == rows["OUTER"].id
    assert rows["INNER.PROCEDURE-START"].parent_id == rows["OUTER.INNER"].id
