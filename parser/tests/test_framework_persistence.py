import uuid

from db import SessionLocal
from java.parse import parse_java_file
from markup.parse import parse_xml_document
from models.database import CodeEdge, CodeEntity, KnowledgeSource, Project, Team
from structure_persist import persist_parse_result
from tasks.edge_resolver import resolve_global_edges


def test_endpoints_injection_dispatch_xml_and_repeated_resolution_survive_persistence():
    db = SessionLocal()
    team = Team(name="framework-" + uuid.uuid4().hex)
    db.add(team)
    db.flush()
    project = Project(name="framework-" + uuid.uuid4().hex, team_id=team.id)
    db.add(project)
    db.flush()
    source = KnowledgeSource(
        project_id=project.id, team_id=team.id, name="frameworks", type="Git", url="local"
    )
    db.add(source)
    db.commit()
    try:
        result = parse_java_file(
            """package app;
import jakarta.inject.*; import jakarta.enterprise.context.*;
import org.springframework.web.bind.annotation.*;
interface Port { void send(); }
@ApplicationScoped @Named("fast") class Fast implements Port { public void send() {} }
@RestController @RequestMapping("/orders") class Client {
 @Inject @Named("fast") Port port;
 @PostMapping public void send() { port.send(); }
}""",
            "app/src/main/java/app/Client.java",
        )
        persist_parse_result(
            db,
            source_id=source.id,
            project_id=project.id,
            file_path=result.path,
            content_hash="frameworks",
            result=result,
        )
        xml = parse_xml_document(
            '<beans xmlns="http://www.springframework.org/schema/beans"><bean id="xmlFast" class="app.Fast"/></beans>',
            "app/src/main/resources/beans.xml",
        )
        persist_parse_result(
            db,
            source_id=source.id,
            project_id=project.id,
            file_path=xml.path,
            content_hash="configuration",
            result=xml,
        )
        db.commit()
        for _ in range(2):
            resolve_global_edges(db, source.id)
            edges = db.query(CodeEdge).filter(CodeEdge.source_id == source.id).all()
            assert len([e for e in edges if e.type == "EXPOSES"]) == 1
            assert len([e for e in edges if e.type == "INJECTS"]) == 1
            assert len([e for e in edges if e.type == "DISPATCHES_TO"]) == 1
            assert next(e for e in edges if e.type == "CONFIGURES").resolution == "resolved"
            dispatch = next(e for e in edges if e.type == "DISPATCHES_TO")
            assert db.get(CodeEntity, dispatch.dst_entity_id).qualified_name == "app.Fast#send()"
    finally:
        db.delete(project)
        db.commit()
        db.delete(team)
        db.commit()
        db.close()
