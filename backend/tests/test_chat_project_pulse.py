import pytest

from models.database import CodeEntity, Project, Team


@pytest.fixture
def pulse_project(db_session):
    team = Team(name="pulse-team")
    db_session.add(team)
    db_session.commit()
    project = Project(name="pulse-project", team_id=team.id)
    db_session.add(project)
    db_session.commit()
    db_session.add_all(
        [
            CodeEntity(project_id=project.id, name="PAYROLL", type="program", file_path="a.cbl", qualified_name="PAYROLL"),
            CodeEntity(project_id=project.id, name="ACCTREC", type="copybook", file_path="b.cpy", qualified_name="ACCTREC"),
            CodeEntity(project_id=project.id, name="MAIN-PARA", type="paragraph", file_path="a.cbl", qualified_name="PAYROLL.MAIN-PARA"),
        ]
    )
    db_session.commit()
    yield project
    db_session.query(CodeEntity).filter(CodeEntity.project_id == project.id).delete()
    db_session.query(Project).filter(Project.id == project.id).delete()
    db_session.query(Team).filter(Team.id == team.id).delete()
    db_session.commit()


def test_project_pulse_returns_counts_and_real_names(client, pulse_project):
    resp = client.get("/chat/project-pulse", params={"project_id": pulse_project.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"] == {"program": 1, "copybook": 1, "sql_table": 0, "jcl_job": 0}
    assert body["samples"]["program"] == ["PAYROLL"]
    assert body["samples"]["copybook"] == ["ACCTREC"]
    assert body["samples"]["sql_table"] == []


def test_project_pulse_requires_login(unauthenticated_client, pulse_project):
    resp = unauthenticated_client.get("/chat/project-pulse", params={"project_id": pulse_project.id})
    assert resp.status_code in (401, 403)
