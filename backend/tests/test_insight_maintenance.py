"""Team maintenance: bounded queues, assignments, targeted inbox and evidence revisions."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from core.auth_dependency import SESSION_COOKIE_NAME, create_session_cookie_value
from doctus_models.database import (
    Insight,
    InsightEmbedding,
    InsightNotification,
    ProjectMembership,
    TeamMembership,
    User,
)
from doctus_models.insight_workflow import content_hash, embedding_profile_key
from services.insight_context import current_insights
from test_insight_versions import version_repo as _version_repo

version_repo = _version_repo


@pytest.fixture
def people(db_session, test_project, test_team):
    rows = []
    for role in ("member", "admin"):
        user = User(username=f"work-{role}-{uuid4().hex}", role="user", is_active=True)
        db_session.add(user)
        db_session.flush()
        db_session.add_all(
            [
                TeamMembership(user_id=user.id, team_id=test_team),
                ProjectMembership(user_id=user.id, project_id=test_project, role=role),
            ]
        )
        rows.append(user)
    db_session.commit()
    yield rows
    db_session.query(Insight).filter_by(project_id=test_project).delete(synchronize_session=False)
    for user in rows:
        db_session.query(ProjectMembership).filter_by(user_id=user.id).delete()
        db_session.query(TeamMembership).filter_by(user_id=user.id).delete()
        db_session.delete(user)
    db_session.commit()


def as_user(client, user):
    client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value(user.id))


def test_assignment_uses_separate_revision_and_targets_inbox(
    version_repo, people, client, db_session, test_project
):
    row = client.get(f"/projects/{test_project}/insights/{version_repo['insight']['id']}").json()
    member, reviewer = people
    response = client.patch(
        f"/projects/{test_project}/insights/{row['id']}/assignment",
        json={
            "expected_revision": row["revision"],
            "expected_work_revision": row["work_revision"],
            "owner_id": member.id,
            "reviewer_id": reviewer.id,
            "priority": 3,
            "due_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["revision"] == row["revision"]
    assert updated["work_revision"] == row["work_revision"] + 1
    assert len(updated["workflow_history"]) == 1
    assert db_session.query(InsightNotification).filter_by(insight_id=row["id"]).count() == 2
    assert (
        client.patch(
            f"/projects/{test_project}/insights/{row['id']}/assignment",
            json={
                "expected_revision": row["revision"],
                "expected_work_revision": row["work_revision"],
            },
        ).status_code
        == 409
    )
    as_user(client, member)
    inbox = client.get(f"/projects/{test_project}/insight-notifications").json()
    assert inbox["unread_count"] == 1 and inbox["items"][0]["kind"] == "assigned"
    assert client.post(f"/projects/{test_project}/insight-notifications/read").json()["read"] == 1
    as_user(client, reviewer)
    assert client.get(f"/projects/{test_project}/insight-notifications").json()["unread_count"] == 1


def test_owned_revision_edits_evidence_and_keeps_old_proof(
    version_repo, people, client, db_session, test_project
):
    member, _ = people
    row = db_session.get(Insight, version_repo["insight"]["id"])
    row.owner_id = member.id
    db_session.commit()
    old_revision, old_evidence = row.revision, row.evidence_json
    as_user(client, member)
    url = f"/projects/{test_project}/insights/{row.id}"
    response = client.post(
        url + "/review",
        json={
            "action": "revise",
            "expected_revision": old_revision,
            "title": "New claim",
            "content": "The helper participates.",
            "evidence": [
                {
                    "file": "Helper.java",
                    "source_id": version_repo["source"].id,
                    "start_line": 1,
                    "end_line": 1,
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["status"] == "draft" and value["revision"] == old_revision + 1
    assert (
        value["evidence"][0]["file"] == "Helper.java" and value["evidence"][0]["file_fingerprint"]
    )
    assert value["review_history"][-1]["evidence"] == old_evidence
    assert value["version_bindings"][0]["files"] == ["Helper.java"]
    assert client.post(url + "/verify", json={"confirm": True}).status_code == 403
    assert (
        client.patch(
            url + "/assignment",
            json={
                "expected_revision": value["revision"],
                "expected_work_revision": 1,
                "owner_id": None,
            },
        ).status_code
        == 403
    )
    invalid = client.post(
        url + "/review",
        json={
            "action": "revise",
            "expected_revision": value["revision"],
            "title": "Invalid",
            "content": "Invalid",
            "evidence": [{"entity_id": 99999999}],
        },
    )
    assert invalid.status_code == 422
    assert client.get(url).json()["revision"] == value["revision"]


def test_source_change_is_coalesced_and_review_filter_finds_it(
    version_repo, people, client, db_session, test_project, monkeypatch
):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "parser"))
    from insight_review import mark_source_insights_outdated

    member, reviewer = people
    row = db_session.get(Insight, version_repo["insight"]["id"])
    row.owner_id, row.reviewer_id = member.id, reviewer.id
    source = version_repo["source"]
    source.sync_cursor = {"last_commit": "b" * 40}
    db_session.commit()
    assert mark_source_insights_outdated(db_session, source) == 1
    db_session.commit()
    assert mark_source_insights_outdated(db_session, source) == 0
    assert (
        db_session.query(InsightNotification)
        .filter_by(insight_id=row.id, kind="source_changed")
        .count()
        == 2
    )
    page = client.get(
        f"/projects/{test_project}/insight-worklist", params={"needs_review": True}
    ).json()
    assert page["items"][0]["needs_review"] and page["items"][0]["status"] == "outdated"


def test_worklist_is_bounded_searchable_and_prioritizes_due_tasks(client, db_session, test_project):
    actor = db_session.query(User).filter_by(username="test-fixture-user").one()
    now = datetime.now(timezone.utc)
    for i in range(10000):
        db_session.add(
            Insight(
                project_id=test_project,
                title=f"Searchable rule {i}",
                content="Unique relevance word",
                origin_kind="code",
                evidence_json=[{"file": "A.java"}],
                created_by_id=actor.id,
                owner_id=actor.id,
                status="draft",
                priority=3 if i == 50 else 1,
                due_at=now - timedelta(days=1) if i == 60 else None,
            )
        )
    db_session.commit()
    url = f"/projects/{test_project}/insight-worklist"
    first = client.get(url, params={"q": "Searchable", "limit": 25, "mine": True}).json()
    second = client.get(url, params={"q": "Searchable", "limit": 25, "offset": 25}).json()
    assert first["total"] == 10000 and len(first["items"]) == 25 and first["has_more"]
    assert first["items"][0]["title"] == "Searchable rule 60"
    assert first["items"][1]["title"] == "Searchable rule 50"
    assert not ({i["id"] for i in first["items"]} & {i["id"] for i in second["items"]})
    assert "content" not in first["items"][0] and "review_history" not in first["items"][0]
    assert len(client.get(f"/projects/{test_project}/insights").json()) == 100
    assert client.get(url, params={"q": "doesnotexist"}).json()["total"] == 0
    assert client.get(url, params={"limit": 5000}).status_code == 422


def test_evidence_options_and_assignment_reject_foreign_scope(
    version_repo, people, client, db_session, test_project
):
    source = version_repo["source"]
    options = client.get(
        f"/projects/{test_project}/insight-evidence-options", params={"q": "Worker", "kind": "code"}
    ).json()
    assert options["items"] and options["items"][0]["evidence"]["source_id"] == source.id
    row = version_repo["insight"]
    member, reviewer = people
    bad = client.patch(
        f"/projects/{test_project}/insights/{row['id']}/assignment",
        json={
            "expected_revision": row["revision"],
            "expected_work_revision": 1,
            "owner_id": member.id,
            "reviewer_id": member.id,
        },
    )
    assert bad.status_code == 422
    db_session.query(ProjectMembership).filter_by(
        user_id=reviewer.id, project_id=test_project
    ).delete()
    db_session.commit()
    as_user(client, reviewer)
    assert client.get(f"/projects/{test_project}/insight-worklist").status_code == 403
    assert client.get(f"/projects/{test_project}/insight-notifications").status_code == 403


def test_manual_batch_keeps_version_and_revision_checks(
    version_repo, client, db_session, test_project
):
    value = client.get(f"/projects/{test_project}/insights/{version_repo['insight']['id']}").json()
    # Explicitly revise, then confirm the displayed snapshot in the batch.
    response = client.post(
        f"/projects/{test_project}/insights/{value['id']}/review",
        json={
            "action": "revise",
            "expected_revision": value["revision"],
            "title": value["title"],
            "content": value["content"],
        },
    )
    value = response.json()
    items = [
        {
            "id": value["id"],
            "expected_revision": value["revision"],
            "expected_versions": value["current_versions"],
        }
    ]
    url = f"/projects/{test_project}/insight-batch-approval"
    assert client.post(url, json={"confirm": False, "items": items}).status_code == 422
    result = client.post(url, json={"confirm": True, "items": items}).json()
    assert result["items"][0]["status"] == "verified"
    again = client.post(url, json={"confirm": True, "items": items}).json()
    assert again["items"][0]["code"] == 409


def test_semantic_candidates_cross_wording_but_never_versions(
    version_repo, client, db_session, test_project, monkeypatch
):
    from services import answer_context, ollama_client

    row = db_session.get(Insight, version_repo["insight"]["id"])
    user = db_session.query(User).filter_by(username="test-fixture-user").one()
    profile = SimpleNamespace(
        provider="ollama",
        model="fixture",
        base_url="http://fixture",
        path=None,
        dimension=1024,
        context_length=8100,
        api_key=None,
    )
    key = embedding_profile_key(
        {
            "provider": "ollama",
            "model": "fixture",
            "base_url": "http://fixture",
            "path": None,
            "dimension": 1024,
            "context": 8100,
        }
    )
    vector = [1.0] + [0.0] * 1023
    db_session.add(
        InsightEmbedding(
            insight_id=row.id,
            project_id=test_project,
            profile_key=key,
            content_hash=content_hash(row),
            embedding=vector,
        )
    )
    db_session.commit()
    monkeypatch.setattr(answer_context, "_embedding_profile_for_project", lambda *a: profile)

    async def embed(*a, **kw):
        return vector

    monkeypatch.setattr(ollama_client, "embed_text", embed)
    result = current_insights(db_session, user, test_project, "Zahlungsabwicklung")
    assert [i.id for i in result] == [row.id]
    version_repo["source"].sync_cursor = {"last_commit": "b" * 40}
    db_session.commit()
    assert current_insights(db_session, user, test_project, "Zahlungsabwicklung") == []


def test_revision_of_referenced_claim_creates_a_targeted_task(
    version_repo, people, client, db_session, test_project
):
    row = db_session.get(Insight, version_repo["insight"]["id"])
    from doctus_models.insight_versions import capture_versions

    parent = Insight(
        project_id=test_project,
        title="Synthesis",
        content="Combined conclusion",
        origin_kind="chat",
        evidence_json=[{"insight_id": row.id}],
        status="verified",
        created_by_id=row.created_by_id,
        verified_by_id=row.verified_by_id,
        verified_at=row.verified_at,
        owner_id=people[0].id,
        version_bindings=capture_versions(db_session, test_project, [{"insight_id": row.id}]),
    )
    db_session.add(parent)
    db_session.commit()
    response = client.post(
        f"/projects/{test_project}/insights/{row.id}/review",
        json={
            "action": "revise",
            "expected_revision": row.revision,
            "title": "Changed",
            "content": "Changed conclusion",
        },
    )
    assert response.status_code == 200
    db_session.refresh(parent)
    assert parent.status == "outdated"
    assert (
        db_session.query(InsightNotification)
        .filter_by(insight_id=parent.id, user_id=people[0].id, kind="dependency_changed")
        .count()
        == 1
    )


def test_owner_requests_a_reviewer_without_assignment_privileges(
    version_repo, people, client, db_session, test_project
):
    member, reviewer = people
    row = db_session.get(Insight, version_repo["insight"]["id"])
    row.owner_id = member.id
    db_session.commit()
    original_revision = row.revision
    as_user(client, member)
    url = f"/projects/{test_project}/insights/{row.id}/assignment"
    request = {
        "expected_revision": row.revision,
        "expected_work_revision": row.work_revision,
        "reviewer_id": reviewer.id,
    }
    response = client.patch(url, json=request)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["owner_id"] == member.id and value["reviewer_id"] == reviewer.id
    assert value["revision"] == original_revision
    assert (
        client.patch(
            url, json={**request, "expected_work_revision": value["work_revision"], "priority": 3}
        ).status_code
        == 403
    )
    as_user(client, reviewer)
    response = client.get(f"/projects/{test_project}/insight-notifications")
    assert response.headers["Cache-Control"] == "no-store"
    notes = response.json()["items"]
    assert any(note["kind"] == "review_requested" for note in notes)
    note_id = notes[0]["id"]
    as_user(client, member)
    assert (
        client.post(f"/projects/{test_project}/insight-notifications/{note_id}/read").status_code
        == 404
    )
    as_user(client, reviewer)
    assert (
        client.post(f"/projects/{test_project}/insight-notifications/{note_id}/read").status_code
        == 200
    )
    assert client.get(f"/projects/{test_project}/insight-notifications").json()["unread_count"] == 0


def test_document_evidence_uses_source_scope_and_checks_lines(
    version_repo, client, db_session, test_project
):
    from doctus_models.database import DocumentChunk

    source = version_repo["source"]
    legacy = DocumentChunk(
        project_id=None,
        source_id=source.id,
        file_path="wiki/Contract",
        content="Rule one.\nRule two.",
        content_hash="legacy-wiki",
        start_line=1,
        end_line=2,
    )
    db_session.add(legacy)
    db_session.commit()
    items = client.get(
        f"/projects/{test_project}/insight-evidence-options",
        params={"q": "Contract", "kind": "file"},
    ).json()["items"]
    assert items and items[0]["evidence"]["source_id"] == source.id
    row = version_repo["insight"]
    body = {
        "action": "revise",
        "expected_revision": row["revision"],
        "title": "Contract rule",
        "content": "Rule two.",
        "evidence": [{"chunk_id": legacy.id, "start_line": 2, "end_line": 2}],
    }
    url = f"/projects/{test_project}/insights/{row['id']}/review"
    response = client.post(url, json=body)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["evidence"][0]["file"] == "wiki/Contract"
    assert value["evidence"][0]["file_fingerprint"]
    bad = {
        **body,
        "expected_revision": value["revision"],
        "evidence": [{"chunk_id": legacy.id, "start_line": 20}],
    }
    assert client.post(url, json=bad).status_code == 422
    assert (
        client.get(
            f"/projects/{test_project}/insight-worklist", params={"unassigned": True}
        ).json()["total"]
        == 0
    )
    assert client.get("/projects/99999999/insight-assignees").status_code == 404


def test_project_knowledge_becomes_an_unbound_task_when_git_is_added(
    version_repo, client, db_session, test_project
):
    row = db_session.get(Insight, version_repo["insight"]["id"])
    # Project knowledge approved before any Git source existed carries [].
    row.version_bindings = []
    row.evidence_json = [{"text": "Project decision recorded before Git was connected"}]
    db_session.commit()
    result = client.get(
        f"/projects/{test_project}/insight-worklist", params={"needs_review": True}
    ).json()
    assert result["total"] == 1
    assert result["items"][0]["id"] == row.id and result["items"][0]["version_state"] == "unbound"
