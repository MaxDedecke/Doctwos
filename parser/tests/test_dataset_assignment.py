"""O-147: JCL-DD-Name ↔ COBOL `ASSIGN TO` als abgeleitete Kante Datei → Dataset."""
from types import SimpleNamespace as Row

import pytest
from sqlalchemy import text

from core.dataset_assignment import DERIVED_BY, EDGE_TYPE, derive_assignments
from db import SessionLocal
from models.database import CodeEdge, CodeEntity, KnowledgeSource
from tasks.edge_resolver import _derive_dataset_assignments


def entity(id_, type_, name, parent_id=None, meta=None, path="x", line=1):
    return Row(id=id_, type=type_, name=name, qualified_name=f"{path}::{name}", parent_id=parent_id,
               meta_json=meta, file_path=path, start_line=line, end_line=line + 1, project_id=1, source_id=1,
               variant_key="default")


def edge(type_, src, dst, resolution="resolved", meta=None, line=5):
    return Row(type=type_, src_entity_id=src, dst_entity_id=dst, resolution=resolution, meta_json=meta,
               src_start_line=line)


def scenario(program_resolved=True):
    entities = [
        entity(1, "jcl_step", "STEP15", path="app/jcl/POSTTRAN.jcl"),
        entity(2, "program", "CBTRN02C", path="app/cbl/CBTRN02C.cbl"),
        entity(3, "file_fd", "TRANSACT-FILE", parent_id=2, meta={"assign": "TRANFILE"}, path="app/cbl/CBTRN02C.cbl", line=30),
        entity(4, "file_fd", "DALYREJS-FILE", parent_id=2, meta={"assign": "DALYREJS"}, path="app/cbl/CBTRN02C.cbl", line=40),
        entity(5, "jcl_dataset", "AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS", meta={"dataset_name": "AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS"}),
        entity(6, "jcl_dataset", "AWS.M2.CARDDEMO.LOADLIB", meta={"dataset_name": "AWS.M2.CARDDEMO.LOADLIB"}),
        entity(7, "jcl_dataset", "AWS.M2.CARDDEMO.DALYREJS", meta={"dataset_name": "AWS.M2.CARDDEMO.DALYREJS"}),
    ]
    edges = [
        edge("EXECUTES", 1, 2 if program_resolved else None, "resolved" if program_resolved else "unresolved"),
        edge("READS", 1, 5, meta={"ddname": "TRANFILE", "disposition": "SHR", "access_certainty": "possible"}, line=12),
        edge("READS", 1, 6, meta={"ddname": "STEPLIB", "disposition": "SHR"}, line=11),
        edge("WRITES", 1, 7, meta={"ddname": "dalyrejs", "disposition": "NEW"}, line=14),
    ]
    return entities, edges


def test_dd_names_equal_to_assign_names_become_file_to_dataset_edges():
    records = derive_assignments(*scenario())
    by_file = {record["src_entity_id"]: record for record in records}
    assert set(by_file) == {3, 4}  # STEPLIB gehört keiner Datei des Programms
    transact = by_file[3]
    assert (transact["dst_entity_id"], transact["dst_name"]) == (5, "AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS")
    assert transact["src_start_line"] == 30
    meta = transact["meta"]
    assert meta["derived_by"] == DERIVED_BY and meta["certainty"] == "possible"
    assert (meta["ddname"], meta["assign"], meta["jcl_start_line"]) == ("TRANFILE", "TRANFILE", 12)
    assert meta["jcl_step_qualified_name"].endswith("::STEP15") and meta["program_qualified_name"].endswith("::CBTRN02C")
    assert by_file[4]["meta"]["ddname"] == "DALYREJS"  # ohne Groß-/Kleinschreibung


def test_nothing_is_guessed_without_a_resolved_program_or_with_ambiguous_files():
    assert derive_assignments(*scenario(program_resolved=False)) == []
    entities, edges = scenario()
    entities.append(entity(8, "file_fd", "OTHER-TRANS", parent_id=2, meta={"assign": "TRANFILE"}, path="app/cbl/CBTRN02C.cbl"))
    assert {record["src_entity_id"] for record in derive_assignments(entities, edges)} == {4}


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_database_pass_is_idempotent_and_drops_stale_edges(db_session):
    team_id = db_session.execute(text("INSERT INTO teams (name, created_at) VALUES ('ds-team', now()) RETURNING id")).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES ('ds-proj', :t, now()) RETURNING id"), {"t": team_id},
    ).scalar_one()
    source = KnowledgeSource(name="ds", type="git", project_id=project_id, team_id=team_id)
    db_session.add(source)
    db_session.flush()
    try:
        def make(type_, name, path, parent=None, meta=None, line=1):
            row = CodeEntity(project_id=project_id, source_id=source.id, file_path=path, name=name, type=type_,
                             qualified_name=f"{path}::{name}", start_line=line, end_line=line + 1,
                             parent_id=parent.id if parent else None, meta_json=meta)
            db_session.add(row)
            db_session.flush()
            return row

        step = make("jcl_step", "S1", "j.jcl")
        program = make("program", "PGM", "p.cbl")
        fd = make("file_fd", "IN-FILE", "p.cbl", parent=program, meta={"assign": "INFILE"}, line=9)
        dataset = make("jcl_dataset", "A.B.C", "j.jcl", meta={"dataset_name": "A.B.C"})

        def link(type_, dst, resolution="resolved", meta=None):
            row = CodeEdge(project_id=project_id, source_id=source.id, src_entity_id=step.id, dst_entity_id=dst.id,
                           dst_name=dst.name, type=type_, resolution=resolution, meta_json=meta, src_start_line=3)
            db_session.add(row)
            db_session.flush()
            return row

        executes = link("EXECUTES", program)
        link("READS", dataset, meta={"ddname": "INFILE", "disposition": "SHR"})

        def derived():
            return db_session.query(CodeEdge).filter(CodeEdge.source_id == source.id, CodeEdge.type == EDGE_TYPE).all()

        assert _derive_dataset_assignments(db_session, source.id) == 1
        db_session.flush()
        first = derived()
        assert [(e.src_entity_id, e.dst_entity_id, e.resolution) for e in first] == [(fd.id, dataset.id, "resolved")]
        assert first[0].src_start_line == 9 and first[0].meta_json["jcl_start_line"] == 3

        assert _derive_dataset_assignments(db_session, source.id) == 0  # zweiter Lauf: nichts Neues, nichts doppelt
        db_session.flush()
        assert [e.id for e in derived()] == [first[0].id]

        executes.resolution, executes.dst_entity_id = "unresolved", None  # Programm nicht mehr aufgelöst
        db_session.flush()
        assert _derive_dataset_assignments(db_session, source.id) == 0
        db_session.flush()
        assert derived() == []
    finally:
        db_session.rollback()
