import core.config as cfg
import core.oidc as oidc_service
from core.auth_dependency import SESSION_COOKIE_NAME, create_session_cookie_value
from models.database import User


def test_protected_endpoint_without_session_returns_401(unauthenticated_client):
    resp = unauthenticated_client.get("/projects")
    assert resp.status_code == 401


def test_protected_endpoint_with_garbage_cookie_returns_401(unauthenticated_client):
    unauthenticated_client.cookies.set("doctus_session", "not-a-valid-signed-value")
    resp = unauthenticated_client.get("/projects")
    assert resp.status_code == 401


def test_protected_endpoint_with_valid_session_succeeds(client):
    resp = client.get("/projects")
    assert resp.status_code == 200


def test_auth_me_returns_user_info_with_valid_session(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == "fixture-user@example.com"


def test_health_endpoint_does_not_require_auth(unauthenticated_client):
    resp = unauthenticated_client.get("/health")

    # /health is a public readiness endpoint. It legitimately returns 503 when
    # a dependency such as Ollama is absent (as in the backend-only CI job);
    # that must not be confused with an authentication failure.
    assert resp.status_code in {200, 503}
    body = resp.json()
    assert body["status"] in {"healthy", "degraded"}
    assert set(body["checks"]) == {"database", "redis", "ollama"}


# ── SSO / OIDC (E-12) ────────────────────────────────────────────────────────
# Die Protokoll-/Provisioning-Logik selbst ist in test_oidc.py abgedeckt — hier
# geht es nur um die Verdrahtung im Router: 404 ohne Konfiguration, Redirects,
# Cookie-Handling, und dass ein SSO-Konto (password_hash=None) den lokalen
# Login sauber ablehnt statt abzustürzen.

def _enable_oidc(monkeypatch):
    monkeypatch.setattr(cfg, "OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setattr(cfg, "OIDC_CLIENT_ID", "doctus-client")
    monkeypatch.setattr(cfg, "OIDC_CLIENT_SECRET", "secret")


def _raise_oidc_error(*_args, **_kwargs):
    raise oidc_service.OidcError("State ungültig")


def test_oidc_login_returns_404_when_not_configured(unauthenticated_client):
    resp = unauthenticated_client.get("/auth/oidc/login", follow_redirects=False)
    assert resp.status_code == 404


def test_oidc_callback_returns_404_when_not_configured(unauthenticated_client):
    resp = unauthenticated_client.get("/auth/oidc/callback", follow_redirects=False)
    assert resp.status_code == 404


def test_oidc_login_redirects_to_idp_and_sets_state_cookie(unauthenticated_client, monkeypatch):
    _enable_oidc(monkeypatch)
    monkeypatch.setattr(
        oidc_service, "build_authorization_url",
        lambda: ("https://idp.example.com/auth?state=abc", "signed-state-cookie-value"),
    )

    resp = unauthenticated_client.get("/auth/oidc/login", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == "https://idp.example.com/auth?state=abc"
    assert resp.cookies.get(oidc_service.OIDC_STATE_COOKIE_NAME) == "signed-state-cookie-value"


def test_oidc_callback_establishes_a_session_on_success(unauthenticated_client, db_session, monkeypatch):
    _enable_oidc(monkeypatch)
    user = User(
        username="test-oidc-callback-user",
        password_hash=None,
        oidc_subject="test-oidc-callback-sub",
        role="user",
    )
    db_session.add(user)
    db_session.commit()
    try:
        monkeypatch.setattr(oidc_service, "verify_state_cookie", lambda cookie, state: "expected-nonce")
        monkeypatch.setattr(oidc_service, "exchange_code", lambda code, expected_nonce: {"sub": "test-oidc-callback-sub"})
        monkeypatch.setattr(oidc_service, "provision_or_link_user", lambda claims, db: user)
        unauthenticated_client.cookies.set(oidc_service.OIDC_STATE_COOKIE_NAME, "irrelevant-because-mocked")

        resp = unauthenticated_client.get(
            "/auth/oidc/callback", params={"code": "abc", "state": "xyz"}, follow_redirects=False
        )

        assert resp.status_code == 302
        assert resp.headers["location"] == cfg.FRONTEND_URL
        assert not resp.cookies.get(oidc_service.OIDC_STATE_COOKIE_NAME)

        session_cookie = resp.cookies.get("doctus_session")
        assert session_cookie
        unauthenticated_client.cookies.set("doctus_session", session_cookie)
        me = unauthenticated_client.get("/auth/me")
        assert me.status_code == 200
        assert me.json()["username"] == "test-oidc-callback-user"
    finally:
        db_session.query(User).filter(User.username == "test-oidc-callback-user").delete()
        db_session.commit()


def test_oidc_callback_redirects_with_error_message_on_failure(unauthenticated_client, monkeypatch):
    _enable_oidc(monkeypatch)
    monkeypatch.setattr(oidc_service, "verify_state_cookie", _raise_oidc_error)

    resp = unauthenticated_client.get(
        "/auth/oidc/callback", params={"code": "abc", "state": "xyz"}, follow_redirects=False
    )

    assert resp.status_code == 302
    assert resp.headers["location"].startswith(cfg.FRONTEND_URL)
    assert "oidc_error=" in resp.headers["location"]
    assert not resp.cookies.get("doctus_session")


def test_oidc_callback_surfaces_idp_error_query_param(unauthenticated_client, monkeypatch):
    _enable_oidc(monkeypatch)
    resp = unauthenticated_client.get(
        "/auth/oidc/callback", params={"error": "access_denied"}, follow_redirects=False
    )
    assert resp.status_code == 302
    assert "oidc_error=" in resp.headers["location"]


def test_login_rejects_sso_only_account_without_crashing(unauthenticated_client, db_session):
    """password_hash=None (SSO-Konto, E-12) darf /auth/login nie mit einem
    500er beantworten — verify_password() bekäme sonst None statt eines Hashs."""
    user = User(
        username="test-oidc-no-password",
        password_hash=None,
        oidc_subject="test-oidc-no-password-sub",
        role="user",
    )
    db_session.add(user)
    db_session.commit()
    try:
        resp = unauthenticated_client.post(
            "/auth/login", json={"username": "test-oidc-no-password", "password": "irrelevant123"}
        )
        assert resp.status_code == 401
    finally:
        db_session.query(User).filter(User.username == "test-oidc-no-password").delete()
        db_session.commit()


def test_change_password_rejects_sso_only_account(unauthenticated_client, db_session):
    user = User(
        username="test-oidc-change-pw",
        password_hash=None,
        oidc_subject="test-oidc-change-pw-sub",
        role="user",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    try:
        unauthenticated_client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value(user.id))
        resp = unauthenticated_client.post(
            "/auth/change-password",
            json={"old_password": "whatever12345", "new_password": "somethingnew123"},
        )
        assert resp.status_code == 400
    finally:
        db_session.query(User).filter(User.username == "test-oidc-change-pw").delete()
        db_session.commit()
