"""
Tests für backend/api/entity_links.py (O-108).

Der Link Manager (388/426 Zeilen, 9 Routen) hatte bislang keinen einzigen
Testaufruf. Schwerpunkte:
  - Empfehlung anlegen (manuell), per LLM neu bewerten, löschen.
  - Projektkontext-Isolation je Route (dieselbe O-032-Klasse wie in
    test_projects.py: Team-Sichtbarkeit allein darf nicht reichen, wer nicht
    Projektmitglied ist, bekommt 403; ein Team-Fremder bekommt 404).
  - llm-review mit deaktiviertem lokalen LLM liefert eine definierte 502-Antwort
    statt eines unbehandelten 500, und das Cloud-Provider-Opt-in-Gate greift
    wie in api/chat.py.

Die Oberfläche darüber (`LinkManagerView`) ist seit O-060 getestet — hier
fehlt die Gegenseite.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import api.entity_links as entity_links_api
from core.auth_dependency import SESSION_COOKIE_NAME, create_session_cookie_value
from models.database import (
    CodeEntity,
    DocumentChunk,
    EntityDocLink,
    KnowledgeSource,
    LinkBuilderRun,
    Project,
    ProjectMembership,
    Team,
    TeamMembership,
    User,
)


@pytest.fixture
def project_member(test_project, db_session):
    """Non-admin member of `test_project`'s own team+project."""
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    user = User(
        username="test-entity-links-member",
        email="test-entity-links-member@example.com",
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
    """Same team as `test_project`, but never added as a project member — the
    O-032-style gap: team visibility alone must not be enough."""
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    user = User(
        username="test-entity-links-team-only",
        email="test-entity-links-team-only@example.com",
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
    """A user in an entirely different team — can't see `test_project` at
    all (404, not 403: existence itself would leak org structure)."""
    foreign_team = Team(name="TestEntityLinksForeignTeam")
    db_session.add(foreign_team)
    db_session.commit()
    db_session.refresh(foreign_team)

    user = User(
        username="test-entity-links-outsider",
        email="test-entity-links-outsider@example.com",
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


@pytest.fixture
def source_entity_chunk(test_project, db_session):
    """A KnowledgeSource + one CodeEntity + one DocumentChunk in `test_project` —
    the minimal fixture most routes here need."""
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    source = KnowledgeSource(
        name="Link Source", type="Local", project_id=test_project, team_id=proj.team_id, spaces={}
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
        content="Kontoführung im Detail.",
        start_line=1,
        end_line=5,
        metadata_json={"title": "Handbuch Kontoführung"},
    )
    db_session.add_all([entity, chunk])
    db_session.commit()
    db_session.refresh(entity)
    db_session.refresh(chunk)

    yield source, entity, chunk

    db_session.query(EntityDocLink).filter(EntityDocLink.entity_id == entity.id).delete()
    db_session.delete(entity)
    db_session.delete(chunk)
    db_session.delete(source)
    db_session.commit()


def _make_link(db_session, project_id, entity, chunk=None, **overrides):
    defaults = dict(
        project_id=project_id,
        entity_id=entity.id,
        chunk_id=chunk.id if chunk else None,
        doc_title=chunk.file_path if chunk else "manual-doc.md",
        status="pending",
        link_type="semantic",
        score=0.5,
    )
    defaults.update(overrides)
    link = EntityDocLink(**defaults)
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)
    return link


# ── GET /projects/{id}/link-recommendations ─────────────────────────────────


def test_get_link_recommendations_lists_links_with_counts(
    client, db_session, test_project, source_entity_chunk
):
    source, entity, chunk = source_entity_chunk
    pending = _make_link(db_session, test_project, entity, chunk, status="pending", score=0.9)
    approved = _make_link(db_session, test_project, entity, chunk, status="approved", score=0.4)
    try:
        res = client.get(f"/projects/{test_project}/link-recommendations")
        assert res.status_code == 200
        body = res.json()
        assert body["counts"] == {"pending": 1, "approved": 1, "rejected": 0}
        ids = {lnk["id"] for lnk in body["links"]}
        assert {pending.id, approved.id} <= ids
        # entity is preloaded (no N+1) and serialized alongside each link.
        served = next(lnk for lnk in body["links"] if lnk["id"] == pending.id)
        assert served["entity"]["name"] == "ACCOUNT-PARA"
    finally:
        db_session.query(EntityDocLink).filter(
            EntityDocLink.id.in_([pending.id, approved.id])
        ).delete(synchronize_session=False)
        db_session.commit()


def test_get_link_recommendations_filters_by_status_and_min_score(
    client, db_session, test_project, source_entity_chunk
):
    source, entity, chunk = source_entity_chunk
    low = _make_link(db_session, test_project, entity, chunk, status="pending", score=0.1)
    high = _make_link(db_session, test_project, entity, chunk, status="pending", score=0.9)
    approved = _make_link(db_session, test_project, entity, chunk, status="approved", score=0.9)
    try:
        res = client.get(
            f"/projects/{test_project}/link-recommendations", params={"status": "pending"}
        )
        ids = {lnk["id"] for lnk in res.json()["links"]}
        assert ids == {low.id, high.id}

        res = client.get(
            f"/projects/{test_project}/link-recommendations",
            params={"status": "pending", "min_score": 0.5},
        )
        ids = {lnk["id"] for lnk in res.json()["links"]}
        assert ids == {high.id}
    finally:
        db_session.query(EntityDocLink).filter(
            EntityDocLink.id.in_([low.id, high.id, approved.id])
        ).delete(synchronize_session=False)
        db_session.commit()


def test_get_link_recommendations_rejects_team_member_without_project(
    unauthenticated_client, test_project, team_member_without_project
):
    res = _as(unauthenticated_client, team_member_without_project).get(
        f"/projects/{test_project}/link-recommendations"
    )
    assert res.status_code == 403


def test_get_link_recommendations_hides_project_from_team_outsider(
    unauthenticated_client, test_project, team_outsider
):
    res = _as(unauthenticated_client, team_outsider).get(
        f"/projects/{test_project}/link-recommendations"
    )
    assert res.status_code == 404


# ── POST /projects/{id}/link-recommendations (manual link) ─────────────────


def test_create_manual_link(client, db_session, test_project, source_entity_chunk):
    source, entity, chunk = source_entity_chunk
    res = client.post(
        f"/projects/{test_project}/link-recommendations",
        json={
            "entity_id": entity.id,
            "doc_title": "handbuch.md",
            "doc_url": "https://example.test/handbuch.md",
            "source_type": "Local",
            "context": "Beschreibt genau diese Buchung.",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "approved"
    assert body["link_type"] == "manual"
    assert body["created_by"] == "user"
    assert body["context"] == "Beschreibt genau diese Buchung."

    link = db_session.query(EntityDocLink).filter(EntityDocLink.id == body["id"]).first()
    assert link is not None
    db_session.delete(link)
    db_session.commit()


def test_create_manual_link_for_unknown_entity_is_404(client, test_project):
    res = client.post(
        f"/projects/{test_project}/link-recommendations",
        json={"entity_id": 9999999, "doc_title": "x"},
    )
    assert res.status_code == 404


def test_create_manual_link_rejects_duplicate_approved_link(
    client, db_session, test_project, source_entity_chunk
):
    source, entity, chunk = source_entity_chunk
    payload = {"entity_id": entity.id, "doc_title": "handbuch.md"}
    first = client.post(f"/projects/{test_project}/link-recommendations", json=payload)
    assert first.status_code == 200
    try:
        second = client.post(f"/projects/{test_project}/link-recommendations", json=payload)
        assert second.status_code == 409
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == first.json()["id"]).delete()
        db_session.commit()


def test_create_manual_link_rejects_team_member_without_project(
    unauthenticated_client, test_project, team_member_without_project, source_entity_chunk
):
    source, entity, chunk = source_entity_chunk
    res = _as(unauthenticated_client, team_member_without_project).post(
        f"/projects/{test_project}/link-recommendations",
        json={"entity_id": entity.id, "doc_title": "handbuch.md"},
    )
    assert res.status_code == 403


# ── POST /projects/{id}/link-recommendations/compute ────────────────────────


def test_trigger_link_computation_dispatches_task_and_creates_run(
    client, db_session, test_project
):
    calls = []

    def fake_send_tracked_task(db, record, task_name, args, kwargs=None):
        calls.append((task_name, args, kwargs))

    with patch.object(entity_links_api, "send_tracked_task", side_effect=fake_send_tracked_task):
        res = client.post(
            f"/projects/{test_project}/link-recommendations/compute",
            params={"min_confidence": 70},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["project_id"] == test_project
    run_id = body["run_id"]

    assert len(calls) == 1
    task_name, args, kwargs = calls[0]
    assert task_name == "compute_entity_links"
    assert args == [run_id, test_project]
    assert kwargs["min_confidence"] == 70

    run = db_session.query(LinkBuilderRun).filter(LinkBuilderRun.id == run_id).first()
    assert run is not None
    assert run.task_type == "entity_links"
    db_session.delete(run)
    db_session.commit()


def test_trigger_link_computation_clears_pending_but_keeps_reviewed_links(
    client, db_session, test_project, source_entity_chunk
):
    source, entity, chunk = source_entity_chunk
    # IDs vorab festhalten: die Route löscht "pending" serverseitig per Bulk-
    # DELETE (synchronize_session=False), was die Python-Objekte dieser
    # Session nach dem nächsten Commit als "expired" zurücklässt — ein
    # Attributzugriff auf `pending` danach würfe ObjectDeletedError.
    pending_id = _make_link(db_session, test_project, entity, chunk, status="pending").id
    approved_id = _make_link(db_session, test_project, entity, chunk, status="approved").id
    rejected_id = _make_link(db_session, test_project, entity, chunk, status="rejected").id

    with patch.object(entity_links_api, "send_tracked_task", side_effect=lambda *a, **k: None):
        res = client.post(f"/projects/{test_project}/link-recommendations/compute")
    assert res.status_code == 200

    remaining_ids = {
        row.id
        for row in db_session.query(EntityDocLink.id).filter(
            EntityDocLink.id.in_([pending_id, approved_id, rejected_id])
        )
    }
    assert remaining_ids == {approved_id, rejected_id}

    db_session.query(LinkBuilderRun).filter(LinkBuilderRun.project_id == test_project).delete(
        synchronize_session=False
    )
    db_session.query(EntityDocLink).filter(
        EntityDocLink.id.in_([approved_id, rejected_id])
    ).delete(synchronize_session=False)
    db_session.commit()


def test_trigger_link_computation_rejects_team_member_without_project(
    unauthenticated_client, test_project, team_member_without_project
):
    res = _as(unauthenticated_client, team_member_without_project).post(
        f"/projects/{test_project}/link-recommendations/compute"
    )
    assert res.status_code == 403


# ── GET /projects/{id}/link-builder-runs ─────────────────────────────────────


def test_list_link_builder_runs_returns_most_recent_first(client, db_session, test_project):
    # created_at explizit gesetzt statt auf den server_default NOW() zu
    # vertrauen: beide Inserts liefen sonst in derselben Transaktion und
    # NOW() ist dort für beide Zeilen identisch — die Reihenfolge unter
    # gleichem Zeitstempel wäre dann zufällig, nicht das, was der Test prüft.
    now = datetime.now(timezone.utc)
    older = LinkBuilderRun(
        task_type="entity_links", project_id=test_project, status="completed",
        created_at=now - timedelta(seconds=5),
    )
    newer = LinkBuilderRun(
        task_type="entity_links", project_id=test_project, status="failed", created_at=now,
    )
    db_session.add_all([older, newer])
    db_session.commit()
    db_session.refresh(older)
    db_session.refresh(newer)
    try:
        res = client.get(f"/projects/{test_project}/link-builder-runs")
        assert res.status_code == 200
        ids = [r["id"] for r in res.json()]
        assert ids.index(newer.id) < ids.index(older.id)
    finally:
        db_session.delete(older)
        db_session.delete(newer)
        db_session.commit()


def test_list_link_builder_runs_ignores_other_task_types(client, db_session, test_project):
    knowledge_run = LinkBuilderRun(task_type="knowledge_links", project_id=test_project, status="completed")
    db_session.add(knowledge_run)
    db_session.commit()
    db_session.refresh(knowledge_run)
    try:
        res = client.get(f"/projects/{test_project}/link-builder-runs")
        assert knowledge_run.id not in [r["id"] for r in res.json()]
    finally:
        db_session.delete(knowledge_run)
        db_session.commit()


def test_list_link_builder_runs_hides_project_from_team_outsider(
    unauthenticated_client, test_project, team_outsider
):
    res = _as(unauthenticated_client, team_outsider).get(f"/projects/{test_project}/link-builder-runs")
    assert res.status_code == 404


# ── PATCH /entity-doc-links/{id} ─────────────────────────────────────────────


def test_update_link_status_approves_and_sets_reviewed_at(
    client, db_session, test_project, source_entity_chunk
):
    source, entity, chunk = source_entity_chunk
    link = _make_link(db_session, test_project, entity, chunk, status="pending")
    try:
        res = client.patch(f"/entity-doc-links/{link.id}", json={"status": "approved"})
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "approved"
        assert body["reviewed_at"] is not None
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.commit()


def test_update_link_status_rejects_invalid_status_value(
    client, db_session, test_project, source_entity_chunk
):
    source, entity, chunk = source_entity_chunk
    link = _make_link(db_session, test_project, entity, chunk, status="pending")
    try:
        res = client.patch(f"/entity-doc-links/{link.id}", json={"status": "maybe"})
        assert res.status_code == 400
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.commit()


def test_update_link_context_is_editable_independent_of_status(
    client, db_session, test_project, source_entity_chunk
):
    source, entity, chunk = source_entity_chunk
    link = _make_link(db_session, test_project, entity, chunk, status="approved", context="alt")
    try:
        # Leerstring löscht die Beschreibung statt sie auf "" stehen zu lassen.
        res = client.patch(f"/entity-doc-links/{link.id}", json={"context": "  "})
        assert res.status_code == 200
        assert res.json()["context"] is None
        assert res.json()["status"] == "approved"

        res = client.patch(f"/entity-doc-links/{link.id}", json={"context": "neue Notiz"})
        assert res.json()["context"] == "neue Notiz"
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.commit()


def test_update_link_status_of_missing_link_is_404(client):
    res = client.patch("/entity-doc-links/9999999", json={"status": "approved"})
    assert res.status_code == 404


def test_update_link_status_rejects_team_member_without_project(
    unauthenticated_client, test_project, team_member_without_project, db_session, source_entity_chunk
):
    source, entity, chunk = source_entity_chunk
    link = _make_link(db_session, test_project, entity, chunk, status="pending")
    try:
        res = _as(unauthenticated_client, team_member_without_project).patch(
            f"/entity-doc-links/{link.id}", json={"status": "approved"}
        )
        assert res.status_code == 403
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.commit()


# ── POST /entity-doc-links/{id}/llm-review ───────────────────────────────────


async def _fake_llm_json(prompt, provider="ollama", model=None, api_key=None, base_url=None, timeout=60.0):
    return {"confidence": 87, "reason": "Deckt sich inhaltlich."}


def test_llm_review_updates_score_and_context_but_not_status(
    client, db_session, test_project, source_entity_chunk, monkeypatch
):
    source, entity, chunk = source_entity_chunk
    link = _make_link(db_session, test_project, entity, chunk, status="pending", score=0.1)
    monkeypatch.setattr(entity_links_api, "ask_llm_json_for_profile", _fake_llm_json)
    try:
        res = client.post(f"/entity-doc-links/{link.id}/llm-review")
        assert res.status_code == 200
        body = res.json()
        assert body["score"] == pytest.approx(0.87)
        assert body["context"] == "Deckt sich inhaltlich."
        assert body["status"] == "pending"  # unverändert — Nutzer entscheidet
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.commit()


def test_llm_review_rejects_manual_link_without_chunk(
    client, db_session, test_project, source_entity_chunk
):
    source, entity, chunk = source_entity_chunk
    link = _make_link(db_session, test_project, entity, chunk=None, status="approved")
    try:
        res = client.post(f"/entity-doc-links/{link.id}/llm-review")
        assert res.status_code == 400
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.commit()


def test_llm_review_rejects_disabled_cloud_provider(
    client, db_session, test_project, source_entity_chunk, monkeypatch
):
    monkeypatch.setattr(entity_links_api.cfg, "cloud_llm_allowed", lambda: False)
    source, entity, chunk = source_entity_chunk
    link = _make_link(db_session, test_project, entity, chunk, status="pending")
    try:
        res = client.post(
            f"/entity-doc-links/{link.id}/llm-review", json={"llm_provider": "openai"}
        )
        assert res.status_code == 403
        assert "allowCloudProviders" in res.json()["detail"]
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.commit()


def test_llm_review_returns_defined_error_when_local_llm_disabled(
    client, db_session, test_project, source_entity_chunk, monkeypatch
):
    """OLLAMA_LLM_MODEL=='disabled' (core/config.py::resolve_ollama_model) muss
    als saubere 502 durchschlagen, nicht als unbehandelter 500."""
    monkeypatch.setattr("core.config.OLLAMA_LLM_MODEL", "disabled")
    source, entity, chunk = source_entity_chunk
    link = _make_link(db_session, test_project, entity, chunk, status="pending")
    try:
        res = client.post(f"/entity-doc-links/{link.id}/llm-review")
        assert res.status_code == 502
        assert "LLM-Prüfung fehlgeschlagen" in res.json()["detail"]
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.commit()


def test_llm_review_of_missing_link_is_404(client):
    res = client.post("/entity-doc-links/9999999/llm-review")
    assert res.status_code == 404


def test_llm_review_rejects_team_member_without_project(
    unauthenticated_client, test_project, team_member_without_project, db_session, source_entity_chunk
):
    source, entity, chunk = source_entity_chunk
    link = _make_link(db_session, test_project, entity, chunk, status="pending")
    try:
        res = _as(unauthenticated_client, team_member_without_project).post(
            f"/entity-doc-links/{link.id}/llm-review"
        )
        assert res.status_code == 403
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.commit()


# ── DELETE /entity-doc-links/{id} ────────────────────────────────────────────


def test_delete_link(client, db_session, test_project, source_entity_chunk):
    source, entity, chunk = source_entity_chunk
    link = _make_link(db_session, test_project, entity, chunk, status="approved")
    res = client.delete(f"/entity-doc-links/{link.id}")
    assert res.status_code == 200
    assert db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).first() is None


def test_delete_missing_link_is_404(client):
    res = client.delete("/entity-doc-links/9999999")
    assert res.status_code == 404


def test_delete_link_rejects_team_member_without_project(
    unauthenticated_client, test_project, team_member_without_project, db_session, source_entity_chunk
):
    source, entity, chunk = source_entity_chunk
    link = _make_link(db_session, test_project, entity, chunk, status="approved")
    try:
        res = _as(unauthenticated_client, team_member_without_project).delete(
            f"/entity-doc-links/{link.id}"
        )
        assert res.status_code == 403
        assert db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).first() is not None
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.commit()


# ── GET /projects/{id}/entities/{id}/links ───────────────────────────────────


def test_get_entity_links_returns_only_approved(
    client, db_session, test_project, source_entity_chunk
):
    source, entity, chunk = source_entity_chunk
    approved = _make_link(db_session, test_project, entity, chunk, status="approved")
    pending = _make_link(db_session, test_project, entity, chunk, status="pending")
    try:
        res = client.get(f"/projects/{test_project}/entities/{entity.id}/links")
        assert res.status_code == 200
        ids = [lnk["id"] for lnk in res.json()]
        assert ids == [approved.id]
    finally:
        db_session.query(EntityDocLink).filter(
            EntityDocLink.id.in_([approved.id, pending.id])
        ).delete(synchronize_session=False)
        db_session.commit()


def test_get_entity_links_hides_project_from_team_outsider(
    unauthenticated_client, test_project, team_outsider, source_entity_chunk
):
    source, entity, chunk = source_entity_chunk
    res = _as(unauthenticated_client, team_outsider).get(
        f"/projects/{test_project}/entities/{entity.id}/links"
    )
    assert res.status_code == 404


# ── GET /projects/{id}/doc-chunks/search ─────────────────────────────────────


def test_search_doc_chunks_finds_by_query(client, source_entity_chunk, test_project):
    source, entity, chunk = source_entity_chunk
    res = client.get(f"/projects/{test_project}/doc-chunks/search", params={"q": "Kontoführung"})
    assert res.status_code == 200
    assert any(r["title"] == "Handbuch Kontoführung" for r in res.json())


def test_search_doc_chunks_without_query_lists_up_to_twenty(
    client, source_entity_chunk, test_project
):
    source, entity, chunk = source_entity_chunk
    res = client.get(f"/projects/{test_project}/doc-chunks/search")
    assert res.status_code == 200
    assert any(r["title"] == "Handbuch Kontoführung" for r in res.json())


def test_search_doc_chunks_rejects_team_member_without_project(
    unauthenticated_client, test_project, team_member_without_project
):
    res = _as(unauthenticated_client, team_member_without_project).get(
        f"/projects/{test_project}/doc-chunks/search"
    )
    assert res.status_code == 403
