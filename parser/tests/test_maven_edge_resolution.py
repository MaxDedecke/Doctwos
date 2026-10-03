"""Maven-Kanten zeigen auf die Deklaration derselben POM und sind damit aufgelöst; interne Projekte werden vermerkt."""
import pytest
from sqlalchemy import text

from db import SessionLocal
from models.database import CodeEdge, CodeEntity, KnowledgeSource
from tasks.edge_resolver import _resolve_maven_edges


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_declaration_edges_resolve_and_internal_projects_are_noted(db_session):
    team_id = db_session.execute(text("INSERT INTO teams (name, created_at) VALUES ('mvn-team', now()) RETURNING id")).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES ('mvn-proj', :t, now()) RETURNING id"), {"t": team_id},
    ).scalar_one()
    source = KnowledgeSource(name="mvn", type="git", project_id=project_id, team_id=team_id)
    db_session.add(source)
    db_session.flush()
    try:
        def entity(type_, name, path, qname, meta=None):
            row = CodeEntity(project_id=project_id, source_id=source.id, file_path=path, name=name, type=type_,
                             qualified_name=qname, start_line=1, end_line=1, meta_json={"language": "maven", "path": path, **(meta or {})})
            db_session.add(row)
            db_session.flush()
            return row

        parent = entity("maven_project", "parent", "pom.xml", "pom.xml", {"group_id": "org.demo", "artifact_id": "parent"})
        core = entity("maven_project", "demo-core", "core/pom.xml", "core/pom.xml", {"group_id": "org.demo", "artifact_id": "demo-core"})
        api = entity("maven_project", "demo-api", "api/pom.xml", "api/pom.xml", {"group_id": "org.demo", "artifact_id": "demo-api"})
        twin_a = entity("maven_project", "twin", "t1/pom.xml", "t1/pom.xml", {"group_id": "org.demo", "artifact_id": "twin"})
        entity("maven_project", "twin", "t2/pom.xml", "t2/pom.xml", {"group_id": "org.demo", "artifact_id": "twin"})
        module = entity("maven_module", "core", "pom.xml", "pom.xml::module:core")
        dep_internal = entity("maven_dependency", "demo-api", "core/pom.xml", "core/pom.xml::dependency:org.demo:demo-api",
                              {"group_id": "org.demo", "artifact_id": "demo-api"})
        dep_external = entity("maven_dependency", "spring-context", "core/pom.xml", "core/pom.xml::dependency:org.spring:spring-context",
                              {"group_id": "org.spring", "artifact_id": "spring-context"})
        dep_twin = entity("maven_dependency", "twin", "core/pom.xml", "core/pom.xml::dependency:org.demo:twin",
                          {"group_id": "org.demo", "artifact_id": "twin"})
        root = entity("maven_source_root", "src/main/java", "core/pom.xml", "core/pom.xml::source:src/main/java")

        def edge(type_, src, target, resolution="unresolved"):
            row = CodeEdge(project_id=project_id, source_id=source.id, src_entity_id=src.id, dst_name=target.qualified_name,
                           type=type_, resolution=resolution, meta_json={"language": "maven", "target_qualified_name": target.qualified_name})
            db_session.add(row)
            db_session.flush()
            return row

        e_module = edge("CONTAINS_MODULE", parent, module)
        e_internal = edge("DEPENDS_ON", core, dep_internal)
        e_external = edge("DEPENDS_ON", core, dep_external)
        e_twin = edge("DEPENDS_ON", core, dep_twin)
        e_root = edge("DECLARES_SOURCE_ROOT", core, root)
        missing = CodeEdge(project_id=project_id, source_id=source.id, src_entity_id=core.id, dst_name="x", type="USES_PLUGIN",
                           resolution="unresolved", meta_json={"language": "maven", "target_qualified_name": "core/pom.xml::plugin:gone"})
        db_session.add(missing)
        db_session.flush()

        assert _resolve_maven_edges(db_session, source.id) == 5
        db_session.flush()

        for item, target in ((e_module, module), (e_internal, dep_internal), (e_external, dep_external), (e_twin, dep_twin), (e_root, root)):
            assert (item.resolution, item.dst_entity_id) == ("resolved", target.id)
            assert item.meta_json["resolution_scope"] == "declaration"
        assert e_module.meta_json["internal_project"] == {"entity_id": core.id, "name": "demo-core", "path": "core/pom.xml"}
        assert e_internal.meta_json["internal_project"]["entity_id"] == api.id
        assert "internal_project" not in e_external.meta_json  # Bibliothek außerhalb des Quellstands
        assert "internal_project" not in e_twin.meta_json  # mehrdeutige Koordinaten: nichts geraten
        assert twin_a.id not in {e_twin.meta_json.get("internal_project", {}).get("entity_id")}
        assert missing.resolution == "unresolved"  # Deklaration fehlt: bleibt offen

        assert _resolve_maven_edges(db_session, source.id) == 0  # idempotent
    finally:
        db_session.rollback()
