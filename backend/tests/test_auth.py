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
