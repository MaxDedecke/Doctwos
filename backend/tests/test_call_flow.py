"""Regression coverage for the agent's directed call-flow tool."""

from models.database import CodeEdge, CodeEntity, KnowledgeSource
from services.call_flow import trace_call_flow


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
        project_id=test_project, source_id=source.id, file_path="api.py", name="get_order",
        qualified_name="get_order", type="function", start_line=10, end_line=20,
    )
    service = CodeEntity(
        project_id=test_project, source_id=source.id, file_path="service.py", name="load_order",
        qualified_name="load_order", type="function", start_line=30, end_line=40,
    )
    repository = CodeEntity(
        project_id=test_project, source_id=source.id, file_path="repository.py", name="find_order",
        qualified_name="find_order", type="function", start_line=50, end_line=60,
    )
    caller = CodeEntity(
        project_id=test_project, source_id=source.id, file_path="job.py", name="warm_cache",
        qualified_name="warm_cache", type="function", start_line=1, end_line=8,
    )
    db_session.add_all([endpoint, service, repository, caller])
    db_session.flush()
    db_session.add_all([
        CodeEdge(project_id=test_project, source_id=source.id, src_entity_id=endpoint.id, dst_entity_id=service.id, dst_name="load_order", type="CALLS", resolution="resolved"),
        CodeEdge(project_id=test_project, source_id=source.id, src_entity_id=service.id, dst_entity_id=repository.id, dst_name="find_order", type="CALLS", resolution="resolved"),
        CodeEdge(project_id=test_project, source_id=source.id, src_entity_id=caller.id, dst_entity_id=endpoint.id, dst_name="get_order", type="CALLS", resolution="resolved"),
    ])
    db_session.commit()
    try:
        flow = trace_call_flow(
            db_session, project_id=test_project, entity_id=endpoint.id, hops=99, direction="outgoing"
        )

        assert flow["hops"] == 5
        assert {node["id"] for node in flow["nodes"]} == {endpoint.id, service.id, repository.id}
        assert {(edge["source"], edge["target"]) for edge in flow["edges"]} == {
            (endpoint.id, service.id), (service.id, repository.id)
        }
        assert "flowchart TD" in flow["mermaid"]
        assert "get_order (function)" in flow["mermaid"]
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()
