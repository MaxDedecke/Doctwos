from pathlib import Path
from datetime import datetime, timezone
import subprocess

import pytest
from doctus_models.database import CodeEntity, Insight, KnowledgeSource
from services.build_evidence import BuildEvidence, summarize_build_evidence
from services.change_diff import _changed_entities
from services.change_package import inspect_change_package


def test_insight_revision_review_and_package(client, db_session, test_project):
    response = client.post(
        f"/projects/{test_project}/insights",
        json={
            "title": "Thread ownership",
            "content": "Keep the transaction in the worker.",
            "origin_kind": "code",
            "evidence": [{"file": "Executor.java", "source_id": None}],
        },
    )
    assert response.status_code == 201
    insight = response.json()
    base = f"/projects/{test_project}/insights/{insight['id']}"
    assert (
        client.post(base + "/verify", json={"confirm": True, "expected_revision": 1}).status_code
        == 200
    )
    item = db_session.get(Insight, insight["id"])
    item.status = "outdated"
    item.outdated_at = datetime.now(timezone.utc)
    item.revision += 1
    db_session.commit()
    assert (
        client.post(base + "/verify", json={"confirm": True, "expected_revision": 2}).status_code
        == 409
    )
    revised = client.post(
        base + "/review",
        json={
            "action": "revise",
            "expected_revision": 3,
            "title": "Thread ownership",
            "content": "Create the transaction inside the worker.",
        },
    )
    assert revised.status_code == 200
    assert revised.json()["status"] == "draft"
    assert revised.json()["review_history"][-1]["content"] == "Keep the transaction in the worker."
    assert (
        client.post(base + "/verify", json={"confirm": True, "expected_revision": 4}).status_code
        == 200
    )
    assert (
        client.post(base + "/review", json={"action": "reject", "expected_revision": 5}).status_code
        == 200
    )
    assert client.post(base + "/verify", json={"confirm": True}).status_code == 409


@pytest.mark.parametrize("kind,path", [("method", "Executor.java"), ("paragraph", "EXECUTOR.cbl")])
def test_package_includes_findings_by_evidence_with_status(
    db_session, test_project, test_team, kind, path
):
    source = KnowledgeSource(name="code", type="Git", project_id=test_project, team_id=test_team)
    db_session.add(source)
    db_session.flush()
    entity = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        name="execute",
        type=kind,
        file_path=path,
        start_line=1,
        end_line=10,
    )
    db_session.add(entity)
    db_session.flush()
    # Use a fixture user as author to satisfy the real audit FK.
    from doctus_models.database import User

    author = db_session.query(User).first()
    if author is None:
        author = User(username="workflow-author", email="workflow@example.com", role="superuser")
        db_session.add(author)
        db_session.flush()
    insight = Insight(
        project_id=test_project,
        title="Worker invariant",
        content="Transaction stays local",
        origin_kind="code",
        evidence_json=[{"entity_id": entity.id}],
        created_by_id=author.id,
    )
    db_session.add(insight)
    db_session.flush()
    package = inspect_change_package(
        db_session, project_id=test_project, entity_id=entity.id, hops=0
    )
    assert package["insights"][0]["id"] == insight.id
    assert package["insights"][0]["status"] == "draft"


