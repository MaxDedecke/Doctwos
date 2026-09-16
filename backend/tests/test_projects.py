"""
O-107: `api/projects.py` (977 Zeilen) hatte keinen eigenen Test. Der
Mitglieder-/Zugriffsanfragen-Teil ist über `test_project_membership.py`
abgedeckt -- diese Datei deckt die inhaltliche Hälfte ab, die andere Tests
bisher nur beiläufig als Fixture-Aufbau berührt haben: PATCH/DELETE/complete,
files/entities/stats/sync/references. Schwerpunkt ist dieselbe
Projektkontext-Isolation, die [O-032] sicherheitsrelevant gemacht hat --
wer im richtigen Team, aber nicht Mitglied des Projekts ist, darf dessen
Dateien/Entitäten/Statistiken/Referenzen nicht sehen.
"""

import os

import pytest

import api.projects as projects_api
from core.auth_dependency import SESSION_COOKIE_NAME, create_session_cookie_value
from models.database import (
    CodeEntity,
    DocumentChunk,
    EntityDocLink,
    KnowledgeLink,
    KnowledgeSource,
    Project,
    ProjectMembership,
    Team,
    TeamMembership,
    User,
)


@pytest.fixture
def project_member(test_project, db_session):
    """A non-admin member of `test_project`'s own team+project -- for asserting
    the admin-only write routes reject a plain member (403), distinct from
    the visibility check itself."""
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    user = User(
        username="test-projects-member",
        email="test-projects-member@example.com",
        name="Project Member",
        password_hash="x",
        role="user",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    db_session.add(TeamMembership(user_id=user.id, team_id=proj.team_id))
    db_session.add(ProjectMembership(user_id=user.id, project_id=proj.id, role="member"))
    db_session.commit()

    yield user

    db_session.query(ProjectMembership).filter(ProjectMembership.user_id == user.id).delete()
    db_session.query(TeamMembership).filter(TeamMembership.user_id == user.id).delete()
    db_session.query(User).filter(User.id == user.id).delete()
    db_session.commit()


@pytest.fixture
def team_member_without_project(test_project, db_session):
    """Same team as `test_project`, but never added as a project member -- the
    actual O-032-style gap: team visibility alone must not be enough to see a
    project's files/entities/stats/references."""
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    user = User(
        username="test-projects-team-only",
        email="test-projects-team-only@example.com",
        name="Team Only",
        password_hash="x",
        role="user",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    db_session.add(TeamMembership(user_id=user.id, team_id=proj.team_id))
    db_session.commit()

    yield user

    db_session.query(TeamMembership).filter(TeamMembership.user_id == user.id).delete()
    db_session.query(User).filter(User.id == user.id).delete()
    db_session.commit()


@pytest.fixture
def team_outsider(db_session):
    """A user in an entirely different team -- can't see `test_project` at
    all (assert_team_visible -- 404, not 403: knowing the project exists at
    all would itself leak org structure across team boundaries)."""
    foreign_team = Team(name="TestProjectsForeignTeam")
    db_session.add(foreign_team)
    db_session.commit()
    db_session.refresh(foreign_team)

    user = User(
        username="test-projects-outsider",
        email="test-projects-outsider@example.com",
        name="Team Outsider",
        password_hash="x",
        role="user",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    db_session.add(TeamMembership(user_id=user.id, team_id=foreign_team.id))
    db_session.commit()

    yield user

    db_session.query(TeamMembership).filter(TeamMembership.user_id == user.id).delete()
    db_session.query(User).filter(User.id == user.id).delete()
    db_session.delete(foreign_team)
    db_session.commit()


def _as(unauthenticated_client, user):
    unauthenticated_client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value(user.id))
    return unauthenticated_client


# ── PATCH /{id} ──────────────────────────────────────────────────────────────


def test_update_project_by_admin_updates_fields(client, db_session, test_project):
    res = client.patch(
        f"/projects/{test_project}",
        json={
            "name": "Renamed Project",
            "description": "Neue Beschreibung",
            "is_archived": True,
            "color": "#123456",
            "expose_code_analysis_globally": True,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Renamed Project"
    assert body["description"] == "Neue Beschreibung"
    assert body["is_archived"] is True
    assert body["color"] == "#123456"
    assert body["expose_code_analysis_globally"] is True

    proj = db_session.query(Project).filter(Project.id == test_project).first()
    assert proj.name == "Renamed Project"
    assert proj.is_archived is True


def test_update_project_omitted_fields_stay_untouched(client, db_session, test_project):
    original_description = (
        db_session.query(Project).filter(Project.id == test_project).first().description
    )

    res = client.patch(f"/projects/{test_project}", json={"color": "#abcdef"})
    assert res.status_code == 200
    body = res.json()
    assert body["color"] == "#abcdef"
    assert body["description"] == original_description


def test_update_project_rejects_non_admin_member(
    unauthenticated_client, test_project, project_member
):
    res = _as(unauthenticated_client, project_member).patch(
        f"/projects/{test_project}", json={"name": "Hijacked"}
    )
    assert res.status_code == 403


def test_update_project_rejects_team_outsider(unauthenticated_client, test_project, team_outsider):
    res = _as(unauthenticated_client, team_outsider).patch(
        f"/projects/{test_project}", json={"name": "Hijacked"}
    )
    assert res.status_code == 404


def test_update_project_unknown_id_404(client):
    res = client.patch("/projects/999999999", json={"name": "x"})
    assert res.status_code == 404


# ── DELETE /{id} ─────────────────────────────────────────────────────────────


def test_delete_project_cascades_sources_chunks_and_entities(client, db_session, test_project):
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    source = KnowledgeSource(
        name="Cascade Source",
        type="Confluence",
        project_id=test_project,
        team_id=proj.team_id,
        spaces={},
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    chunk = DocumentChunk(
        project_id=test_project,
        source_id=source.id,
        file_path="doc.md",
        content="x",
        start_line=1,
        end_line=2,
    )
    entity = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="doc.cbl",
        name="PROG",
        type="program",
        start_line=1,
        end_line=2,
    )
    db_session.add_all([chunk, entity])
    db_session.commit()
    chunk_id, entity_id, source_id = chunk.id, entity.id, source.id

    res = client.delete(f"/projects/{test_project}")
    assert res.status_code == 200

    assert db_session.query(Project).filter(Project.id == test_project).first() is None
    assert (
        db_session.query(ProjectMembership)
        .filter(ProjectMembership.project_id == test_project)
        .count()
        == 0
    )
    assert db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first() is None
    assert db_session.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first() is None
    assert db_session.query(CodeEntity).filter(CodeEntity.id == entity_id).first() is None


def test_delete_project_rejects_non_admin_member(
    unauthenticated_client, test_project, project_member
):
    res = _as(unauthenticated_client, project_member).delete(f"/projects/{test_project}")
    assert res.status_code == 403


def test_delete_project_unknown_id_404(client):
    res = client.delete("/projects/999999999")
    assert res.status_code == 404


# ── POST /{id}/complete ──────────────────────────────────────────────────────


def test_complete_project_promotes_selected_sources_and_archives(client, db_session, test_project):
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    source = KnowledgeSource(
        name="Promote Me",
        type="Confluence",
        project_id=test_project,
        team_id=proj.team_id,
        spaces={},
    )
    kept_source = KnowledgeSource(
        name="Stay Attached",
        type="Confluence",
        project_id=test_project,
        team_id=proj.team_id,
        spaces={},
    )
    db_session.add_all([source, kept_source])
    db_session.commit()
    db_session.refresh(source)
    db_session.refresh(kept_source)

    chunk = DocumentChunk(
        project_id=test_project,
        source_id=source.id,
        file_path="doc.md",
        content="x",
        start_line=1,
        end_line=2,
    )
    entity = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="doc.cbl",
        name="PROG",
        type="program",
        start_line=1,
        end_line=2,
    )
    db_session.add_all([chunk, entity])
    db_session.commit()

    try:
        res = client.post(
            f"/projects/{test_project}/complete", json={"promote_source_ids": [source.id]}
        )
        assert res.status_code == 200
        body = res.json()
        assert body["promoted_source_ids"] == [source.id]
        assert body["project"]["is_archived"] is True

        db_session.refresh(source)
        db_session.refresh(kept_source)
        db_session.refresh(chunk)
        db_session.refresh(entity)
        assert source.project_id is None
        assert kept_source.project_id == test_project
        # DocumentChunk/CodeEntity carry a denormalized project_id independent
        # of the source relationship -- both must clear on promotion, or the
        # promoted content stays invisible outside the project (see code comment).
        assert chunk.project_id is None
        assert entity.project_id is None
    finally:
        # Promotion moved these to project_id=None (global) -- they no longer
        # cascade-delete with the project at fixture teardown.
        db_session.delete(chunk)
        db_session.delete(entity)
        db_session.delete(source)
        db_session.commit()


def test_complete_project_without_promotion_only_archives(client, db_session, test_project):
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    source = KnowledgeSource(
        name="Stays Attached",
        type="Confluence",
        project_id=test_project,
        team_id=proj.team_id,
        spaces={},
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    res = client.post(f"/projects/{test_project}/complete", json={})
    assert res.status_code == 200
    body = res.json()
    assert body["promoted_source_ids"] == []
    assert body["project"]["is_archived"] is True

    db_session.refresh(source)
    assert source.project_id == test_project


def test_complete_project_rejects_source_ids_from_another_project(client, db_session, test_project):
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    other_project = Project(name="Other Project For Complete", team_id=proj.team_id)
    db_session.add(other_project)
    db_session.commit()
    db_session.refresh(other_project)
    foreign_source = KnowledgeSource(
        name="Foreign",
        type="Confluence",
        project_id=other_project.id,
        team_id=proj.team_id,
        spaces={},
    )
    db_session.add(foreign_source)
    db_session.commit()
    db_session.refresh(foreign_source)

    try:
        res = client.post(
            f"/projects/{test_project}/complete", json={"promote_source_ids": [foreign_source.id]}
        )
        assert res.status_code == 400
        db_session.refresh(foreign_source)
        assert foreign_source.project_id == other_project.id
    finally:
        db_session.delete(foreign_source)
        db_session.delete(other_project)
        db_session.commit()


def test_complete_project_rejects_non_admin_member(
    unauthenticated_client, test_project, project_member
):
    res = _as(unauthenticated_client, project_member).post(
        f"/projects/{test_project}/complete", json={}
    )
    assert res.status_code == 403


# ── GET /{id}/files ──────────────────────────────────────────────────────────


def test_list_project_files_without_git_source_returns_empty(client, test_project):
    res = client.get(f"/projects/{test_project}/files")
    assert res.status_code == 200
    assert res.json() == []


def test_list_project_files_lists_worktree_contents(
    client, db_session, test_project, tmp_path, monkeypatch
):
    monkeypatch.setattr(projects_api, "REPOS_ROOT", str(tmp_path))
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    source = KnowledgeSource(
        name="Git Source", type="Git", project_id=test_project, team_id=proj.team_id, spaces={}
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    worktree = tmp_path / "wt" / f"ks_{source.id}"
    (worktree / "src").mkdir(parents=True)
    (worktree / "src" / "ACCOUNT.cbl").write_text("       IDENTIFICATION DIVISION.\n")
    (worktree / "README.md").write_text("# demo\n")

    res = client.get(f"/projects/{test_project}/files")
    assert res.status_code == 200
    assert set(res.json()) == {os.path.join("src", "ACCOUNT.cbl"), "README.md"}


def test_list_project_files_requires_project_membership(
    unauthenticated_client, test_project, team_member_without_project
):
    res = _as(unauthenticated_client, team_member_without_project).get(
        f"/projects/{test_project}/files"
    )
    assert res.status_code == 403


def test_list_project_files_hides_project_from_team_outsider(
    unauthenticated_client, test_project, team_outsider
):
    res = _as(unauthenticated_client, team_outsider).get(f"/projects/{test_project}/files")
    assert res.status_code == 404


# ── GET /{id}/entities ───────────────────────────────────────────────────────


def test_get_project_entities_scoped_to_project_and_filterable_by_type(
    client, db_session, test_project
):
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    other_project = Project(name="Other Project For Entities", team_id=proj.team_id)
    db_session.add(other_project)
    db_session.commit()
    db_session.refresh(other_project)

    own_program = CodeEntity(
        project_id=test_project,
        file_path="ACCOUNT.cbl",
        name="ACCOUNT",
        type="program",
        start_line=1,
        end_line=10,
    )
    own_paragraph = CodeEntity(
        project_id=test_project,
        file_path="ACCOUNT.cbl",
        name="INIT-PARA",
        type="paragraph",
        start_line=2,
        end_line=4,
    )
    foreign_entity = CodeEntity(
        project_id=other_project.id,
        file_path="OTHER.cbl",
        name="OTHER",
        type="program",
        start_line=1,
        end_line=5,
    )
    db_session.add_all([own_program, own_paragraph, foreign_entity])
    db_session.commit()

    try:
        res = client.get(f"/projects/{test_project}/entities")
        assert res.status_code == 200
        assert {e["name"] for e in res.json()} == {"ACCOUNT", "INIT-PARA"}

        res = client.get(f"/projects/{test_project}/entities", params={"type": "paragraph"})
        assert res.status_code == 200
        assert {e["name"] for e in res.json()} == {"INIT-PARA"}
    finally:
        db_session.query(CodeEntity).filter(
            CodeEntity.id.in_([own_program.id, own_paragraph.id, foreign_entity.id])
        ).delete(synchronize_session=False)
        db_session.delete(other_project)
        db_session.commit()


def test_get_project_entities_requires_project_membership(
    unauthenticated_client, test_project, team_member_without_project
):
    res = _as(unauthenticated_client, team_member_without_project).get(
        f"/projects/{test_project}/entities"
    )
    assert res.status_code == 403


# ── GET /{id}/stats ──────────────────────────────────────────────────────────


def test_get_project_repository_stats_without_git_source_returns_zeros(client, test_project):
    res = client.get(f"/projects/{test_project}/stats")
    assert res.status_code == 200
    assert res.json() == {"total_files": 0, "total_lines": 0, "languages": []}


def test_get_project_repository_stats_counts_worktree_lines_by_language(
    client, db_session, test_project, tmp_path, monkeypatch
):
    monkeypatch.setattr(projects_api, "REPOS_ROOT", str(tmp_path))
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    source = KnowledgeSource(
        name="Git Source", type="Git", project_id=test_project, team_id=proj.team_id, spaces={}
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    worktree = tmp_path / "wt" / f"ks_{source.id}"
    worktree.mkdir(parents=True)
    (worktree / "main.py").write_text("a\nb\nc\n")
    (worktree / "README.md").write_text("x\n")

    res = client.get(f"/projects/{test_project}/stats")
    assert res.status_code == 200
    body = res.json()
    assert body["total_files"] == 2
    assert body["total_lines"] == 4
    languages = {language["name"]: language for language in body["languages"]}
    assert languages["Python"]["lines"] == 3
    assert languages["Markdown"]["lines"] == 1


def test_get_project_repository_stats_requires_project_membership(
    unauthenticated_client, test_project, team_member_without_project
):
    res = _as(unauthenticated_client, team_member_without_project).get(
        f"/projects/{test_project}/stats"
    )
    assert res.status_code == 403


# ── POST /{id}/sync ──────────────────────────────────────────────────────────


def test_sync_project_repository_without_git_source_404(client, test_project):
    res = client.post(f"/projects/{test_project}/sync")
    assert res.status_code == 404


def test_sync_project_repository_enqueues_task_and_resets_source_status(
    client, db_session, test_project, monkeypatch
):
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    source = KnowledgeSource(
        name="Git Source",
        type="Git",
        project_id=test_project,
        team_id=proj.team_id,
        spaces={},
        sync_status="completed",
        progress=100,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    sent_tasks = []
    monkeypatch.setattr(
        projects_api.celery_app,
        "send_task",
        lambda *args, **kwargs: sent_tasks.append((args, kwargs)),
    )

    res = client.post(f"/projects/{test_project}/sync")
    assert res.status_code == 200
    assert res.json() == {"message": "Synchronisierung gestartet", "repo_id": source.id}
    assert sent_tasks == [(("sync_source",), {"args": [source.id]})]

    db_session.refresh(source)
    assert source.sync_status == "pending"
    assert source.progress == 0


def test_sync_project_repository_requires_project_membership(
    unauthenticated_client, test_project, team_member_without_project
):
    res = _as(unauthenticated_client, team_member_without_project).post(
        f"/projects/{test_project}/sync"
    )
    assert res.status_code == 403


# ── GET /{id}/references ─────────────────────────────────────────────────────


def test_get_project_references_entity_doc_link_both_directions(client, db_session, test_project):
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    source = KnowledgeSource(
        name="Refs Source", type="Local", project_id=test_project, team_id=proj.team_id, spaces={}
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    entity = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="ACCOUNT.cbl",
        name="ACCOUNT-PARA",
        type="paragraph",
        start_line=10,
        end_line=20,
    )
    chunk = DocumentChunk(
        project_id=test_project,
        source_id=source.id,
        file_path="handbuch.md",
        content="Kontoführung",
        start_line=1,
        end_line=5,
    )
    db_session.add_all([entity, chunk])
    db_session.commit()
    db_session.refresh(entity)
    db_session.refresh(chunk)

    link = EntityDocLink(
        project_id=test_project,
        entity_id=entity.id,
        chunk_id=chunk.id,
        doc_title="handbuch.md",
        status="approved",
        link_type="manual",
    )
    db_session.add(link)
    db_session.commit()

    try:
        # Referenzen DES Dokuments -> das verlinkte Code-Objekt.
        res = client.get(
            f"/projects/{test_project}/references", params={"file_path": "handbuch.md"}
        )
        assert res.status_code == 200
        assert any(r["node_type"] == "entity" and r["name"] == "ACCOUNT-PARA" for r in res.json())

        # Referenzen DES Code-Objekts -> das verlinkte Dokument. entity_name grenzt
        # auf das angeklickte Objekt ein, sonst würde jede Entität der Datei
        # dieselben Referenzen melden (siehe Code-Kommentar in projects.py).
        res = client.get(
            f"/projects/{test_project}/references",
            params={"file_path": "ACCOUNT.cbl", "entity_name": "ACCOUNT-PARA"},
        )
        assert res.status_code == 200
        assert any(r["node_type"] == "document" and r["name"] == "handbuch.md" for r in res.json())
    finally:
        db_session.delete(link)
        db_session.delete(entity)
        db_session.delete(chunk)
        db_session.delete(source)
        db_session.commit()


def test_get_project_references_ignores_pending_links(client, db_session, test_project):
    entity = CodeEntity(
        project_id=test_project,
        file_path="PENDING.cbl",
        name="PENDING-PARA",
        type="paragraph",
        start_line=1,
        end_line=2,
    )
    chunk = DocumentChunk(
        project_id=test_project, file_path="pending.md", content="x", start_line=1, end_line=2
    )
    db_session.add_all([entity, chunk])
    db_session.commit()
    db_session.refresh(entity)
    db_session.refresh(chunk)

    link = EntityDocLink(
        project_id=test_project,
        entity_id=entity.id,
        chunk_id=chunk.id,
        doc_title="pending.md",
        status="pending",
    )
    db_session.add(link)
    db_session.commit()

    try:
        res = client.get(f"/projects/{test_project}/references", params={"file_path": "pending.md"})
        assert res.status_code == 200
        assert res.json() == []
    finally:
        db_session.delete(link)
        db_session.delete(entity)
        db_session.delete(chunk)
        db_session.commit()


def test_get_project_references_includes_approved_knowledge_link(client, db_session, test_project):
    entity = CodeEntity(
        project_id=test_project,
        file_path="ZINSBERECH.cbl",
        name="ZINS-BERECH",
        type="paragraph",
        start_line=5,
        end_line=9,
    )
    chunk = DocumentChunk(
        project_id=test_project,
        file_path="zinsformel.md",
        content="Zinsformel",
        start_line=1,
        end_line=3,
    )
    db_session.add_all([entity, chunk])
    db_session.commit()
    db_session.refresh(entity)
    db_session.refresh(chunk)

    link = KnowledgeLink(
        source_a_type="entity",
        source_a_entity_id=entity.id,
        source_a_title="ZINS-BERECH",
        source_b_type="document",
        source_b_chunk_id=chunk.id,
        source_b_title="zinsformel.md",
        status="approved",
        score=0.87,
    )
    db_session.add(link)
    db_session.commit()

    try:
        res = client.get(
            f"/projects/{test_project}/references",
            params={"file_path": "ZINSBERECH.cbl", "entity_name": "ZINS-BERECH"},
        )
        assert res.status_code == 200
        assert any(
            r["node_type"] == "document" and r["name"] == "zinsformel.md" for r in res.json()
        )
    finally:
        db_session.delete(link)
        db_session.delete(entity)
        db_session.delete(chunk)
        db_session.commit()


def test_get_project_references_requires_project_membership(
    unauthenticated_client, test_project, team_member_without_project
):
    res = _as(unauthenticated_client, team_member_without_project).get(
        f"/projects/{test_project}/references", params={"file_path": "ACCOUNT.cbl"}
    )
    assert res.status_code == 403
