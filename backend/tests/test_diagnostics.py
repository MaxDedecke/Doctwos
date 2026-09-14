"""
Tests für backend/api/diagnostics.py (O-112).

Zwei getrennte Router, absichtlich unterschiedlich gegatet (main.py):
  - `diagnostics.router` (`/generate`, `/runs`, `/runs/{id}/download`) läuft
    hinter `dependencies=[Depends(require_admin)]` -- ein Diagnose-Bundle
    enthält DB-Auszüge und Logs.
  - `diagnostics.public_router` (nur `/client-error`) ist bewusst ohne
    Anmeldung erreichbar (Modul-Docstring: ein Frontend-Absturz kann vor dem
    Login passieren), speichert aber nichts über eine Logzeile hinaus.

Die eigentliche Klärung, die der Katalogeintrag verlangt hat, stand also
schon im Code -- hier wird sie erstmals per Test festgehalten statt nur
behauptet: die Admin-Gating-Prüfung zielt bewusst auf eine nicht existierende
Run-ID, damit ein 404 aus der Routenlogik selbst kein fälschlich grünes 403
vortäuschen kann (gleiches Muster wie test_topics.py, O-111), und ein eigener
Test stellt sicher, dass der öffentliche Router wirklich nur `/client-error`
freigibt und nicht versehentlich eine der drei Admin-Routen mit erreicht.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import api.diagnostics as diagnostics_api
from models.database import DiagnosticsRun

ADMIN_GATED_ROUTES = [
    ("post", "/diagnostics/generate", None),
    ("get", "/diagnostics/runs", None),
    ("get", "/diagnostics/runs/999999/download", None),
]


def test_admin_gating_blocks_every_route_for_a_non_admin(member_client):
    for method, path, payload in ADMIN_GATED_ROUTES:
        kwargs = {"json": payload} if payload is not None else {}
        res = getattr(member_client, method)(path, **kwargs)
        assert res.status_code == 403, (
            f"{method.upper()} {path} sollte 403 liefern, war {res.status_code}"
        )


def test_admin_gating_requires_login_at_all_for_every_route(unauthenticated_client):
    for method, path, payload in ADMIN_GATED_ROUTES:
        kwargs = {"json": payload} if payload is not None else {}
        res = getattr(unauthenticated_client, method)(path, **kwargs)
        assert res.status_code == 401, (
            f"{method.upper()} {path} sollte 401 liefern, war {res.status_code}"
        )


def test_public_router_only_exposes_client_error(unauthenticated_client):
    """Die Admin-Routen dürfen über den öffentlichen Router nicht erreichbar
    sein -- ein Pfadtippfehler in main.py würde sonst DB-Auszüge/Logs für
    jeden ohne Anmeldung öffnen."""
    res = unauthenticated_client.post("/diagnostics/client-error", json={"message": "boom"})
    assert res.status_code == 200
    assert res.json() == {"message": "Error report received"}


def test_client_error_report_is_opt_in_and_only_logged(unauthenticated_client, caplog):
    """Kein Persistenz-Nebeneffekt -- nur eine Logzeile, wie der Docstring
    verspricht."""
    with caplog.at_level("ERROR"):
        res = unauthenticated_client.post(
            "/diagnostics/client-error",
            json={
                "message": "TypeError: x is not a function",
                "stack": "at Foo (bar.js:1:1)",
                "digest": "abc123",
                "url": "https://example.test/broken",
                "trace_id": "trace-xyz",
            },
        )
    assert res.status_code == 200
    assert any(
        "TypeError: x is not a function" in r.message and "trace-xyz" in r.message
        for r in caplog.records
    )


def test_client_error_report_accepts_minimal_payload(unauthenticated_client):
    # Alle Felder außer `message` sind optional.
    res = unauthenticated_client.post("/diagnostics/client-error", json={"message": "kaputt"})
    assert res.status_code == 200


# ── POST /diagnostics/generate ────────────────────────────────────────────────


def test_trigger_bundle_generation_dispatches_task_and_creates_run(client, db_session):
    calls = []

    def fake_send_tracked_task(db, record, task_name, args, kwargs=None):
        calls.append((task_name, args, kwargs))

    with patch.object(diagnostics_api, "send_tracked_task", side_effect=fake_send_tracked_task):
        res = client.post("/diagnostics/generate")
    assert res.status_code == 200
    run_id = res.json()["run_id"]

    assert len(calls) == 1
    task_name, args, kwargs = calls[0]
    assert task_name == "generate_diagnostics_bundle"
    assert args == [run_id]
    assert "trace_id" in kwargs

    run = db_session.query(DiagnosticsRun).filter(DiagnosticsRun.id == run_id).first()
    assert run is not None
    assert run.status == "pending"
    assert run.triggered_by_user_id is not None
    db_session.delete(run)
    db_session.commit()


# ── GET /diagnostics/runs ─────────────────────────────────────────────────────


def test_list_runs_returns_most_recent_first(client, db_session):
    # created_at explizit gesetzt statt auf den server_default NOW() zu
    # vertrauen -- beide Inserts liefen sonst in derselben Transaktion mit
    # identischem NOW().
    now = datetime.now(timezone.utc)
    older = DiagnosticsRun(status="completed", created_at=now - timedelta(seconds=5))
    newer = DiagnosticsRun(status="failed", error_message="boom", created_at=now)
    db_session.add_all([older, newer])
    db_session.commit()
    db_session.refresh(older)
    db_session.refresh(newer)
    try:
        res = client.get("/diagnostics/runs")
        assert res.status_code == 200
        ids = [r["id"] for r in res.json()]
        assert ids.index(newer.id) < ids.index(older.id)
        failed = next(r for r in res.json() if r["id"] == newer.id)
        assert failed["error_message"] == "boom"
    finally:
        db_session.delete(older)
        db_session.delete(newer)
        db_session.commit()


# ── GET /diagnostics/runs/{id}/download ───────────────────────────────────────


def test_download_completed_bundle(client, db_session, tmp_path):
    bundle = tmp_path / "diagnostics-bundle.tar.gz"
    bundle.write_bytes(b"fake-bundle-content")
    run = DiagnosticsRun(status="completed", bundle_path=str(bundle))
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    try:
        res = client.get(f"/diagnostics/runs/{run.id}/download")
        assert res.status_code == 200
        assert res.content == b"fake-bundle-content"
        assert "diagnostics-bundle.tar.gz" in res.headers["content-disposition"]
    finally:
        db_session.delete(run)
        db_session.commit()


def test_download_missing_run_is_404(client):
    res = client.get("/diagnostics/runs/9999999/download")
    assert res.status_code == 404


def test_download_unfinished_bundle_is_409(client, db_session):
    run = DiagnosticsRun(status="running")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    try:
        res = client.get(f"/diagnostics/runs/{run.id}/download")
        assert res.status_code == 409
    finally:
        db_session.delete(run)
        db_session.commit()


def test_download_bundle_with_missing_file_is_410(client, db_session):
    run = DiagnosticsRun(status="completed", bundle_path="/nonexistent/diagnostics-bundle.tar.gz")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    try:
        res = client.get(f"/diagnostics/runs/{run.id}/download")
        assert res.status_code == 410
    finally:
        db_session.delete(run)
        db_session.commit()
