"""Interface-Aufruf zur einzigen Implementierung im Quelltext (Katalogtest 08.11.2026, J3)."""

from hashlib import sha256
from uuid import uuid4

from db import SessionLocal
from doctus_models.database import CodeEdge, CodeEntity, KnowledgeSource, Project, Team
from java.parse import parse_java_file
from structure_persist import persist_parse_result
from tasks.edge_resolver import resolve_global_edges

FILES = {
    "p/AnyOp.java": "package p; public interface AnyOp<C> { String create(C c, boolean f); }",
    "p/UserOp.java": "package p; public interface UserOp extends AnyOp<String> {}",
    "p/GroupOp.java": "package p; public interface GroupOp extends AnyOp<Integer> {}",
    "p/AbstractLogic.java": (
        "package p; public abstract class AbstractLogic {"
        " public String create(String c, boolean f) { return c; } }"
    ),
    "p/UserLogic.java": "package p; public class UserLogic extends AbstractLogic implements UserOp {}",
    "p/GroupLogicA.java": (
        "package p; public class GroupLogicA implements GroupOp {"
        " public String create(Integer c, boolean f) { return null; } }"
    ),
    "p/GroupLogicB.java": (
        "package p; public class GroupLogicB implements GroupOp {"
        " public String create(Integer c, boolean f) { return null; } }"
    ),
    "p/Service.java": (
        "package p; public class Service { private UserOp users; private GroupOp groups;"
        ' String run() { groups.create(1, true); return users.create("x", true); } }'
    ),
}


def test_a_call_on_an_interface_dispatches_only_to_its_single_implementation():
    with SessionLocal() as db:
        team = Team(name="dispatch-" + uuid4().hex)
        db.add(team)
        db.flush()
        project = Project(name="dispatch", team_id=team.id)
        db.add(project)
        db.flush()
        source = KnowledgeSource(
            name="dispatch", type="Git", url="local", project_id=project.id, team_id=team.id
        )
        db.add(source)
        db.commit()
        try:
            for path, text in FILES.items():
                result = parse_java_file(text, path)
                persist_parse_result(
                    db,
                    source_id=source.id,
                    project_id=project.id,
                    file_path=result.path,
                    content_hash=sha256(text.encode()).hexdigest(),
                    result=result,
                )
            db.commit()
            for _ in range(2):  # Neuberechnung ohne Dubletten
                resolve_global_edges(db, source.id)
                dispatch = (
                    db.query(CodeEdge).filter_by(source_id=source.id, type="DISPATCHES_TO").all()
                )
                targets = [
                    db.get(CodeEntity, edge.dst_entity_id).qualified_name for edge in dispatch
                ]
                # Geerbt von der abstrakten Oberklasse; GroupOp hat zwei Implementierungen und bleibt offen.
                assert targets == ["p.AbstractLogic#create(String,boolean)"]
                assert (
                    dispatch[0].meta_json["declared_qualified_name"] == "p.AnyOp#create(C,boolean)"
                )
                assert dispatch[0].meta_json["dispatch_scope"] == "single_source_implementation"
        finally:
            db.delete(project)
            db.commit()
            db.delete(team)
            db.commit()
