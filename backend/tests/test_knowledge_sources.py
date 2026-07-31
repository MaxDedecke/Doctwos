import pytest

from models.database import KnowledgeSource, Project, ProjectMembership, User
from conftest import TEST_USERNAME


@pytest.fixture
def make_project(db_session, test_team):
    created_ids = []

    def _make_project() -> int:
        user = db_session.query(User).filter(User.username == TEST_USERNAME).first()
        proj = Project(name="test-project", team_id=test_team, creator_id=user.id)
        db_session.add(proj)
        db_session.commit()
        db_session.refresh(proj)
        
        membership = ProjectMembership(project_id=proj.id, user_id=user.id, role="admin")
        db_session.add(membership)
        db_session.commit()
        
        created_ids.append(proj.id)
        return proj.id

    yield _make_project

    for proj_id in created_ids:
        db_session.query(ProjectMembership).filter(ProjectMembership.project_id == proj_id).delete()
        db_session.query(Project).filter(Project.id == proj_id).delete()
    db_session.commit()


@pytest.fixture
def cleanup_unscoped_sources(db_session):
    """Tracks KnowledgeSource rows created without a project_id (not covered by project cascade-delete)."""
    created_ids = []
    yield created_ids
    if created_ids:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id.in_(created_ids)).delete(synchronize_session=False)
        db_session.commit()


def test_first_two_knowledge_sources_succeed(client, make_project):
    project_id = make_project()

    for i in range(2):
        resp = client.post("/knowledge-sources", json={
            "name": f"source-{i}", "type": "Local", "project_id": project_id
        })
        assert resp.status_code == 200, resp.text


def test_multiple_knowledge_sources_for_same_project_succeed(client, make_project):
    project_id = make_project()

    for i in range(5):
        resp = client.post("/knowledge-sources", json={
            "name": f"source-{i}", "type": "Local", "project_id": project_id
        })
        assert resp.status_code == 200, resp.text


def test_knowledge_source_without_project_is_unrestricted(client, cleanup_unscoped_sources):
    for i in range(3):
        resp = client.post("/knowledge-sources", json={
            "name": f"global-source-{i}", "type": "Local", "project_id": None
        })
        assert resp.status_code == 200, resp.text
        cleanup_unscoped_sources.append(resp.json()["id"])


def test_deleting_a_source(client, make_project):
    project_id = make_project()

    created_ids = []
    for i in range(2):
        resp = client.post("/knowledge-sources", json={
            "name": f"source-{i}", "type": "Local", "project_id": project_id
        })
        created_ids.append(resp.json()["id"])

    del_resp = client.delete(f"/knowledge-sources/{created_ids[0]}")
    assert del_resp.status_code == 200

    resp = client.post("/knowledge-sources", json={
        "name": "source-replacement", "type": "Local", "project_id": project_id
    })
    assert resp.status_code == 200, resp.text



def test_get_project_knowledge_sources_lists_only_attached(client, make_project):
    project_id = make_project()
    other_project_id = make_project()

    client.post("/knowledge-sources", json={"name": "a", "type": "Local", "project_id": project_id})
    client.post("/knowledge-sources", json={"name": "b", "type": "Local", "project_id": other_project_id})

    resp = client.get(f"/projects/{project_id}/knowledge-sources")
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert names == ["a"]