def test_diff_selects_changed_method_instead_of_unchanged_sibling(
    db_session, test_project, test_team, tmp_path, monkeypatch
):
    from services import change_diff

    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()

    git("init")
    git("config", "user.email", "fixture@example.com")
    git("config", "user.name", "Fixture")
    file = tmp_path / "App.java"
    file.write_text(
        "class App {\n void changed() {\n  old();\n }\n void untouched() {}\n}\n".replace(
            "\\n", "\n"
        )
    )
    git("add", ".")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    file.write_text(file.read_text().replace("old();", "updated();"))
    git("add", ".")
    git("commit", "-m", "head")
    head = git("rev-parse", "HEAD")
    source = KnowledgeSource(name="diff", type="Git", project_id=test_project, team_id=test_team)
    db_session.add(source)
    db_session.flush()
    entities = []
    for name, start, end in [("App", 1, 6), ("changed", 2, 4), ("untouched", 5, 5)]:
        e = CodeEntity(
            project_id=test_project,
            source_id=source.id,
            name=name,
            type="class" if name == "App" else "method",
            file_path="App.java",
            start_line=start,
            end_line=end,
        )
        db_session.add(e)
        entities.append(e)
    db_session.flush()
    monkeypatch.setattr(change_diff, "_git_worktree", lambda *a: tmp_path)
    ids, ranges = _changed_entities(
        db_session,
        test_project,
        {
            "source_id": source.id,
            "indexed_files": ["App.java"],
            "base_commit": base,
            "head_commit": head,
        },
    )
    assert ids == [entities[1].id]
    assert ranges["App.java"][0]["start_line"] == 3


def test_build_artifacts_require_exact_source_revision(client, db_session, test_project, test_team):
    source = KnowledgeSource(
        name="build",
        type="Git",
        project_id=test_project,
        team_id=test_team,
        sync_status="completed",
        sync_cursor={"last_commit": "a" * 40},
    )
    db_session.add(source)
    db_session.flush()
    body = BuildEvidence(
        source_id=source.id,
        commit="a" * 40,
        effective_pom="<project><artifactId>app</artifactId><version>2</version></project>",
        dependency_tree={
            "artifactId": "app",
            "version": "2",
            "children": [{"artifactId": "lib", "version": "3", "scope": "compile"}],
        },
        active_profiles=["integration"],
        junit_xml="<testsuite><testcase/><testcase><failure/></testcase></testsuite>",
    )
    entity = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        name="run",
        type="method",
        file_path="App.java",
        start_line=1,
        end_line=3,
    )
    db_session.add(entity)
    db_session.commit()
    response = client.post(
        f"/projects/{test_project}/change-package?entity_id={entity.id}", json=body.model_dump()
    )
    assert response.status_code == 200, response.text
    assert response.json()["build_evidence"]["commit"] == body.commit
    summary = summarize_build_evidence(db_session, test_project, body)
    assert summary["dependencies"][1]["version"] == "3"
    assert summary["test_results"]["failure"] == 1
    with pytest.raises(ValueError, match="indexed"):
        summarize_build_evidence(
            db_session, test_project, body.model_copy(update={"commit": "b" * 40})
        )


def test_unchanged_evidence_file_survives_source_sync(db_session, test_project, test_team):
    from doctus_models.database import DocumentChunk, User
    from doctus_models.insight_evidence import snapshot_evidence
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "parser"))
    from insight_review import mark_source_insights_outdated

    author = db_session.query(User).first()
    if author is None:
        author = User(username="snapshot-author", email="snapshot@example.com", role="superuser")
        db_session.add(author)
        db_session.flush()
    source = KnowledgeSource(
        name="fingerprint", type="Git", project_id=test_project, team_id=test_team
    )
    db_session.add(source)
    db_session.flush()
    chunk = DocumentChunk(
        project_id=test_project,
        source_id=source.id,
        file_path="Worker.java",
        content="class Worker {}",
        content_hash="old-hash",
    )
    db_session.add(chunk)
    db_session.flush()
    evidence = snapshot_evidence(
        db_session, test_project, [{"source_id": source.id, "file": "Worker.java"}]
    )
    insight = Insight(
        project_id=test_project,
        title="Transaction",
        content="Keep local",
        origin_kind="code",
        evidence_json=evidence,
        status="verified",
        created_by_id=author.id,
        verified_by_id=author.id,
        verified_at=datetime.now(timezone.utc),
    )
    db_session.add(insight)
    db_session.flush()
    assert mark_source_insights_outdated(db_session, source) == 0
    chunk.content_hash = "new-hash"
    db_session.flush()
    assert mark_source_insights_outdated(db_session, source) == 1
    assert insight.status == "outdated"
