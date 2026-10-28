from uuid import uuid4
from hashlib import sha256

from db import SessionLocal
from java.parse import parse_java_file
from doctus_models.database import CodeEdge, CodeEntity, KnowledgeSource, Project, Team
from structure_persist import persist_parse_result
from tasks.edge_resolver import resolve_global_edges


def test_lambda_dispatch_is_recomputed_without_duplicates_or_stale_bindings():
    with SessionLocal() as db:
        team = Team(name="lambda-" + uuid4().hex)
        db.add(team)
        db.flush()
        project = Project(name="lambda", team_id=team.id)
        db.add(project)
        db.flush()
        source = KnowledgeSource(
            name="lambda", type="Git", url="local", project_id=project.id, team_id=team.id
        )
        db.add(source)
        db.commit()
        text = "interface Task{void run();} class C{void work(){} void use(){Task t=()->work();t.run();}}"
        try:

            def persist(text):
                result = parse_java_file(text, "C.java")
                persist_parse_result(
                    db,
                    source_id=source.id,
                    project_id=project.id,
                    file_path=result.path,
                    content_hash=sha256(text.encode()).hexdigest(),
                    result=result,
                )
                db.commit()

            persist(text)
            for _ in range(2):
                resolve_global_edges(db, source.id)
                dispatch = (
                    db.query(CodeEdge).filter_by(source_id=source.id, type="DISPATCHES_TO").all()
                )
                assert len(dispatch) == 1
                assert db.get(CodeEntity, dispatch[0].dst_entity_id).type == "lambda"
            persist(text.replace("t.run();", "t=()->work();t.run();"))
            resolve_global_edges(db, source.id)
            assert (
                db.query(CodeEdge).filter_by(source_id=source.id, type="DISPATCHES_TO").count() == 0
            )
        finally:
            db.delete(project)
            db.commit()
            db.delete(team)
            db.commit()
