"""Shared Java package rows must survive deletion/reparse of the file that created them.

Regression: the row keeps the path of its creator. Deleting that file used to
re-home it onto ANY entity of the source (e.g. a COBOL program); the next reparse
of that program then deleted the package and cascaded through `parent_id` into
every unchanged Java class.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from connectors.git import _delete_file_entities
from db import SessionLocal
from java.parse import parse_java_file
from models.database import CodeEdge, CodeEntity, KnowledgeSource
from structure_persist import persist_parse_result


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def source(db_session, tmp_path):
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:n, now()) RETURNING id"),
        {"n": f"shared-java-team-{tmp_path.name}"},
    ).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES (:n, :t, now()) RETURNING id"),
        {"n": f"shared-java-project-{tmp_path.name}", "t": team_id},
    ).scalar_one()
    src = KnowledgeSource(
        name=f"shared-java-{tmp_path.name}", type="Git", project_id=project_id, team_id=team_id
    )
    db_session.add(src)
    db_session.commit()
    yield src
    db_session.query(CodeEdge).filter(CodeEdge.source_id == src.id).delete(synchronize_session=False)
    db_session.query(CodeEntity).filter(CodeEntity.source_id == src.id).delete(synchronize_session=False)
    db_session.query(KnowledgeSource).filter(KnowledgeSource.id == src.id).delete(synchronize_session=False)
    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
    db_session.commit()


def _persist_java(db, src, path, body):
    result = parse_java_file(f"package com.acme;\n{body}\n", path)
    persist_parse_result(
        db, project_id=src.project_id, source_id=src.id, file_path=path,
        content_hash=path, result=result,
    )
    db.commit()
    return result.variant_key


def _classes(db, src):
    return {
        e.qualified_name
        for e in db.query(CodeEntity).filter(CodeEntity.source_id == src.id, CodeEntity.type == "class")
    }


def _package(db, src):
    return db.query(CodeEntity).filter(
        CodeEntity.source_id == src.id, CodeEntity.type == "package", CodeEntity.qualified_name == "com.acme"
    ).one()


def _add_cobol_program(db, src, variant_key):
    db.add(CodeEntity(
        source_id=src.id, project_id=src.project_id, file_path="PAYMENT.CBL", variant_key=variant_key,
        name="PAYMENT", qualified_name="PAYMENT", type="program", meta_json={"language": "cobol"},
    ))
    db.commit()


def test_deleting_package_owner_rehomes_package_to_java_file_not_cobol(db_session, source):
    # The COBOL row is older (lower id) than the Java survivors: the old lookup
    # picked "the first other entity" and therefore chose it.
    _add_cobol_program(db_session, source, parse_java_file("class X {}", "X.java").variant_key)
    _persist_java(db_session, source, "a/Legacy.java", "class Legacy {}")
    _persist_java(db_session, source, "a/Client.java", "class Client {}")
    _persist_java(db_session, source, "a/Report.java", "class Report {}")
    assert _package(db_session, source).file_path == "a/Legacy.java"

    _delete_file_entities(db_session, source_id=source.id, file_path="a/Legacy.java")
    db_session.commit()

    assert _package(db_session, source).file_path in {"a/Client.java", "a/Report.java"}
    # Deleting/reparsing the COBOL file must no longer take the Java classes with it.
    _delete_file_entities(db_session, source_id=source.id, file_path="PAYMENT.CBL")
    db_session.commit()
    assert _classes(db_session, source) == {"com.acme.Client", "com.acme.Report"}


def test_last_java_file_of_package_removes_the_package(db_session, source):
    _persist_java(db_session, source, "a/Only.java", "class Only {}")
    _delete_file_entities(db_session, source_id=source.id, file_path="a/Only.java")
    db_session.commit()
    assert db_session.query(CodeEntity).filter(CodeEntity.source_id == source.id).count() == 0


def test_owner_file_reparsed_into_other_package_keeps_package_for_siblings(db_session, source):
    _persist_java(db_session, source, "a/Owner.java", "class Owner {}")
    _persist_java(db_session, source, "a/Sibling.java", "class Sibling {}")
    result = parse_java_file("package other;\nclass Owner {}\n", "a/Owner.java")
    persist_parse_result(
        db_session, project_id=source.project_id, source_id=source.id, file_path="a/Owner.java",
        content_hash="moved", result=result,
    )
    db_session.commit()
    assert _package(db_session, source).file_path == "a/Sibling.java"
    assert "com.acme.Sibling" in _classes(db_session, source)
