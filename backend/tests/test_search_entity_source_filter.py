"""O-348: der Quellfilter der globalen Suche muss auch für Code-Entities greifen
(vorher wurden Entities bei gesetztem source_id komplett übersprungen -> 0 Treffer)."""

from models.database import CodeEntity, KnowledgeSource, Project
from services.search import search_nodes


def _source(db_session, project_id, name):
    proj = db_session.query(Project).filter(Project.id == project_id).first()
    src = KnowledgeSource(
        name=name, type="Local", project_id=project_id, team_id=proj.team_id, spaces={}
    )
    db_session.add(src)
    db_session.commit()
    db_session.refresh(src)
    return src


def _entity(db_session, project_id, source_id, path):
    e = CodeEntity(
        project_id=project_id,
        source_id=source_id,
        file_path=path,
        name="COPAUA0C",
        type="program",
        qualified_name=f"{path}::COPAUA0C",
    )
    db_session.add(e)
    db_session.commit()
    return e


def test_entity_search_respects_source_filter(db_session, test_project):
    a = _source(db_session, test_project, "Quelle A")
    b = _source(db_session, test_project, "Quelle B")
    ea = _entity(db_session, test_project, a.id, "a/COPAUA0C.cbl")
    eb = _entity(db_session, test_project, b.id, "b/COPAUA0C.cbl")
    try:
        res, counts = search_nodes(
            db_session, q="COPAUA0C", types="entity", project_id=test_project, source_id=a.id
        )
        assert counts["entity"] == 1
        assert [r["node_meta"]["source_id"] for r in res] == [a.id]

        _, all_counts = search_nodes(
            db_session, q="COPAUA0C", types="entity", project_id=test_project
        )
        assert all_counts["entity"] == 2
    finally:
        db_session.delete(ea)
        db_session.delete(eb)
        db_session.delete(a)
        db_session.delete(b)
        db_session.commit()
