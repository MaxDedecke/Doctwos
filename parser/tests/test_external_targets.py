"""O-375: Systemziele werden als extern gekennzeichnet, echte Lücken nicht."""

import pytest

from core.external_targets import classify_external
from db import SessionLocal
from models.database import CodeEdge, CodeEntity, KnowledgeSource
from sqlalchemy import text
from tasks.edge_resolver import _mark_external_targets


@pytest.mark.parametrize(
    "edge_type,name,language,category",
    [
        ("COPY", "DFHAID", None, "cics"),
        ("COPY", "dfhbmsca", None, "cics"),
        ("COPY", "CMQODV", None, "mq"),
        ("COPY", "SQLCA", None, "db2"),
        ("CALL", "CEE3ABD", "cobol", "language_environment"),
        ("CALL", "CBLTDLI", None, "ims"),
        ("CALL", "MQOPEN", None, "mq"),
        ("EXECUTES", "IEBGENER", "jcl", "ibm_utility"),
        ("EXECUTES", "SDSF", "jcl", "ibm_utility"),
        ("EXECUTES", "IGYCRCTL", "jcl", "ibm_utility"),
        ("EXECUTES", "DFSRRC00", "jcl", "ims"),
        ("EXECUTES", "DFHCSDUP", "jcl", "cics"),
        ("EXECUTES", "DFHECP1$", "jcl", "cics"),
    ],
)
def test_known_system_targets_are_classified(edge_type, name, language, category):
    assert classify_external(edge_type, name, language)["category"] == category


@pytest.mark.parametrize(
    "edge_type,name,language",
    [
        ("CALL", "COBDATFT", None),  # kundeneigenes Programm: echte Lücke
        ("COPY", "CVACT01Y", None),
        ("EXECUTES", "IEBGENER", "cobol"),  # EXEC-Operation, kein JCL-Programm
        ("EXECUTES", "REPROC", "jcl"),  # kundeneigene PROC: echte Lücke
        ("EXECUTES", "CBTRN02C", "jcl"),  # Anwendungsprogramm: echte Lücke, falls ungelöst
        ("CALLS", "MQOPEN", "java"),
        ("CALL", "", None),
    ],
)
def test_real_gaps_and_other_languages_are_not_marked(edge_type, name, language):
    assert classify_external(edge_type, name, language) is None


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_pass_marks_unresolved_system_targets_and_clears_resolved_ones(db_session):
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES ('ext-team', now()) RETURNING id")
    ).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES ('ext-proj', :t, now()) RETURNING id"),
        {"t": team_id},
    ).scalar_one()
    source = KnowledgeSource(name="ext", type="git", project_id=project_id, team_id=team_id)
    db_session.add(source)
    db_session.flush()
    try:
        program = CodeEntity(
            project_id=project_id, source_id=source.id, file_path="a.cbl", name="A", type="program",
            qualified_name="A", start_line=1, end_line=2,
        )
        db_session.add(program)
        db_session.flush()

        def edge(edge_type, name, resolution="unresolved", meta=None):
            row = CodeEdge(
                project_id=project_id, source_id=source.id, src_entity_id=program.id, dst_name=name,
                type=edge_type, resolution=resolution, meta_json=meta,
            )
            db_session.add(row)
            return row

        copy_sys = edge("COPY", "DFHAID")
        call_gap = edge("CALL", "COBDATFT")
        stale = edge("CALL", "MQOPEN", "resolved", {"external": {"category": "mq", "kind": "system_routine"}})
        db_session.flush()
        _mark_external_targets(db_session, source.id)
        db_session.flush()
        assert copy_sys.meta_json["external"] == {"category": "cics", "kind": "system_copybook"}
        assert call_gap.meta_json is None
        assert stale.meta_json is None
    finally:
        db_session.rollback()
