"""
Tests für backend/api/knowledge_links.py (O-109).

Sieben Routen, von denen fünf keinen einzigen Testaufruf hatten: Links
anlegen/ändern/löschen, den Cross-Source-Compute-Lauf anstoßen, dessen
Historie lesen, und einen Einzel-Link per LLM neu bewerten. GET (Liste) und
GET /counts sind bereits über O-165 abgedeckt (`test_knowledge_links_listing.py`)
-- hier fehlt der Rest.

knowledge_links.py teilt sich Bewertungs-/Review-Logik mit entity_links.py
(O-108): dieselbe `ask_llm_json_for_profile`-Signatur, dieselbe
Konfidenz->Score-Umrechnung, dasselbe Cloud-Provider-Gate. Der Fake dafür
kommt aus `conftest.py::make_fake_llm_json`, damit beide Testdateien ihn
nicht getrennt pflegen.

Sichtbarkeit läuft hier anders als bei entity_links.py: es gibt keine
Projekt-ID in der Route, jede Seite eines Links wird einzeln per
`is_side_visible` geprüft (Entity/Chunk -> Projekt bzw. Wissensquelle ->
Team). Ein Team-Mitglied ohne Projektmitgliedschaft und ein komplett fremdes
Team landen deshalb beide auf derselben 404 ("Link nicht gefunden") statt wie
bei entity_links.py auf 403 vs. 404 -- das ist hier bewusst mitgetestet statt
stillschweigend vorausgesetzt. `/compute` und `/runs` sind dagegen
admin-only (`is_admin`), unabhängig von jeder Projekt-/Link-Sichtbarkeit.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import api.knowledge_links as knowledge_links_api
from core.auth_dependency import SESSION_COOKIE_NAME, create_session_cookie_value
from models.database import (
    CodeEntity,
    DocumentChunk,
    KnowledgeLink,
    KnowledgeSource,
    LinkBuilderRun,
    Project,
    ProjectMembership,
    Team,
    TeamMembership,
    User,
)
from tests.conftest import make_fake_llm_json


@pytest.fixture
def project_member(test_project, db_session):
    """Non-admin member of `test_project`'s own team+project."""
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    user = User(
        username="test-knowledge-links-member",
        email="test-knowledge-links-member@example.com",
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
    Punkt, an dem is_side_visible trotz Teamzugehörigkeit False liefert."""
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    user = User(
        username="test-knowledge-links-team-only",
        email="test-knowledge-links-team-only@example.com",
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
    """A user in an entirely different team -- can't see `test_project` at all."""
    foreign_team = Team(name="TestKnowledgeLinksForeignTeam")
    db_session.add(foreign_team)
    db_session.commit()
    db_session.refresh(foreign_team)

    user = User(
        username="test-knowledge-links-outsider",
        email="test-knowledge-links-outsider@example.com",
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
def two_chunks(test_project, db_session):
    """Two DocumentChunks in `test_project` -- die minimale Grundlage für
    einen document<->document KnowledgeLink."""
    proj = db_session.query(Project).filter(Project.id == test_project).first()
    source = KnowledgeSource(
        name="KL Source", type="Local", project_id=test_project, team_id=proj.team_id
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    chunks = [
        DocumentChunk(
            project_id=test_project,
            source_id=source.id,
            file_path=f"doc{i}.md",
            content=f"Inhalt {i}",
            start_line=1,
            end_line=2,
        )
        for i in range(2)
    ]
    db_session.add_all(chunks)
    db_session.commit()
    for c in chunks:
        db_session.refresh(c)

    yield source, chunks[0], chunks[1]

    db_session.query(DocumentChunk).filter(DocumentChunk.id.in_([c.id for c in chunks])).delete(
        synchronize_session=False
    )
    db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
    db_session.commit()


@pytest.fixture
def entity_without_chunk(test_project, db_session):
    """Eine CodeEntity in `test_project`, als Linkseite ohne Chunk -- llm-review
    kann so ein Paar nicht bewerten, weil beiden Seiten Inhalt fehlen muss."""
    entity = CodeEntity(
        project_id=test_project,
        file_path="X.cbl",
        name="X-PARA",
        type="paragraph",
        start_line=1,
        end_line=2,
    )
    db_session.add(entity)
    db_session.commit()
    db_session.refresh(entity)

    yield entity

    db_session.delete(entity)
    db_session.commit()


def _make_link(db_session, chunk_a, chunk_b, **overrides):
    defaults = dict(
        source_a_type="document",
        source_a_chunk_id=chunk_a.id,
        source_a_title=chunk_a.file_path,
        source_b_type="document",
        source_b_chunk_id=chunk_b.id,
        source_b_title=chunk_b.file_path,
        status="pending",
        link_type="semantic",
        score=0.5,
    )
    defaults.update(overrides)
    link = KnowledgeLink(**defaults)
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)
    return link


# ── POST /knowledge-links ─────────────────────────────────────────────────────


def test_create_knowledge_link(client, db_session, two_chunks):
    source, chunk_a, chunk_b = two_chunks
    res = client.post(
        "/knowledge-links",
        json={
            "source_a_type": "document",
            "source_a_chunk_id": chunk_a.id,
            "source_a_title": chunk_a.file_path,
            "source_b_type": "document",
            "source_b_chunk_id": chunk_b.id,
            "source_b_title": chunk_b.file_path,
            "context": "Beide beschreiben dieselbe Buchung.",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "approved"
    assert body["link_type"] == "manual"
    assert body["created_by"] == "user"
    assert body["context"] == "Beide beschreiben dieselbe Buchung."

    link = db_session.query(KnowledgeLink).filter(KnowledgeLink.id == body["id"]).first()
    assert link is not None
    db_session.delete(link)
    db_session.commit()


def test_create_knowledge_link_rejects_invisible_side(
    unauthenticated_client, team_outsider, two_chunks
):
    source, chunk_a, chunk_b = two_chunks
    res = _as(unauthenticated_client, team_outsider).post(
        "/knowledge-links",
        json={
            "source_a_type": "document",
            "source_a_chunk_id": chunk_a.id,
            "source_a_title": chunk_a.file_path,
            "source_b_type": "document",
            "source_b_chunk_id": chunk_b.id,
            "source_b_title": chunk_b.file_path,
        },
    )
    assert res.status_code == 403


def test_create_knowledge_link_requires_login(unauthenticated_client):
    # Bewusst ohne `two_chunks`/`test_project` in den Fixture-Parametern: die
    # ziehen über test_team die `client`-Fixture nach, die auf demselben
    # zugrundeliegenden TestClient bereits eine Superuser-Session setzt --
    # das würde diesen Test am eigentlichen Zweck vorbei grün machen.
    res = unauthenticated_client.post(
        "/knowledge-links",
        json={
            "source_a_type": "document",
            "source_a_chunk_id": 1,
            "source_a_title": "a",
            "source_b_type": "document",
            "source_b_chunk_id": 2,
            "source_b_title": "b",
        },
    )
    assert res.status_code == 401


# ── PATCH /knowledge-links/{id} ───────────────────────────────────────────────


def test_update_knowledge_link_status_sets_reviewed_at(client, db_session, two_chunks):
    source, chunk_a, chunk_b = two_chunks
    link = _make_link(db_session, chunk_a, chunk_b, status="pending")
    try:
        res = client.patch(f"/knowledge-links/{link.id}", json={"status": "approved"})
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "approved"
        assert body["reviewed_at"] is not None
    finally:
        db_session.query(KnowledgeLink).filter(KnowledgeLink.id == link.id).delete()
        db_session.commit()


def test_update_knowledge_link_context_is_editable_independent_of_status(
    client, db_session, two_chunks
):
    source, chunk_a, chunk_b = two_chunks
    link = _make_link(db_session, chunk_a, chunk_b, status="approved", context="alt")
    try:
        # Leerstring löscht die Beschreibung statt sie auf "" stehen zu lassen.
        res = client.patch(f"/knowledge-links/{link.id}", json={"context": "  "})
        assert res.status_code == 200
        assert res.json()["context"] is None
        assert res.json()["status"] == "approved"

        res = client.patch(f"/knowledge-links/{link.id}", json={"context": "neue Notiz"})
        assert res.json()["context"] == "neue Notiz"
    finally:
        db_session.query(KnowledgeLink).filter(KnowledgeLink.id == link.id).delete()
        db_session.commit()


def test_update_knowledge_link_of_missing_link_is_404(client):
    res = client.patch("/knowledge-links/9999999", json={"status": "approved"})
    assert res.status_code == 404


def test_update_knowledge_link_hides_invisible_link_as_404(
    unauthenticated_client, team_outsider, db_session, two_chunks
):
    """Weder 403 (existiert, aber verboten) noch stiller Erfolg -- dieselbe 404
    wie bei einer nicht existierenden ID, damit ein Fremder die Existenz des
    Links nicht aus dem Statuscode ablesen kann."""
    source, chunk_a, chunk_b = two_chunks
    link = _make_link(db_session, chunk_a, chunk_b, status="pending")
    try:
        res = _as(unauthenticated_client, team_outsider).patch(
            f"/knowledge-links/{link.id}", json={"status": "approved"}
        )
        assert res.status_code == 404
    finally:
        db_session.query(KnowledgeLink).filter(KnowledgeLink.id == link.id).delete()
        db_session.commit()


def test_update_knowledge_link_hides_link_from_team_member_without_project(
    unauthenticated_client, team_member_without_project, db_session, two_chunks
):
    """Team-Sichtbarkeit allein reicht nicht -- ohne Projektmitgliedschaft
    dieselbe 404 wie beim komplett fremden Team (anders als bei
    entity_links.py, das hier 403 liefert, s. Moduldoc)."""
    source, chunk_a, chunk_b = two_chunks
    link = _make_link(db_session, chunk_a, chunk_b, status="pending")
    try:
        res = _as(unauthenticated_client, team_member_without_project).patch(
            f"/knowledge-links/{link.id}", json={"status": "approved"}
        )
        assert res.status_code == 404
    finally:
        db_session.query(KnowledgeLink).filter(KnowledgeLink.id == link.id).delete()
        db_session.commit()


def test_update_knowledge_link_visible_to_project_member(
    unauthenticated_client, project_member, db_session, two_chunks
):
    source, chunk_a, chunk_b = two_chunks
    link = _make_link(db_session, chunk_a, chunk_b, status="pending")
    try:
        res = _as(unauthenticated_client, project_member).patch(
            f"/knowledge-links/{link.id}", json={"status": "rejected"}
        )
        assert res.status_code == 200
        assert res.json()["status"] == "rejected"
    finally:
        db_session.query(KnowledgeLink).filter(KnowledgeLink.id == link.id).delete()
        db_session.commit()


# ── DELETE /knowledge-links/{id} ──────────────────────────────────────────────


def test_delete_knowledge_link(client, db_session, two_chunks):
    source, chunk_a, chunk_b = two_chunks
    link = _make_link(db_session, chunk_a, chunk_b, status="approved")
    res = client.delete(f"/knowledge-links/{link.id}")
    assert res.status_code == 200
    assert db_session.query(KnowledgeLink).filter(KnowledgeLink.id == link.id).first() is None


def test_delete_missing_knowledge_link_is_404(client):
    res = client.delete("/knowledge-links/9999999")
    assert res.status_code == 404


def test_delete_knowledge_link_hides_invisible_link_as_404(
    unauthenticated_client, team_outsider, db_session, two_chunks
):
    source, chunk_a, chunk_b = two_chunks
    link = _make_link(db_session, chunk_a, chunk_b, status="approved")
    try:
        res = _as(unauthenticated_client, team_outsider).delete(f"/knowledge-links/{link.id}")
        assert res.status_code == 404
        assert (
            db_session.query(KnowledgeLink).filter(KnowledgeLink.id == link.id).first() is not None
        )
    finally:
        db_session.query(KnowledgeLink).filter(KnowledgeLink.id == link.id).delete()
        db_session.commit()


# ── POST /knowledge-links/{id}/llm-review ─────────────────────────────────────


def test_llm_review_updates_score_and_context_but_not_status(
    client, db_session, two_chunks, monkeypatch
):
    source, chunk_a, chunk_b = two_chunks
    link = _make_link(db_session, chunk_a, chunk_b, status="pending", score=0.1)
    monkeypatch.setattr(knowledge_links_api, "ask_llm_json_for_profile", make_fake_llm_json())
    try:
        res = client.post(f"/knowledge-links/{link.id}/llm-review")
        assert res.status_code == 200
        body = res.json()
        assert body["score"] == pytest.approx(0.87)
        assert body["context"] == "Deckt sich inhaltlich."
        assert body["status"] == "pending"  # unverändert — Nutzer entscheidet
    finally:
        db_session.query(KnowledgeLink).filter(KnowledgeLink.id == link.id).delete()
        db_session.commit()


def test_llm_review_rejects_link_without_chunk_on_either_side(
    client, db_session, two_chunks, entity_without_chunk
):
    source, chunk_a, chunk_b = two_chunks
    link = _make_link(
        db_session,
        chunk_a,
        chunk_b,
        source_b_type="entity",
        source_b_chunk_id=None,
        source_b_entity_id=entity_without_chunk.id,
        status="approved",
    )
    try:
        res = client.post(f"/knowledge-links/{link.id}/llm-review")
        assert res.status_code == 400
    finally:
        db_session.query(KnowledgeLink).filter(KnowledgeLink.id == link.id).delete()
        db_session.commit()


def test_llm_review_rejects_disabled_cloud_provider(client, db_session, two_chunks, monkeypatch):
    monkeypatch.setattr(knowledge_links_api.cfg, "cloud_llm_allowed", lambda: False)
    source, chunk_a, chunk_b = two_chunks
    link = _make_link(db_session, chunk_a, chunk_b, status="pending")
    try:
        res = client.post(f"/knowledge-links/{link.id}/llm-review", json={"llm_provider": "openai"})
        assert res.status_code == 403
        assert "allowCloudProviders" in res.json()["detail"]
    finally:
        db_session.query(KnowledgeLink).filter(KnowledgeLink.id == link.id).delete()
        db_session.commit()


def test_llm_review_returns_defined_error_when_local_llm_disabled(
    client, db_session, two_chunks, monkeypatch
):
    """OLLAMA_LLM_MODEL=='disabled' (core/config.py::resolve_ollama_model) muss
    als saubere 502 durchschlagen, nicht als unbehandelter 500."""
    monkeypatch.setattr("core.config.OLLAMA_LLM_MODEL", "disabled")
    source, chunk_a, chunk_b = two_chunks
    link = _make_link(db_session, chunk_a, chunk_b, status="pending")
    try:
        res = client.post(f"/knowledge-links/{link.id}/llm-review")
        assert res.status_code == 502
        assert "LLM-Prüfung fehlgeschlagen" in res.json()["detail"]
    finally:
        db_session.query(KnowledgeLink).filter(KnowledgeLink.id == link.id).delete()
        db_session.commit()


def test_llm_review_of_missing_link_is_404(client):
    res = client.post("/knowledge-links/9999999/llm-review")
    assert res.status_code == 404


def test_llm_review_hides_invisible_link_as_404(
    unauthenticated_client, team_outsider, db_session, two_chunks
):
    source, chunk_a, chunk_b = two_chunks
    link = _make_link(db_session, chunk_a, chunk_b, status="pending")
    try:
        res = _as(unauthenticated_client, team_outsider).post(
            f"/knowledge-links/{link.id}/llm-review"
        )
        assert res.status_code == 404
    finally:
        db_session.query(KnowledgeLink).filter(KnowledgeLink.id == link.id).delete()
        db_session.commit()


# ── POST /knowledge-links/compute ─────────────────────────────────────────────


def test_trigger_computation_dispatches_task_and_creates_run(client, db_session):
    calls = []

    def fake_send_tracked_task(db, record, task_name, args, kwargs=None):
        calls.append((task_name, args, kwargs))

    with patch.object(knowledge_links_api, "send_tracked_task", side_effect=fake_send_tracked_task):
        res = client.post("/knowledge-links/compute", params={"min_confidence": 70})
    assert res.status_code == 200
    run_id = res.json()["run_id"]

    assert len(calls) == 1
    task_name, args, kwargs = calls[0]
    assert task_name == "compute_knowledge_links"
    assert args == [run_id]
    assert kwargs["min_confidence"] == 70

    run = db_session.query(LinkBuilderRun).filter(LinkBuilderRun.id == run_id).first()
    assert run is not None
    assert run.task_type == "knowledge_links"
    db_session.delete(run)
    db_session.commit()


def test_trigger_computation_clears_pending_but_keeps_reviewed_links(
    client, db_session, two_chunks
):
    source, chunk_a, chunk_b = two_chunks
    # IDs vorab festhalten: die Route löscht "pending" serverseitig per Bulk-
    # DELETE (synchronize_session=False), ein Attributzugriff danach auf das
    # Python-Objekt würfe ObjectDeletedError.
    pending_id = _make_link(db_session, chunk_a, chunk_b, status="pending").id
    approved_id = _make_link(db_session, chunk_a, chunk_b, status="approved").id
    rejected_id = _make_link(db_session, chunk_a, chunk_b, status="rejected").id

    with patch.object(knowledge_links_api, "send_tracked_task", side_effect=lambda *a, **k: None):
        res = client.post("/knowledge-links/compute")
    assert res.status_code == 200
    run_id = res.json()["run_id"]

    remaining_ids = {
        row.id
        for row in db_session.query(KnowledgeLink.id).filter(
            KnowledgeLink.id.in_([pending_id, approved_id, rejected_id])
        )
    }
    assert remaining_ids == {approved_id, rejected_id}

    db_session.query(LinkBuilderRun).filter(LinkBuilderRun.id == run_id).delete()
    db_session.query(KnowledgeLink).filter(KnowledgeLink.id.in_([approved_id, rejected_id])).delete(
        synchronize_session=False
    )
    db_session.commit()


def test_trigger_computation_rejects_non_admin(member_client):
    res = member_client.post("/knowledge-links/compute")
    assert res.status_code == 403


def test_trigger_computation_requires_login(unauthenticated_client):
    res = unauthenticated_client.post("/knowledge-links/compute")
    assert res.status_code == 401


# ── GET /knowledge-links/runs ──────────────────────────────────────────────────


def test_list_runs_returns_most_recent_first(client, db_session):
    # created_at explizit gesetzt statt auf den server_default NOW() zu
    # vertrauen: beide Inserts liefen sonst in derselben Transaktion und NOW()
    # ist dort für beide Zeilen identisch.
    now = datetime.now(timezone.utc)
    older = LinkBuilderRun(
        task_type="knowledge_links",
        project_id=None,
        status="completed",
        created_at=now - timedelta(seconds=5),
    )
    newer = LinkBuilderRun(
        task_type="knowledge_links", project_id=None, status="failed", created_at=now
    )
    db_session.add_all([older, newer])
    db_session.commit()
    db_session.refresh(older)
    db_session.refresh(newer)
    try:
        res = client.get("/knowledge-links/runs")
        assert res.status_code == 200
        ids = [r["id"] for r in res.json()]
        assert ids.index(newer.id) < ids.index(older.id)
    finally:
        db_session.delete(older)
        db_session.delete(newer)
        db_session.commit()


def test_list_runs_ignores_other_task_types(client, db_session, test_project):
    entity_run = LinkBuilderRun(
        task_type="entity_links", project_id=test_project, status="completed"
    )
    db_session.add(entity_run)
    db_session.commit()
    db_session.refresh(entity_run)
    try:
        res = client.get("/knowledge-links/runs")
        assert entity_run.id not in [r["id"] for r in res.json()]
    finally:
        db_session.delete(entity_run)
        db_session.commit()


def test_list_runs_rejects_non_admin(member_client):
    res = member_client.get("/knowledge-links/runs")
    assert res.status_code == 403


def test_list_runs_requires_login(unauthenticated_client):
    res = unauthenticated_client.get("/knowledge-links/runs")
    assert res.status_code == 401
