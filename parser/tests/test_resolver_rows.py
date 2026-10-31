"""Der Nachlauf lädt große Metadaten nicht und darf sie beim Zurückschreiben nicht verlieren."""

import uuid

from doctus_models.database import CodeEdge, CodeEntity, KnowledgeSource, Project, Team

from db import SessionLocal
from java.parse import parse_java_file
from structure_persist import persist_parse_result
from tasks.edge_resolver import (
    UNREAD_JAVA_EDGE_META,
    UNREAD_JAVA_ENTITY_META,
    java_entity_rows,
    resolve_global_edges,
)
from tasks.resolver_rows import share, slim_meta

_A = """package app;
public class A {
    public int run(int value) {
        int doubled = value * 2;
        return new B().twice(doubled);
    }
}
"""
_B = """package app;
public class B {
    public int twice(int value) { return value * 2; }
}
"""


def test_slim_meta_drops_only_named_fields_and_shares_equal_texts():
    first = slim_meta({"keep": "app.Klasse", "data_flow": [1]}, frozenset({"data_flow"}))
    second = slim_meta({"keep": "".join(["app.", "Klasse"])})
    assert first == {"keep": "app.Klasse"}
    assert first["keep"] is second["keep"]
    long_text = "x" * 1000
    assert share({"a": [long_text]}) == {"a": [long_text]}


def test_resolving_keeps_metadata_it_did_not_load():
    db = SessionLocal()
    team = Team(name="resolver-rows-" + uuid.uuid4().hex)
    db.add(team)
    db.flush()
    project = Project(name="resolver-rows-" + uuid.uuid4().hex, team_id=team.id)
    db.add(project)
    db.flush()
    source = KnowledgeSource(
        name="rows", type="Git", url="file:///rows", project_id=project.id, team_id=team.id
    )
    db.add(source)
    db.commit()
    try:
        for path, text in (("src/main/java/app/A.java", _A), ("src/main/java/app/B.java", _B)):
            persist_parse_result(
                db,
                source_id=source.id,
                project_id=project.id,
                file_path=path,
                content_hash=path,
                result=parse_java_file(text, path),
            )
        db.commit()
        method = next(
            entity
            for entity in db.query(CodeEntity).filter_by(source_id=source.id, type="method")
            if "#run(" in entity.qualified_name
        )
        method.meta_json = {**method.meta_json, "data_flow": [{"marker": "bleibt"}]}
        call = next(
            edge
            for edge in db.query(CodeEdge).filter_by(source_id=source.id, type="CALLS")
            if edge.meta_json.get("method_name") == "twice"
        )
        call.meta_json = {
            **call.meta_json,
            "argument_refs": [{"marker": "bleibt"}],
            "control_path": ["bleibt"],
        }
        call_id, method_id = call.id, method.id
        db.commit()

        resolve_global_edges(db, source.id)
        db.commit()
        db.expire_all()

        call = db.get(CodeEdge, call_id)
        assert call.resolution == "resolved"
        assert "#twice(" in db.get(CodeEntity, call.dst_entity_id).qualified_name
        assert "#twice(" in call.meta_json["target_qualified_name"]
        assert call.meta_json["argument_refs"] == [{"marker": "bleibt"}]
        assert call.meta_json["control_path"] == ["bleibt"]
        method = db.get(CodeEntity, method_id)
        assert method.meta_json["data_flow"] == [{"marker": "bleibt"}]

        rows = java_entity_rows(db, source.id, UNREAD_JAVA_ENTITY_META)
        assert all(not (UNREAD_JAVA_ENTITY_META & row.meta_json.keys()) for row in rows)
        assert "control_path" in UNREAD_JAVA_EDGE_META
        # Ein zweiter Lauf ändert nichts mehr und bleibt stabil.
        resolve_global_edges(db, source.id)
        db.commit()
        db.expire_all()
        assert db.get(CodeEdge, call_id).resolution == "resolved"
    finally:
        db.rollback()
        db.delete(project)
        db.commit()
        db.delete(team)
        db.commit()
        db.close()
