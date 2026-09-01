import os

import pytest

from core.config import UPLOADS_DIR
from models.database import KnowledgeSource, Project, ProjectMembership, SourceScanFile, Team, User
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



def test_deleting_a_source_with_scan_file_journal_succeeds(client, make_project, db_session):
    """Regression: eine synchronisierte Quelle (Git/Confluence/Jira/WebDAV) hinterlaesst
    source_scan_files-Zeilen (source_id NOT NULL). Ohne passive_deletes=True auf
    SourceScanFile.knowledge_source versucht SQLAlchemy beim Loeschen, source_id per
    UPDATE auf NULL zu setzen statt die DB-CASCADE greifen zu lassen -> IntegrityError,
    reproduzierbar u.a. bei jedem Git-Quellen-Delete nach abgeschlossenem Sync."""
    project_id = make_project()

    resp = client.post("/knowledge-sources", json={
        "name": "git-source", "type": "Git", "project_id": project_id
    })
    source_id = resp.json()["id"]

    db_session.add(SourceScanFile(
        source_id=source_id, file_path="src/FOO.cbl", content_hash="abc123", parse_status="ok",
    ))
    db_session.commit()

    del_resp = client.delete(f"/knowledge-sources/{source_id}")
    assert del_resp.status_code == 200, del_resp.text


def test_get_project_knowledge_sources_lists_only_attached(client, make_project):
    project_id = make_project()
    other_project_id = make_project()

    client.post("/knowledge-sources", json={"name": "a", "type": "Local", "project_id": project_id})
    client.post("/knowledge-sources", json={"name": "b", "type": "Local", "project_id": other_project_id})

    resp = client.get(f"/projects/{project_id}/knowledge-sources")
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert names == ["a"]


def test_project_knowledge_sources_require_project_membership(member_client, db_session):
    """Team membership alone must not grant access to a project's sources."""
    member = db_session.query(User).filter(User.username == "test-fixture-member").first()
    team = db_session.query(Team).filter(Team.name == "Default Team").first()
    project = Project(name="membership-gated-source-project", team_id=team.id)
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    source = KnowledgeSource(
        name="membership-gated-source",
        type="Local",
        project_id=project.id,
        team_id=team.id,
        spaces={},
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    try:
        listed = member_client.get("/knowledge-sources")
        assert listed.status_code == 200
        assert source.id not in {item["id"] for item in listed.json()}

        assert member_client.get(f"/knowledge-sources/{source.id}/files").status_code == 403
        assert member_client.patch(
            f"/knowledge-sources/{source.id}", json={"context_note": "nope"}
        ).status_code == 403
        assert member_client.delete(f"/knowledge-sources/{source.id}").status_code == 403
        assert member_client.post(
            "/knowledge-sources", json={
                "name": "unauthorized-source",
                "type": "Local",
                "project_id": project.id,
            }
        ).status_code == 403
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.query(Project).filter(Project.id == project.id).delete()
        db_session.commit()


def test_model_selection_is_global_admin_only(member_client):
    response = member_client.post("/model-info", json={"llm": "not-authorized"})
    assert response.status_code == 403


def test_upload_local_document_creates_source_and_saves_file(client, make_project, db_session):
    project_id = make_project()

    resp = client.post(
        "/knowledge-sources/upload",
        data={"name": "Handbuch.txt", "project_id": str(project_id)},
        files={"file": ("Handbuch.txt", b"COBOL Betriebshandbuch Inhalt", "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["type"] == "Local"
    assert body["name"] == "Handbuch.txt"

    source = db_session.query(KnowledgeSource).filter(KnowledgeSource.id == body["id"]).first()
    assert source is not None
    assert source.spaces["filename"] == "Handbuch.txt"

    expected_path = os.path.join(UPLOADS_DIR, f"{source.id}_Handbuch.txt")
    assert os.path.isfile(expected_path)
    with open(expected_path, "rb") as f:
        assert f.read() == b"COBOL Betriebshandbuch Inhalt"

    os.remove(expected_path)
    db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
    db_session.commit()


def test_upload_local_document_sanitizes_path_traversal_in_filename(client, make_project, db_session):
    """F-018: der Dateiname kommt vom Client (multipart filename) -- os.path.basename()
    muss einen Pfad wie '../../etc/passwd' auf den reinen Dateinamen kappen, sonst
    könnte der Upload außerhalb von UPLOADS_DIR schreiben."""
    project_id = make_project()

    resp = client.post(
        "/knowledge-sources/upload",
        data={"name": "evil", "project_id": str(project_id)},
        files={"file": ("../../etc/passwd", b"harmless", "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    source = db_session.query(KnowledgeSource).filter(KnowledgeSource.id == body["id"]).first()
    assert source is not None
    assert ".." not in source.spaces["path"]

    expected_path = os.path.join(UPLOADS_DIR, f"{source.id}_passwd")
    assert os.path.isfile(expected_path)

    os.remove(expected_path)
    db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
    db_session.commit()
