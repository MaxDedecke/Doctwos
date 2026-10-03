"""Katalogisierte JCL-Prozeduren werden über das Bibliothekselement (`NAME.prc`) aufgelöst; IBM-Programme sind extern."""
import pytest
from sqlalchemy import text

from core.external_targets import classify_external
from db import SessionLocal
from models.database import CodeEdge, CodeEntity, KnowledgeSource
from tasks.edge_resolver import _resolve_jcl_edges


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_ibm_programs_in_jcl_are_external_utilities():
    for name in ("FTP", "ASMA90", "DSNHPC"):
        assert classify_external("EXECUTES", name, "jcl") == {"category": "ibm_utility", "kind": "utility_program"}
    assert classify_external("EXECUTES", "MYPROG", "jcl") is None


def test_cataloged_procedure_resolves_to_unique_library_member(db_session):
    team_id = db_session.execute(text("INSERT INTO teams (name, created_at) VALUES ('jcl-team', now()) RETURNING id")).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES ('jcl-proj', :t, now()) RETURNING id"), {"t": team_id},
    ).scalar_one()
    source = KnowledgeSource(name="jcl", type="git", project_id=project_id, team_id=team_id)
    db_session.add(source)
    db_session.flush()
    try:
        def entity(type_, name, path):
            row = CodeEntity(project_id=project_id, source_id=source.id, file_path=path, name=name, type=type_,
                             qualified_name=f"{path}::{type_}:{name}", start_line=1, end_line=1, meta_json={"language": "jcl"})
            db_session.add(row)
            db_session.flush()
            return row

        job = entity("jcl_job", "JOB1", "a/JOB1.jcl")
        reproc = entity("jcl_file", "REPROC.prc", "app/proc/REPROC.prc")
        entity("jcl_file", "TWIN.prc", "x/TWIN.prc")
        entity("jcl_file", "TWIN.PROC", "y/TWIN.PROC")
        entity("jcl_file", "NOTPROC.jcl", "z/NOTPROC.jcl")

        def edge(name):
            row = CodeEdge(project_id=project_id, source_id=source.id, src_entity_id=job.id, dst_name=name, type="EXECUTES",
                           resolution="unresolved",
                           meta_json={"language": "jcl", "execution_kind": "procedure", "target_entity_type": "jcl_proc", "target_proc_name": name})
            db_session.add(row)
            db_session.flush()
            return row

        def edge_from(step, name):
            row = CodeEdge(project_id=project_id, source_id=source.id, src_entity_id=step.id, dst_name=name, type="EXECUTES",
                           resolution="unresolved",
                           meta_json={"language": "jcl", "execution_kind": "procedure", "target_entity_type": "jcl_proc", "target_proc_name": name})
            db_session.add(row)
            db_session.flush()
            return row

        found, twin, notproc, missing = edge("reproc"), edge("TWIN"), edge("NOTPROC"), edge("GONE")
        # (1) Instream-Prozedur im selben Job gewinnt.
        instream = entity("jcl_proc", "SHARED", "lib/JOB1.jcl")
        entity("jcl_proc", "SHARED", "lib/OTHER.prc")
        in_job = edge_from(entity("jcl_step", "S1", "lib/JOB1.jcl"), "SHARED")
        # (2) Bibliothek sucht nach Membername: `TRANREPT.prc` beginnt zwar mit `//REPROC PROC`, ist aber nicht das Member REPROC.
        member_proc = entity("jcl_proc", "LIBPROC", "lib/LIBPROC.prc")
        entity("jcl_proc", "LIBPROC", "lib/MISLABELED.prc")
        from_job = edge_from(entity("jcl_step", "S2", "jobs/J2.jcl"), "LIBPROC")
        from_member = edge_from(entity("jcl_step", "S3", "lib/MISLABELED.prc"), "LIBPROC")
        # Ohne Instream-Treffer und ohne gleichnamiges Member bleibt es mehrdeutig.
        entity("jcl_proc", "PAIR", "lib/X.prc")
        entity("jcl_proc", "PAIR", "lib/Y.prc")
        pair = edge_from(entity("jcl_step", "S4", "jobs/J3.jcl"), "PAIR")
        assert _resolve_jcl_edges(db_session, source.id) == 4
        assert in_job.dst_entity_id == instream.id
        assert from_job.dst_entity_id == member_proc.id
        assert from_member.dst_entity_id == member_proc.id  # nicht die eigene Prozedur (Selbstaufruf)
        assert pair.resolution == "unresolved"
        assert (found.resolution, found.dst_entity_id) == ("resolved", reproc.id)
        assert found.meta_json["resolution_via"] == "proc_library_member"
        for item in (twin, notproc, missing):  # mehrdeutig, keine Prozedurdatei, fehlt: nichts geraten
            assert item.resolution == "unresolved"
    finally:
        db_session.rollback()


def test_earlier_self_resolution_of_a_procedure_call_is_corrected_on_the_next_run(db_session):
    team_id = db_session.execute(text("INSERT INTO teams (name, created_at) VALUES ('jcl-team2', now()) RETURNING id")).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES ('jcl-proj2', :t, now()) RETURNING id"), {"t": team_id},
    ).scalar_one()
    source = KnowledgeSource(name="jcl2", type="git", project_id=project_id, team_id=team_id)
    db_session.add(source)
    db_session.flush()
    try:
        def entity(type_, name, path):
            row = CodeEntity(project_id=project_id, source_id=source.id, file_path=path, name=name, type=type_,
                             qualified_name=f"{path}::{type_}:{name}", start_line=1, end_line=1, meta_json={"language": "jcl"})
            db_session.add(row)
            db_session.flush()
            return row

        real = entity("jcl_proc", "REPROC", "app/proc/REPROC.prc")
        mislabeled = entity("jcl_proc", "REPROC", "app/proc/TRANREPT.prc")
        step = entity("jcl_step", "STEP01R", "app/proc/TRANREPT.prc")
        edge = CodeEdge(project_id=project_id, source_id=source.id, src_entity_id=step.id, dst_entity_id=mislabeled.id,
                        dst_name="REPROC", type="EXECUTES", resolution="resolved",
                        meta_json={"language": "jcl", "execution_kind": "procedure", "target_entity_type": "jcl_proc",
                                   "target_proc_name": "REPROC", "target_qualified_name": "app/proc/TRANREPT.prc::proc:REPROC"})
        db_session.add(edge)
        db_session.flush()
        assert _resolve_jcl_edges(db_session, source.id) == 1
        assert edge.dst_entity_id == real.id and edge.resolution == "resolved"
    finally:
        db_session.rollback()
