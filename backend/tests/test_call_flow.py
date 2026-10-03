"""Regression coverage for the agent's directed call-flow tool."""

from models.database import CodeEdge, CodeEntity, KnowledgeSource
from services.call_flow import trace_call_flow
from api.callgraph import _focus
import pytest


def test_trace_call_flow_follows_only_the_requested_direction(db_session, test_project, test_team):
    source = KnowledgeSource(
        name="call-flow-source",
        type="Git",
        url="https://example.test/call-flow.git",
        branch="main",
        project_id=test_project,
        team_id=test_team,
    )
    db_session.add(source)
    db_session.flush()
    endpoint = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="api.py",
        name="get_order",
        qualified_name="get_order",
        type="function",
        start_line=10,
        end_line=20,
    )
    service = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="service.py",
        name="load_order",
        qualified_name="load_order",
        type="function",
        start_line=30,
        end_line=40,
    )
    repository = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="repository.py",
        name="find_order",
        qualified_name="find_order",
        type="function",
        start_line=50,
        end_line=60,
    )
    caller = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="job.py",
        name="warm_cache",
        qualified_name="warm_cache",
        type="function",
        start_line=1,
        end_line=8,
    )
    db_session.add_all([endpoint, service, repository, caller])
    db_session.flush()
    db_session.add_all(
        [
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=endpoint.id,
                dst_entity_id=service.id,
                dst_name="load_order",
                type="CALLS",
                resolution="resolved",
            ),
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=service.id,
                dst_entity_id=repository.id,
                dst_name="find_order",
                type="CALLS",
                resolution="resolved",
            ),
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=caller.id,
                dst_entity_id=endpoint.id,
                dst_name="get_order",
                type="CALLS",
                resolution="resolved",
            ),
        ]
    )
    db_session.commit()
    try:
        flow = trace_call_flow(
            db_session,
            project_id=test_project,
            entity_id=endpoint.id,
            hops=99,
            direction="outgoing",
        )

        assert flow["hops"] == 5
        assert {node["id"] for node in flow["nodes"]} == {endpoint.id, service.id, repository.id}
        assert {(edge["source"], edge["target"]) for edge in flow["edges"]} == {
            (endpoint.id, service.id),
            (service.id, repository.id),
        }
        assert "flowchart TD" in flow["mermaid"]
        assert "get_order (function)" in flow["mermaid"]
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_resource_flow_preserves_types_evidence_and_open_targets(
    db_session, test_project, test_team
):
    source = KnowledgeSource(
        name="resource-flow", type="Git", project_id=test_project, team_id=test_team
    )
    db_session.add(source)
    db_session.flush()
    nodes = [
        CodeEntity(
            project_id=test_project,
            source_id=source.id,
            file_path=path,
            name=name,
            qualified_name=name,
            type=kind,
            start_line=1,
            end_line=5,
        )
        for path, name, kind in [
            ("run.sh", "run", "shell_script"),
            ("Main.java", "main", "method"),
            ("report.xsl", "report", "xslt_stylesheet"),
        ]
    ]
    db_session.add_all(nodes)
    db_session.flush()
    for src, dst, kind, status, reason in [
        (nodes[0], nodes[1], "STARTS_JAVA", "resolved", "exact_resource_target"),
        (nodes[1], nodes[2], "USES_RESOURCE", "resolved", "exact_resource_target"),
        (nodes[1], None, "USES_RESOURCE", "unresolved", "resource_target_not_found"),
    ]:
        db_session.add(
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=src.id,
                dst_entity_id=dst.id if dst else None,
                dst_name=dst.name if dst else "missing.jsp",
                type=kind,
                resolution=status,
                src_start_line=3,
                src_end_line=3,
                meta_json={"resolution_reason": reason, "source_file_path": src.file_path},
            )
        )
    db_session.commit()
    try:
        for graph in [
            trace_call_flow(db_session, project_id=test_project, entity_id=nodes[0].id),
            _focus(db_session, nodes[0].id, 3),
        ]:
            edges = graph["edges"]
            assert len(edges) == 3
            assert {edge["type"] for edge in edges} == {"STARTS_JAVA", "USES_RESOURCE"}
            assert all(edge["start_line"] == 3 for edge in edges)
            assert (
                next(edge for edge in edges if edge["target"] is None)["meta"]["resolution_reason"]
                == "resource_target_not_found"
            )
        execution = trace_call_flow(
            db_session, project_id=test_project, entity_id=nodes[0].id, scope="execution"
        )
        # O-349: "dependencies" folgt nur Abhaengigkeitskanten. Vom Shell-Skript fuehrt
        # nur die Ausfuehrungskante STARTS_JAVA weg, die Ressourcen haengen an Main.java.
        dependencies = trace_call_flow(
            db_session, project_id=test_project, entity_id=nodes[1].id, scope="dependencies"
        )
        assert {edge["type"] for edge in execution["edges"]} == {"STARTS_JAVA"}
        assert {edge["type"] for edge in dependencies["edges"]} == {"USES_RESOURCE"}
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_execute_edges_are_classified_by_language_metadata(db_session, test_project):
    step = CodeEntity(
        project_id=test_project, name="STEP1", type="jcl_step", file_path="JOB.jcl"
    )
    jcl_target = CodeEntity(
        project_id=test_project, name="PROGRAM1", type="program", file_path="PROGRAM1.cbl"
    )
    cobol_operation = CodeEntity(
        project_id=test_project, name="EXEC-SQL", type="exec_operation", file_path="PROGRAM1.cbl"
    )
    db_session.add_all([step, jcl_target, cobol_operation])
    db_session.flush()
    edges = [
        CodeEdge(
            project_id=test_project, src_entity_id=step.id, dst_entity_id=jcl_target.id,
            dst_name="PROGRAM1", type="EXECUTES", resolution="resolved",
            meta_json={"language": "jcl"},
        ),
        CodeEdge(
            project_id=test_project, src_entity_id=step.id, dst_entity_id=cobol_operation.id,
            dst_name="EXEC-SQL", type="EXECUTES", resolution="resolved",
            meta_json={"language": "cobol"},
        ),
    ]
    db_session.add_all(edges)
    db_session.commit()
    try:
        execution = trace_call_flow(
            db_session, project_id=test_project, entity_id=step.id, scope="execution"
        )
        dependencies = trace_call_flow(
            db_session, project_id=test_project, entity_id=step.id, scope="dependencies"
        )
        assert [edge["target"] for edge in execution["edges"]] == [jcl_target.id]
        assert [edge["target"] for edge in dependencies["edges"]] == [cobol_operation.id]
    finally:
        db_session.query(CodeEdge).filter(CodeEdge.id.in_([edge.id for edge in edges])).delete(
            synchronize_session=False
        )
        db_session.query(CodeEntity).filter(
            CodeEntity.project_id == test_project,
            CodeEntity.id.in_([step.id, jcl_target.id, cobol_operation.id]),
        ).delete(synchronize_session=False)
        db_session.commit()


