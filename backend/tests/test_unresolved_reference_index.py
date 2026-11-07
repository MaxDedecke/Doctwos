"""Preserve uncertain name matches and the PostgreSQL access path."""

import pytest
from sqlalchemy import text
from sqlalchemy.schema import CreateIndex
from sqlalchemy.dialects.postgresql import dialect
from doctus_models.database import CodeEdge, CodeEntity, KnowledgeSource
from services.change_impact import inspect_change_impact


def test_migrated_index_matches_shared_model(db_session):
    definition = db_session.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname=current_schema() AND indexname='ix_code_edges_unresolved_project_name'"
        )
    ).scalar_one()
    model_index = next(
        i for i in CodeEdge.__table__.indexes if i.name == "ix_code_edges_unresolved_project_name"
    )
    ddl = str(CreateIndex(model_index).compile(dialect=dialect()))
    for sql in (definition, ddl):
        assert "project_id, lower(" in sql
        assert "dst_entity_id IS NULL" in sql
        assert "unresolved" in sql and "dynamic" in sql


@pytest.mark.parametrize("kind", ["method", "paragraph"])
def test_case_insensitive_uncertain_matches_keep_resolution_and_scope(
    db_session, test_project, test_team, kind
):
    source = KnowledgeSource(
        name="uncertain", type="Git", project_id=test_project, team_id=test_team
    )
    db_session.add(source)
    db_session.flush()
    target = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="target",
        name="PROCESS",
        type=kind,
        start_line=1,
        end_line=2,
    )
    caller = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="caller",
        name="CALLER",
        type=kind,
        start_line=1,
        end_line=2,
    )
    db_session.add_all([target, caller])
    db_session.flush()
    matches = []
    for resolution in ("unresolved", "dynamic"):
        edge = CodeEdge(
            project_id=test_project,
            source_id=source.id,
            src_entity_id=caller.id,
            dst_name="process",
            resolution=resolution,
            type="CALLS",
        )
        db_session.add(edge)
        matches.append(edge)
    # Same name, different project scope must remain excluded even with the new index.
    db_session.add(
        CodeEdge(
            project_id=None,
            source_id=source.id,
            src_entity_id=caller.id,
            dst_name="process",
            resolution="unresolved",
            type="CALLS",
        )
    )
    db_session.flush()
    result = inspect_change_impact(db_session, project_id=test_project, entity_id=target.id, hops=0)
    assert {edge["id"] for edge in result["edges"]} == {edge.id for edge in matches}
    assert {edge["resolution"] for edge in result["edges"]} == {"unresolved", "dynamic"}
    assert all(edge["target"] is None for edge in result["edges"])
