"""Dateieingabe der Änderungsanalyse: Mainframe-Endungen in Großbuchstaben (`.CBL`) werden eindeutig gefunden."""

from models.database import CodeEdge, CodeEntity, KnowledgeSource, Project
from services.change_impact import inspect_change_impact


def _entity(db, project_id, source_id, path, name, type_="paragraph"):
    item = CodeEntity(project_id=project_id, source_id=source_id, file_path=path, name=name, type=type_,
                      qualified_name=f"{path}::{name}", start_line=1, end_line=2)
    db.add(item)
    db.flush()
    return item


def test_file_path_matches_ignoring_case_only_when_unambiguous(db_session, test_project):
    team_id = db_session.query(Project.team_id).filter(Project.id == test_project).scalar()
    source = KnowledgeSource(name="impact-case", type="Git", project_id=test_project, team_id=team_id, spaces={})
    db_session.add(source)
    db_session.flush()
    callee = _entity(db_session, test_project, source.id, "app/cbl/CBSTM03B.CBL", "CALLEE")
    caller = _entity(db_session, test_project, source.id, "app/cbl/CBSTM03A.CBL", "CALLER")
    db_session.add(CodeEdge(project_id=test_project, source_id=source.id, src_entity_id=caller.id,
                            dst_entity_id=callee.id, dst_name="CALLEE", type="PERFORM", resolution="resolved"))
    db_session.flush()

    lower = inspect_change_impact(db_session, project_id=test_project, file_path="app/cbl/CBSTM03B.cbl")
    assert "error" not in lower
    assert {node["id"] for node in lower["nodes"]} >= {callee.id, caller.id}

    _entity(db_session, test_project, source.id, "app/cbl/cbstm03b.cbl", "OTHER")
    ambiguous = inspect_change_impact(db_session, project_id=test_project, file_path="app/cbl/Cbstm03b.Cbl")
    assert "error" in ambiguous
