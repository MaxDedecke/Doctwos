"""Real Git revisions, database scopes and HTTP review paths."""

from pathlib import Path

import subprocess

import pytest
from doctus_models.database import (
    CodeEdge,
    CodeEntity,
    DocumentChunk,
    KnowledgeSource,
    SourceScanFile,
)
from doctus_models.insight_versions import version_state
from services.insight_context import retrieve_insight_context


@pytest.fixture
def version_repo(client, db_session, test_project, test_team, tmp_path, monkeypatch):
    from services import insight_commit_check

    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()

    git("init", "-b", "main")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.com")
    (tmp_path / "Worker.java").write_text(
        "class Worker {\n void run() { new Helper().work(); }\n}\n".replace("\\n", "\n")
    )
    (tmp_path / "Helper.java").write_text("class Helper { void work() {} }\n".replace("\\n", "\n"))
    git("add", ".")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    source = KnowledgeSource(
        name="main",
        type="Git",
        project_id=test_project,
        team_id=test_team,
        branch="main",
        repo_fingerprint="repo",
        sync_status="completed",
        sync_cursor={"last_commit": base},
    )
    db_session.add(source)
    db_session.flush()
    entities = []
    for path, name in [("Worker.java", "Worker"), ("Helper.java", "Helper")]:
        entity = CodeEntity(
            project_id=test_project,
            source_id=source.id,
            file_path=path,
            name=name,
            qualified_name=name,
            type="class",
            start_line=1,
            end_line=3,
        )
        chunk = DocumentChunk(
            project_id=test_project,
            source_id=source.id,
            file_path=path,
            content=(tmp_path / path).read_text(),
            content_hash=path,
        )
        db_session.add_all([entity, chunk])
        entities.append(entity)
    db_session.flush()
    db_session.add(
        CodeEdge(
            project_id=test_project,
            source_id=source.id,
            src_entity_id=entities[0].id,
            dst_entity_id=entities[1].id,
            dst_name="Helper",
            type="USES_TYPE",
            resolution="resolved",
        )
    )
    scan = SourceScanFile(
        source_id=source.id,
        file_path="Worker.java",
        content_hash="base",
        analysis_fingerprint="profile-a",
    )
    db_session.add(scan)
    db_session.commit()
    monkeypatch.setattr(insight_commit_check, "_git_worktree", lambda *args: tmp_path)
    response = client.post(
        f"/projects/{test_project}/insights",
        json={
            "title": "Worker transaction",
            "content": "The transaction belongs to the worker.",
            "origin_kind": "code",
            "evidence": [
                {
                    "entity_id": entities[0].id,
                    "source_id": source.id,
                    "file": "Worker.java",
                    "start_line": 1,
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    insight = response.json()
    url = f"/projects/{test_project}/insights/{insight['id']}/verify"
    response = client.post(
        url,
        json={
            "confirm": True,
            "expected_revision": insight["revision"],
            "expected_versions": insight["current_versions"],
        },
    )
    assert response.status_code == 200, response.text
    yield {
        "source": source,
        "base": base,
        "git": git,
        "path": tmp_path,
        "insight": response.json(),
        "url": url,
        "scan": scan,
    }


def test_new_commit_dependency_diff_and_explicit_reapproval(
    version_repo, client, db_session, test_project
):
    from doctus_models.database import Insight, User

    f = version_repo
    source = f["source"]
    bound = f["insight"]["version_bindings"][0]
    assert bound["commit"] == f["base"]
    assert bound["branch"] == "main"
    assert bound["dependency_files"] == ["Helper.java"]
    (f["path"] / "Helper.java").write_text(
        "class Helper { void work() { throw new RuntimeException(); } }"
    )
    f["git"]("add", ".")
    f["git"]("commit", "-m", "dependency changed")
    target = f["git"]("rev-parse", "HEAD")
    response = client.get(
        f"/projects/{test_project}/insights/commit-check",
        params={"source_id": source.id, "target_ref": target},
    )
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["target_indexed"] is False
    item = report["items"][0]
    assert item["result"] == "needs_review"
    assert item["can_verify"] is False
    assert item["files"][0]["kind"] == "dependency"
    assert "RuntimeException" in item["files"][0]["diff"]["text"]
    source.sync_cursor = {"last_commit": target}
    db_session.commit()
    insight = db_session.get(Insight, f["insight"]["id"])
    user = db_session.query(User).filter_by(username="test-fixture-user").one()
    assert version_state(db_session, insight) == "different_version"
    assert (
        retrieve_insight_context(
            db_session, user, test_project, "Worker transaction", source_id=source.id
        )
        == ""
    )
    stale = client.post(
        f["url"],
        json={
            "confirm": True,
            "expected_revision": insight.revision,
            "expected_versions": f["insight"]["current_versions"],
        },
    )
    assert stale.status_code == 409
    current = client.get(f"/projects/{test_project}/insights").json()[0]
    approved = client.post(
        f["url"],
        json={
            "confirm": True,
            "expected_revision": current["revision"],
            "expected_versions": current["current_versions"],
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["version_bindings"][0]["commit"] == target
    assert approved.json()["review_history"][-1]["version_bindings"][0]["commit"] == f["base"]
    assert "Worker transaction" in retrieve_insight_context(
        db_session, user, test_project, "Worker transaction", source_id=source.id
    )


def test_branch_profile_and_legacy_isolation(
    version_repo, client, db_session, test_project, test_team
):
    from doctus_models.database import Insight, User

    f = version_repo
    insight = db_session.get(Insight, f["insight"]["id"])
    user = db_session.query(User).filter_by(username="test-fixture-user").one()
    other = KnowledgeSource(
        name="release",
        type="Git",
        project_id=test_project,
        team_id=test_team,
        branch="release",
        repo_fingerprint="repo",
        sync_status="completed",
        sync_cursor={"last_commit": f["base"]},
    )
    db_session.add(other)
    db_session.commit()
    assert (
        retrieve_insight_context(
            db_session, user, test_project, "Worker transaction", source_id=other.id
        )
        == ""
    )
    f["scan"].analysis_fingerprint = "profile-b"
    db_session.commit()
    assert version_state(db_session, insight) == "different_version"
    stale = client.post(
        f["url"],
        json={
            "confirm": True,
            "expected_revision": insight.revision,
            "expected_versions": f["insight"]["current_versions"],
        },
    )
    assert stale.status_code == 409
    insight.version_bindings = None
    db_session.commit()
    assert version_state(db_session, insight) == "unbound"
    assert (
        retrieve_insight_context(
            db_session, user, test_project, "Worker transaction", source_id=f["source"].id
        )
        == ""
    )
    result = client.get(
        f"/projects/{test_project}/insights/commit-check",
        params={"source_id": f["source"].id, "target_ref": f["base"]},
    ).json()
    assert result["items"][0]["reason"] == "unbound"
    assert result["items"][0]["result"] == "unknown"


def test_commit_scope_pagination_and_deleted_evidence(
    version_repo, client, db_session, test_project
):
    f = version_repo
    (f["path"] / "Worker.java").unlink()
    f["git"]("add", ".")
    f["git"]("commit", "-m", "remove worker")
    params = {"source_id": f["source"].id, "target_ref": "HEAD", "limit": 1}
    result = client.get(f"/projects/{test_project}/insights/commit-check", params=params)
    assert result.status_code == 200
    assert result.json()["items"][0]["files"][0]["change"] == "D"
    assert (
        client.get(
            f"/projects/{test_project}/insights/commit-check",
            params={"source_id": 999999, "target_ref": "HEAD"},
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/projects/{test_project}/insights/commit-check",
            params={"source_id": f["source"].id, "target_ref": "--help"},
        ).status_code
        == 422
    )


def test_insight_evidence_inherits_and_rechecks_version_binding(
    version_repo, client, db_session, test_project
):
    f = version_repo
    response = client.post(
        f"/projects/{test_project}/insights",
        json={
            "title": "Worker policy",
            "content": "Reuse the reviewed transaction finding.",
            "origin_kind": "chat",
            "evidence": [{"insight_id": f["insight"]["id"]}],
        },
    )
    assert response.status_code == 201
    child = response.json()
    assert child["version_bindings"][0]["commit"] == f["base"]
    approved = client.post(
        f"/projects/{test_project}/insights/{child['id']}/verify",
        json={
            "confirm": True,
            "expected_revision": child["revision"],
            "expected_versions": child["current_versions"],
        },
    )
    assert approved.status_code == 200, approved.text
    # Revising the parent changes the derived finding's analysis context.
    parent = f["insight"]
    assert (
        client.post(
            f"/projects/{test_project}/insights/{parent['id']}/review",
            json={
                "action": "revise",
                "expected_revision": parent["revision"],
                "title": parent["title"],
                "content": "A corrected transaction rule.",
            },
        ).status_code
        == 200
    )
    from doctus_models.database import Insight

    derived = db_session.get(Insight, child["id"])
    assert version_state(db_session, derived) == "different_version"


def test_commit_pagination_does_not_include_other_branch(
    version_repo, client, db_session, test_project, test_team
):
    from doctus_models.database import Insight

    f = version_repo
    first = db_session.get(Insight, f["insight"]["id"])
    copy = Insight(
        project_id=test_project,
        title="Second",
        content="Second finding",
        origin_kind="code",
        evidence_json=first.evidence_json,
        created_by_id=first.created_by_id,
        version_bindings=first.version_bindings,
    )
    db_session.add(copy)
    db_session.commit()
    params = {"source_id": f["source"].id, "target_ref": "HEAD", "limit": 1}
    page = client.get(f"/projects/{test_project}/insights/commit-check", params=params).json()
    assert page["next_cursor"] == first.id
    next_page = client.get(
        f"/projects/{test_project}/insights/commit-check",
        params={**params, "after_id": page["next_cursor"]},
    ).json()
    assert next_page["items"][0]["id"] == copy.id
    assert next_page["next_cursor"] is None
    other = KnowledgeSource(
        name="release",
        type="Git",
        project_id=test_project,
        team_id=test_team,
        branch="release",
        sync_status="completed",
        sync_cursor={"last_commit": f["base"]},
    )
    db_session.add(other)
    db_session.commit()
    isolated = client.get(
        f"/projects/{test_project}/insights/commit-check",
        params={"source_id": other.id, "target_ref": "HEAD"},
    ).json()
    assert isolated["items"] == []


def test_empty_commit_invalidates_a_bound_approval(version_repo, db_session):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "parser"))
    from insight_review import mark_source_insights_outdated
    from doctus_models.database import Insight

    f = version_repo
    f["git"]("commit", "--allow-empty", "-m", "new revision")
    f["source"].sync_cursor = {"last_commit": f["git"]("rev-parse", "HEAD")}
    db_session.flush()
    assert mark_source_insights_outdated(db_session, f["source"]) == 1
    insight = db_session.get(Insight, f["insight"]["id"])
    assert insight.status == "outdated"
    assert insight.version_bindings[0]["commit"] == f["base"]


def test_commit_check_uses_the_same_scope_for_cobol(version_repo, client, db_session, test_project):
    f = version_repo
    path = f["path"] / "WORKER.cbl"
    path.write_text(
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. WORKER.\n       PROCEDURE DIVISION.\n           STOP RUN.\n".replace(
            "\\n", "\n"
        )
    )
    f["git"]("add", ".")
    f["git"]("commit", "-m", "COBOL base")
    f["source"].sync_cursor = {"last_commit": f["git"]("rev-parse", "HEAD")}
    entity = CodeEntity(
        project_id=test_project,
        source_id=f["source"].id,
        file_path="WORKER.cbl",
        name="WORKER",
        qualified_name="WORKER",
        type="program",
        start_line=1,
        end_line=4,
    )
    db_session.add(entity)
    db_session.add(
        DocumentChunk(
            project_id=test_project,
            source_id=f["source"].id,
            file_path="WORKER.cbl",
            content=path.read_text(),
            content_hash="cobol",
        )
    )
    db_session.commit()
    draft = client.post(
        f"/projects/{test_project}/insights",
        json={
            "title": "COBOL termination",
            "content": "The program stops here.",
            "origin_kind": "code",
            "evidence": [
                {"entity_id": entity.id, "source_id": f["source"].id, "file": "WORKER.cbl"}
            ],
        },
    ).json()
    assert (
        client.post(
            f"/projects/{test_project}/insights/{draft['id']}/verify",
            json={
                "confirm": True,
                "expected_revision": draft["revision"],
                "expected_versions": draft["current_versions"],
            },
        ).status_code
        == 200
    )
    path.write_text(
        path.read_text().replace("STOP RUN.", 'DISPLAY "changed".\n           STOP RUN.')
    )
    f["git"]("add", ".")
    f["git"]("commit", "-m", "COBOL change")
    report = client.get(
        f"/projects/{test_project}/insights/commit-check",
        params={"source_id": f["source"].id, "target_ref": "HEAD"},
    ).json()
    row = next(item for item in report["items"] if item["id"] == draft["id"])
    assert row["result"] == "needs_review"
    assert row["files"][0]["file"] == "WORKER.cbl"
