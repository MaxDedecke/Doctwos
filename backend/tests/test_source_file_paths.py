"""Dateiinhalte einer Quelle: Ein übergebener Pfad bleibt in der Wurzel seiner Quelle."""

import pytest

import api.knowledge_sources as ks_api
from doctus_models.database import KnowledgeSource, Project


@pytest.fixture
def make_source(db_session, test_project):
    team_id = db_session.query(Project).filter(Project.id == test_project).first().team_id
    created = []

    def make(kind, spaces):
        source = KnowledgeSource(
            name=f"paths-{kind}", type=kind, project_id=test_project, team_id=team_id, spaces=spaces
        )
        db_session.add(source)
        db_session.commit()
        created.append(source)
        return source

    yield make
    for source in created:
        db_session.delete(source)
    db_session.commit()


@pytest.mark.parametrize("endpoint", ["content", "raw"])
def test_a_web_source_points_to_the_web_view_instead_of_reading_a_server_path(
    client, make_source, endpoint
):
    # Jira hält seine Projekte als Liste in `spaces`; das führte früher zu einem 500.
    source = make_source("Jira", ["SYNCOPE"])
    res = client.get(f"/knowledge-sources/{source.id}/{endpoint}", params={"path": "/etc/hostname"})
    assert res.status_code == 400


def test_a_git_path_cannot_leave_the_worktree(client, make_source, tmp_path, monkeypatch):
    monkeypatch.setattr(ks_api, "REPOS_ROOT", str(tmp_path))
    source = make_source("Git", {})
    worktree = tmp_path / "wt" / f"ks_{source.id}"
    worktree.mkdir(parents=True)
    (worktree / "README.md").write_text("Inhalt")
    (tmp_path / "secret.env").write_text("TOKEN=geheim")

    ok = client.get(f"/knowledge-sources/{source.id}/content", params={"path": "README.md"})
    assert ok.status_code == 200 and ok.json()["content"] == "Inhalt"
    for escape in ("../../secret.env", str(tmp_path / "secret.env")):
        res = client.get(f"/knowledge-sources/{source.id}/content", params={"path": escape})
        assert res.status_code == 404, escape


@pytest.mark.parametrize("endpoint", ["content", "raw"])
def test_a_folder_source_reads_only_below_the_watched_root(
    client, make_source, tmp_path, monkeypatch, endpoint
):
    watched = tmp_path / "watched"
    watched.mkdir()
    (watched / "notiz.txt").write_text("Notiz")
    (tmp_path / "outside.txt").write_text("draußen")
    monkeypatch.setattr(ks_api, "WATCHED_ROOT", str(watched))
    source = make_source("FolderWatch", {"folder_path": str(watched)})

    ok = client.get(
        f"/knowledge-sources/{source.id}/{endpoint}", params={"path": str(watched / "notiz.txt")}
    )
    assert ok.status_code == 200
    res = client.get(
        f"/knowledge-sources/{source.id}/{endpoint}", params={"path": str(tmp_path / "outside.txt")}
    )
    assert res.status_code == 404
