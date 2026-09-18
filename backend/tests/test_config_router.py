"""
Tests für backend/api/config_router.py — System- und SSO-Konfigurations-Endpoints.
"""

import pytest


def test_get_features_unauthenticated(unauthenticated_client):
    res = unauthenticated_client.get("/config/features")
    assert res.status_code == 200
    data = res.json()
    assert "auth" in data
    assert "ssoEnabled" in data["auth"]


def test_get_system_config_requires_login(unauthenticated_client):
    res = unauthenticated_client.get("/config/system")
    assert res.status_code == 401


def test_get_system_config_forbidden_for_regular_user(member_client):
    res = member_client.get("/config/system")
    assert res.status_code == 403


def test_get_system_config_returns_expected_structure(client, monkeypatch):
    monkeypatch.setattr("core.config.OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setattr("core.config.OIDC_CLIENT_ID", "doctus-app")
    monkeypatch.setattr("core.config.OIDC_CLIENT_SECRET", "super-secret")
    monkeypatch.setattr("core.config.OIDC_DEFAULT_TEAM", "Default Team")
    monkeypatch.setattr("core.config.OIDC_ADMIN_ROLES", "admin, doctus-admin")
    monkeypatch.setattr("core.config.OIDC_TEAM_MAPPING", '{"dev": "Default Team"}')

    res = client.get("/config/system")
    assert res.status_code == 200
    data = res.json()

    # SSO block
    assert "sso" in data
    assert data["sso"]["enabled"] is True
    assert data["sso"]["issuer"] == "https://idp.example.com"
    assert data["sso"]["client_id"] == "doctus-app"
    assert data["sso"]["client_secret_configured"] is True
    assert data["sso"]["default_team"] == "Default Team"
    assert data["sso"]["default_team_exists"] is True
    assert "doctus-admin" in data["sso"]["admin_roles"]
    assert data["sso"]["team_mapping"] == {"dev": "Default Team"}
    assert data["sso"]["redirect_uri"].endswith("/auth/oidc/callback")

    # System block
    assert "system" in data
    assert "version" in data["system"]
    assert "api_url" in data["system"]
    assert "frontend_url" in data["system"]

    # Secrets block (no secrets leaked)
    assert "secrets" in data
    assert "master_encryption_key_configured" in data["secrets"]
    assert "super-secret" not in str(data)

    # Teams list
    assert "existing_teams" in data
    assert "Default Team" in data["existing_teams"]


def test_test_oidc_connection_without_issuer(client, monkeypatch):
    monkeypatch.setattr("core.config.OIDC_ISSUER", "")
    res = client.post("/config/oidc/test-connection")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert "Kein OIDC_ISSUER" in data["error"]


def test_test_oidc_connection_successful(client, monkeypatch):
    monkeypatch.setattr("core.config.OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setattr(
        "core.oidc._discover",
        lambda: {
            "issuer": "https://idp.example.com",
            "authorization_endpoint": "https://idp.example.com/auth",
            "token_endpoint": "https://idp.example.com/token",
            "userinfo_endpoint": "https://idp.example.com/userinfo",
            "jwks_uri": "https://idp.example.com/jwks",
        },
    )

    res = client.post("/config/oidc/test-connection")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["issuer"] == "https://idp.example.com"
    assert data["authorization_endpoint"] == "https://idp.example.com/auth"
    assert "duration_ms" in data


def test_simulate_oidc_mapping(client, monkeypatch):
    monkeypatch.setattr("core.config.OIDC_ADMIN_ROLES", "doctus-admin")
    monkeypatch.setattr("core.config.OIDC_DEFAULT_TEAM", "Default Team")
    monkeypatch.setattr("core.config.OIDC_TEAM_MAPPING", '{"dev": "Default Team", "special": "NonExistentTeam"}')

    # Simulation with admin role and dev group
    res = client.post(
        "/config/oidc/simulate-mapping",
        json={"roles": ["doctus-admin"], "groups": ["dev", "special"]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["computed_role"] == "superuser"

    team_names = {t["name"]: t["exists"] for t in data["teams"]}
    assert "Default Team" in team_names
    assert team_names["Default Team"] is True
    assert "NonExistentTeam" in team_names
    assert team_names["NonExistentTeam"] is False
