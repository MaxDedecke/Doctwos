"""
Nutzerverwaltung (F-004) und das, was sie für die Anmeldung bedeutet (F-005).

Läuft wie die übrigen Backend-Tests gegen die konfigurierte DB. Alle angelegten
Konten werden am Ende wieder entfernt.
"""

from contextlib import contextmanager

import pytest

from core.auth_dependency import SESSION_COOKIE_NAME
from models.database import User

NEW_USERNAME = "test-managed-user"


@contextmanager
def as_nobody(client):
    """Abgemeldeter Client — und danach wieder der Admin.

    `client` und `unauthenticated_client` sind dieselbe TestClient-Instanz (die
    Admin-Fixture setzt nur eine Cookie darauf, siehe conftest). Wer hier einfach
    `cookies.clear()` aufruft, meldet damit auch den Administrator ab und die
    restlichen Aufrufe des Tests laufen still in 401.
    """
    saved = client.cookies.get(SESSION_COOKIE_NAME)
    client.cookies.clear()
    try:
        yield client
    finally:
        client.cookies.clear()
        if saved:
            client.cookies.set(SESSION_COOKIE_NAME, saved)


@pytest.fixture
def cleanup_user(db_session):
    def _delete():
        db_session.query(User).filter(User.username == NEW_USERNAME).delete()
        db_session.commit()

    _delete()
    yield
    _delete()


def _create(client, **overrides):
    payload = {"username": NEW_USERNAME, "name": "Verwalteter Nutzer", "role": "user"}
    payload.update(overrides)
    return client.post("/users", json=payload)


def test_create_user_returns_the_initial_password_exactly_once(client, cleanup_user):
    res = _create(client)
    assert res.status_code == 201
    body = res.json()

    assert body["username"] == NEW_USERNAME
    assert body["is_active"] is True
    # Ein fremdgesetztes Passwort gilt nur bis zum ersten Login.
    assert body["must_change_password"] is True
    assert len(body["initial_password"]) >= 12
    assert "password_hash" not in body

    # Die Liste zeigt das Passwort nicht mehr — es existiert nur noch als Hash.
    listed = next(u for u in client.get("/users").json() if u["username"] == NEW_USERNAME)
    assert "initial_password" not in listed
    assert "password_hash" not in listed


def test_duplicate_username_is_rejected(client, cleanup_user):
    assert _create(client).status_code == 201
    assert _create(client).status_code == 409


def test_new_user_can_log_in_and_deactivation_stops_that(client, cleanup_user):
    password = _create(client).json()["initial_password"]
    user_id = next(u["id"] for u in client.get("/users").json() if u["username"] == NEW_USERNAME)

    with as_nobody(client) as anon:
        res = anon.post("/auth/login", json={"username": NEW_USERNAME, "password": password})
        assert res.status_code == 200
        assert res.json()["must_change_password"] is True

    assert client.patch(f"/users/{user_id}", json={"is_active": False}).json()["is_active"] is False

    with as_nobody(client) as anon:
        res = anon.post("/auth/login", json={"username": NEW_USERNAME, "password": password})
    # 401 und nicht 403: ob ein Konto deaktiviert ist oder das Passwort falsch war,
    # darf von außen nicht unterscheidbar sein.
    assert res.status_code == 401


def test_reset_password_replaces_the_old_one(client, cleanup_user):
    old_password = _create(client).json()["initial_password"]
    user_id = next(u["id"] for u in client.get("/users").json() if u["username"] == NEW_USERNAME)

    new_password = client.post(f"/users/{user_id}/reset-password", json={}).json()["initial_password"]
    assert new_password != old_password

    with as_nobody(client) as anon:
        assert anon.post("/auth/login", json={"username": NEW_USERNAME, "password": new_password}).status_code == 200
        # Das alte Passwort ist damit tot.
        assert anon.post("/auth/login", json={"username": NEW_USERNAME, "password": old_password}).status_code == 401


def test_reset_password_is_rejected_for_sso_accounts(client, db_session):
    """E-12: ein gesetztes lokales Passwort wäre für ein SSO-Konto ein Weg an
    der Kunden-IdP-Anmeldung vorbei."""
    from core.users import create_oidc_user

    user = create_oidc_user(db_session, username="test-oidc-reset-guard", subject="test-oidc-reset-guard-sub")
    try:
        resp = client.post(f"/users/{user.id}/reset-password", json={})
        assert resp.status_code == 400
    finally:
        db_session.query(User).filter(User.username == "test-oidc-reset-guard").delete()
        db_session.commit()


def test_users_list_reports_auth_provider(client, cleanup_user):
    _create(client)
    listed = next(u for u in client.get("/users").json() if u["username"] == NEW_USERNAME)
    assert listed["auth_provider"] == "local"


def test_reset_password_lifts_an_existing_lock(client, db_session, cleanup_user):
    from datetime import datetime, timedelta, timezone

    _create(client)
    user = db_session.query(User).filter(User.username == NEW_USERNAME).first()
    user.locked_until = datetime.now(timezone.utc) + timedelta(hours=1)
    user.failed_login_count = 9
    db_session.commit()

    body = client.post(f"/users/{user.id}/reset-password", json={}).json()
    assert body["is_locked"] is False
    assert body["failed_login_count"] == 0


def test_unlock_clears_the_lock(client, db_session, cleanup_user):
    from datetime import datetime, timedelta, timezone

    _create(client)
    user = db_session.query(User).filter(User.username == NEW_USERNAME).first()
    user.locked_until = datetime.now(timezone.utc) + timedelta(hours=1)
    db_session.commit()

    body = client.post(f"/users/{user.id}/unlock").json()
    assert body["is_locked"] is False


def test_admin_cannot_lock_itself_out(client, cleanup_user):
    me = client.get("/auth/me").json()
    assert client.patch(f"/users/{me['id']}", json={"is_active": False}).status_code == 400
    assert client.patch(f"/users/{me['id']}", json={"role": "user"}).status_code == 400


def test_users_endpoints_require_admin(client, cleanup_user):
    """Ein normaler Nutzer mit gültiger Session darf die Verwaltung nicht sehen."""
    from core.auth_dependency import create_session_cookie_value

    _create(client)
    user_id = next(u["id"] for u in client.get("/users").json() if u["username"] == NEW_USERNAME)

    with as_nobody(client) as plain_user:
        plain_user.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value(user_id))
        assert plain_user.get("/users").status_code == 403
        assert plain_user.post("/users", json={"username": "x-nope"}).status_code == 403
        assert plain_user.post(f"/users/{user_id}/unlock").status_code == 403
