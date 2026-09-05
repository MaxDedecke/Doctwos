"""
Tests für core/oidc.py (E-12) — Protokoll- und Provisioning-Logik.

Läuft ohne echten Identity Provider: die HTTP-Aufrufe an Discovery-/Token-
Endpunkt werden gemockt, das ID-Token wird mit einem selbst erzeugten
RSA-Schlüsselpaar signiert und über ein eigenes JWKS verifiziert — dieselbe
Signatur-/Claims-Prüfung wie gegen einen echten IdP (Authlib macht dabei keine
Ausnahme für Tests), nur ohne Netzwerk. Die Provisioning-Tests (DB-Teil)
laufen wie die übrigen Backend-Tests gegen die konfigurierte DB.
"""

import time

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from joserfc import jwt as jose_jwt
from joserfc.jwk import RSAKey

import core.oidc as oidc
from core.users import get_by_oidc_subject
from models.database import User

ISSUER = "https://idp.example.com"
CLIENT_ID = "doctus-client"


@pytest.fixture(autouse=True)
def _reset_oidc_caches(monkeypatch):
    """Discovery/JWKS sind prozessweit gecacht — jeder Test startet blank,
    sonst leckt eine gemockte Antwort in den nächsten Test."""
    monkeypatch.setattr(oidc, "_metadata_cache", None)
    monkeypatch.setattr(oidc, "_jwks_cache", None)
    monkeypatch.setattr("core.config.OIDC_ISSUER", ISSUER)
    monkeypatch.setattr("core.config.OIDC_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr("core.config.OIDC_CLIENT_SECRET", "secret")
    monkeypatch.setattr("core.config.API_URL", "https://doctus.example.com")


@pytest.fixture
def rsa_jwk():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return RSAKey.import_key(pem, {"kid": "test-key"})


def _jwks_for(jwk) -> dict:
    return {"keys": [jwk.as_dict(private=False)]}


def _sign(jwk, claims: dict) -> str:
    header = {"alg": "RS256", "kid": "test-key"}
    return jose_jwt.encode(header, claims, jwk)


def _valid_claims(**overrides) -> dict:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "idp-subject-123",
        "email": "jane.doe@example.com",
        "name": "Jane Doe",
        "nonce": "expected-nonce",
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return claims


class _FakeTokenResponse:
    def __init__(self, status_code=200, id_token=None):
        self.status_code = status_code
        self._id_token = id_token
        self.text = "" if id_token else "token endpoint error"

    def json(self):
        return {"id_token": self._id_token} if self._id_token else {}


class _FakeHttpClient:
    """Ersetzt core.oidc._http_client() nur für den Token-POST — Discovery/
    JWKS werden in den meisten Tests direkt gemockt, nicht über HTTP."""

    def __init__(self, post_response=None, post_error=None):
        self._post_response = post_response
        self._post_error = post_error

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def post(self, url, data=None):
        if self._post_error:
            raise self._post_error
        return self._post_response


def _patch_discovery(monkeypatch, jwks):
    monkeypatch.setattr(
        oidc,
        "_discover",
        lambda: {
            "authorization_endpoint": f"{ISSUER}/auth",
            "token_endpoint": f"{ISSUER}/token",
            "jwks_uri": f"{ISSUER}/jwks",
        },
    )
    monkeypatch.setattr(oidc, "_jwks", lambda: jwks)


# ── build_authorization_url / verify_state_cookie ────────────────────────────


def test_build_authorization_url_contains_required_params(monkeypatch):
    _patch_discovery(monkeypatch, {"keys": []})
    url, cookie_value = oidc.build_authorization_url()

    assert url.startswith(f"{ISSUER}/auth?")
    assert f"client_id={CLIENT_ID}" in url
    assert "response_type=code" in url
    assert "state=" in url and "nonce=" in url

    # Die Cookie trägt dieselben state/nonce-Werte, die auch in der URL stehen —
    # sonst könnte verify_state_cookie() den zurückkommenden State nie bestätigen.
    payload = oidc._state_serializer.loads(cookie_value, max_age=60)
    assert payload["state"] in url
    assert payload["nonce"] in url


def test_verify_state_cookie_accepts_matching_state():
    cookie_value = oidc._state_serializer.dumps({"state": "abc", "nonce": "xyz"})
    nonce = oidc.verify_state_cookie(cookie_value, "abc")
    assert nonce == "xyz"


def test_verify_state_cookie_rejects_missing_cookie():
    with pytest.raises(oidc.OidcError):
        oidc.verify_state_cookie(None, "abc")


def test_verify_state_cookie_rejects_mismatched_state():
    cookie_value = oidc._state_serializer.dumps({"state": "abc", "nonce": "xyz"})
    with pytest.raises(oidc.OidcError):
        oidc.verify_state_cookie(cookie_value, "someone-elses-state")


def test_verify_state_cookie_rejects_tampered_signature():
    cookie_value = oidc._state_serializer.dumps({"state": "abc", "nonce": "xyz"})
    with pytest.raises(oidc.OidcError):
        oidc.verify_state_cookie(cookie_value + "tampered", "abc")


def test_verify_state_cookie_rejects_expired_cookie(monkeypatch):
    cookie_value = oidc._state_serializer.dumps({"state": "abc", "nonce": "xyz"})
    monkeypatch.setattr(oidc, "OIDC_STATE_MAX_AGE_SECONDS", -1)
    with pytest.raises(oidc.OidcError):
        oidc.verify_state_cookie(cookie_value, "abc")


# ── exchange_code: echte JWT-Signatur-/Claims-Prüfung gegen ein Test-JWKS ───


def test_exchange_code_accepts_a_validly_signed_token(monkeypatch, rsa_jwk):
    _patch_discovery(monkeypatch, _jwks_for(rsa_jwk))
    id_token = _sign(rsa_jwk, _valid_claims())
    monkeypatch.setattr(oidc, "_http_client", lambda: _FakeHttpClient(_FakeTokenResponse(id_token=id_token)))

    claims = oidc.exchange_code("some-code", expected_nonce="expected-nonce")

    assert claims["sub"] == "idp-subject-123"
    assert claims["email"] == "jane.doe@example.com"


def test_exchange_code_rejects_wrong_issuer(monkeypatch, rsa_jwk):
    _patch_discovery(monkeypatch, _jwks_for(rsa_jwk))
    id_token = _sign(rsa_jwk, _valid_claims(iss="https://not-the-configured-idp.example.com"))
    monkeypatch.setattr(oidc, "_http_client", lambda: _FakeHttpClient(_FakeTokenResponse(id_token=id_token)))

    with pytest.raises(oidc.OidcError):
        oidc.exchange_code("some-code", expected_nonce="expected-nonce")


def test_exchange_code_rejects_wrong_audience(monkeypatch, rsa_jwk):
    _patch_discovery(monkeypatch, _jwks_for(rsa_jwk))
    id_token = _sign(rsa_jwk, _valid_claims(aud="some-other-client"))
    monkeypatch.setattr(oidc, "_http_client", lambda: _FakeHttpClient(_FakeTokenResponse(id_token=id_token)))

    with pytest.raises(oidc.OidcError):
        oidc.exchange_code("some-code", expected_nonce="expected-nonce")


def test_exchange_code_rejects_expired_token(monkeypatch, rsa_jwk):
    _patch_discovery(monkeypatch, _jwks_for(rsa_jwk))
    now = int(time.time())
    id_token = _sign(rsa_jwk, _valid_claims(iat=now - 600, exp=now - 300))
    monkeypatch.setattr(oidc, "_http_client", lambda: _FakeHttpClient(_FakeTokenResponse(id_token=id_token)))

    with pytest.raises(oidc.OidcError):
        oidc.exchange_code("some-code", expected_nonce="expected-nonce")


def test_exchange_code_rejects_token_signed_by_unknown_key(monkeypatch, rsa_jwk):
    """Ein zweites, beim IdP nie registriertes Schlüsselpaar signiert — das
    JWKS im Test kennt nur `rsa_jwk`. Simuliert einen gefälschten Aussteller."""
    _patch_discovery(monkeypatch, _jwks_for(rsa_jwk))
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    other_jwk = RSAKey.import_key(other_pem, {"kid": "test-key"})
    id_token = _sign(other_jwk, _valid_claims())
    monkeypatch.setattr(oidc, "_http_client", lambda: _FakeHttpClient(_FakeTokenResponse(id_token=id_token)))

    with pytest.raises(oidc.OidcError):
        oidc.exchange_code("some-code", expected_nonce="expected-nonce")


def test_exchange_code_rejects_nonce_mismatch(monkeypatch, rsa_jwk):
    _patch_discovery(monkeypatch, _jwks_for(rsa_jwk))
    id_token = _sign(rsa_jwk, _valid_claims(nonce="a-different-nonce"))
    monkeypatch.setattr(oidc, "_http_client", lambda: _FakeHttpClient(_FakeTokenResponse(id_token=id_token)))

    with pytest.raises(oidc.OidcError):
        oidc.exchange_code("some-code", expected_nonce="expected-nonce")


def test_exchange_code_rejects_non_200_token_response(monkeypatch, rsa_jwk):
    _patch_discovery(monkeypatch, _jwks_for(rsa_jwk))
    monkeypatch.setattr(oidc, "_http_client", lambda: _FakeHttpClient(_FakeTokenResponse(status_code=400)))

    with pytest.raises(oidc.OidcError):
        oidc.exchange_code("some-code", expected_nonce="expected-nonce")


def test_exchange_code_rejects_missing_id_token(monkeypatch, rsa_jwk):
    _patch_discovery(monkeypatch, _jwks_for(rsa_jwk))
    monkeypatch.setattr(oidc, "_http_client", lambda: _FakeHttpClient(_FakeTokenResponse(id_token=None)))

    with pytest.raises(oidc.OidcError):
        oidc.exchange_code("some-code", expected_nonce="expected-nonce")


def test_exchange_code_handles_unreachable_token_endpoint(monkeypatch, rsa_jwk):
    _patch_discovery(monkeypatch, _jwks_for(rsa_jwk))
    monkeypatch.setattr(
        oidc, "_http_client", lambda: _FakeHttpClient(post_error=httpx.ConnectError("boom"))
    )

    with pytest.raises(oidc.OidcError):
        oidc.exchange_code("some-code", expected_nonce="expected-nonce")


# ── provision_or_link_user: JIT-Provisioning gegen die echte DB ─────────────


@pytest.fixture
def cleanup_oidc_users(db_session):
    def _delete():
        db_session.query(User).filter(User.oidc_subject.like("test-oidc-%")).delete(synchronize_session=False)
        db_session.commit()

    _delete()
    yield
    _delete()


def test_provision_or_link_user_creates_a_new_account(db_session, cleanup_oidc_users):
    claims = {
        "sub": "test-oidc-new-user",
        "email": "new.oidc.user@example.com",
        "name": "New OIDC User",
    }
    user = oidc.provision_or_link_user(claims, db_session)

    assert user.oidc_subject == "test-oidc-new-user"
    assert user.password_hash is None
    assert user.role == "user"
    assert user.is_active is True
    assert user.username == "new.oidc.user"
    assert user.email == "new.oidc.user@example.com"


def test_provision_or_link_user_finds_the_same_user_again(db_session, cleanup_oidc_users):
    claims = {"sub": "test-oidc-repeat-login", "email": "repeat@example.com"}
    first = oidc.provision_or_link_user(claims, db_session)
    second = oidc.provision_or_link_user(claims, db_session)

    assert first.id == second.id
    # Kein zweites Konto für denselben 'sub' angelegt.
    assert get_by_oidc_subject(db_session, "test-oidc-repeat-login").id == first.id


def test_provision_or_link_user_resolves_username_collisions(db_session, cleanup_oidc_users):
    existing = User(username="collide", password_hash="$argon2id$v=19$m=65536,t=3,p=4$x$y", role="user")
    db_session.add(existing)
    db_session.commit()
    try:
        claims = {"sub": "test-oidc-collide", "email": "collide@example.com"}
        user = oidc.provision_or_link_user(claims, db_session)
        assert user.username != "collide"
        assert user.username.startswith("collide-")
    finally:
        db_session.query(User).filter(User.username == "collide").delete()
        db_session.commit()


def test_provision_or_link_user_rejects_deactivated_account(db_session, cleanup_oidc_users):
    claims = {"sub": "test-oidc-deactivated", "email": "deactivated@example.com"}
    user = oidc.provision_or_link_user(claims, db_session)
    user.is_active = False
    db_session.commit()

    with pytest.raises(oidc.OidcError):
        oidc.provision_or_link_user(claims, db_session)


def test_provision_or_link_user_requires_a_subject_claim(db_session, cleanup_oidc_users):
    with pytest.raises(oidc.OidcError):
        oidc.provision_or_link_user({"email": "no-sub@example.com"}, db_session)
