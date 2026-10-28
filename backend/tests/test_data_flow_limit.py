from models.database import CodeEntity, KnowledgeSource, User
from services.evidence import data_origin


def test_data_origin_reports_an_incomplete_table_even_without_a_matching_assignment(
    client, db_session, test_project, test_team
):
    source = KnowledgeSource(name="limited", type="Git", project_id=test_project, team_id=test_team)
    db_session.add(source)
    db_session.flush()
    routine = CodeEntity(
        source_id=source.id,
        project_id=test_project,
        file_path="C.java",
        name="use",
        qualified_name="C#use()",
        type="method",
        start_line=5,
        end_line=100,
        meta_json={
            "language": "java",
            "data_flow": [],
            "data_flow_truncated": True,
            "data_flow_omitted": 11,
        },
    )
    db_session.add(routine)
    db_session.flush()
    variable = CodeEntity(
        source_id=source.id,
        project_id=test_project,
        file_path="C.java",
        name="value",
        qualified_name="C#use()@local:value:90:1",
        type="local_variable",
        parent_id=routine.id,
        start_line=90,
        end_line=90,
    )
    db_session.add(variable)
    db_session.commit()
    try:
        user = db_session.query(User).filter_by(username="test-fixture-user").one()
        steps = data_origin(db_session, user, test_project, variable)
        assert steps == [
            {
                "field": "value",
                "file": "C.java",
                "line": 5,
                "cite": "C.java:5",
                "truncated": True,
                "operation": "analysis_limit",
                "reason": "data_flow_statement_limit",
                "omitted_statements": 11,
            }
        ]
    finally:
        db_session.delete(source)
        db_session.commit()