@pytest.mark.parametrize("mode", ["main", "single", "ambiguous", "empty", "incoming"])
def test_java_class_entry_selection(db_session, test_project, test_team, mode):
    source = KnowledgeSource(
        name="java-entry", type="Git", project_id=test_project, team_id=test_team
    )
    db_session.add(source)
    db_session.flush()
    root = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="QueryTransaction.java",
        name="QueryTransaction",
        qualified_name="QueryTransaction",
        type="class",
        start_line=1,
    )
    db_session.add(root)
    db_session.flush()
    methods = []
    for index, name in enumerate(
        [] if mode == "empty" else ["main"] if mode == "single" else ["main", "execute"]
    ):
        method = CodeEntity(
            project_id=test_project,
            source_id=source.id,
            file_path=root.file_path,
            parent_id=root.id,
            name=name,
            qualified_name=f"QueryTransaction#{name}()",
            type="method",
            start_line=index + 2,
            meta_json={
                "modifiers": ["public", "static"],
                "return_type": "void",
                "parameter_types": ["String[]"],
            }
            if mode == "main" and name == "main"
            else {},
        )
        db_session.add(method)
        methods.append(method)
    db_session.flush()
    if methods:
        db_session.add(
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=methods[0].id,
                dst_name="externalService",
                type="CALLS",
                resolution="unresolved",
            )
        )
    db_session.commit()
    try:
        flow = trace_call_flow(
            db_session,
            project_id=test_project,
            entity_id=root.id,
            direction="incoming" if mode == "incoming" else "outgoing",
        )
        assert flow["requested_root"]["id"] == root.id
        if mode in {"main", "single"}:
            assert flow["root"]["id"] == methods[0].id
            assert flow["entry_resolution"] == (
                "unique_java_main" if mode == "main" else "only_method"
            )
            assert flow["edges"][0]["resolution"] == "unresolved"
            assert "main (method)" in flow["mermaid"]
        elif mode == "ambiguous":
            assert flow["status"] == "entry_point_selection_required"
            assert {item["id"] for item in flow["entry_candidates"]} == {
                method.id for method in methods
            }
            assert flow["mermaid"] == ""
        else:
            assert flow["root"]["id"] == root.id
            assert flow["status"] == "no_indexed_calls"
            assert flow["notice"]
        assert "error" in trace_call_flow(db_session, project_id=-1, entity_id=root.id)
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_include_tests_false_hides_callers_from_test_code(db_session, test_project, test_team):
    """O-377: Aufrufer aus Testcode dürfen Impact-/Caller-Fragen nicht überdecken."""
    source = KnowledgeSource(
        name="call-flow-tests", type="Git", url="https://example.test/t.git", branch="main",
        project_id=test_project, team_id=test_team,
    )
    db_session.add(source)
    db_session.flush()

    def entity(path, name):
        item = CodeEntity(
            project_id=test_project, source_id=source.id, file_path=path, name=name,
            qualified_name=name, type="method", start_line=1, end_line=5,
        )
        db_session.add(item)
        db_session.flush()
        return item

    target = entity("core/src/main/java/OrderService.java", "load")
    prod = entity("core/src/main/java/OrderController.java", "get")
    unit = entity("core/src/test/java/OrderServiceTest.java", "shouldLoad")
    named = entity("core/src/main/java/FooIT.java", "run")
    lookalike = entity("core/src/main/java/EditService.java", "edit")
    for caller in (prod, unit, named, lookalike):
        db_session.add(CodeEdge(
            project_id=test_project, source_id=source.id, src_entity_id=caller.id,
            dst_entity_id=target.id, dst_name="load", type="CALLS", resolution="resolved",
        ))
    db_session.commit()
    try:
        everything = trace_call_flow(
            db_session, project_id=test_project, entity_id=target.id, hops=1, direction="incoming",
        )
        assert {edge["source"] for edge in everything["edges"]} == {
            prod.id, unit.id, named.id, lookalike.id,
        }
        production = trace_call_flow(
            db_session, project_id=test_project, entity_id=target.id, hops=1,
            direction="incoming", include_tests=False,
        )
        assert {edge["source"] for edge in production["edges"]} == {prod.id, lookalike.id}
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()
