"""
backend/core/oidc.py
=====================
Optionaler zweiter Anmeldeweg neben dem lokalen Passwort-Login (api/auth.py,
core/users.py): OpenID Connect Authorization Code Flow gegen einen vom Kunden
betriebenen Identity Provider (Keycloak, Entra ID, Okta, ...). Deaktiviert,
solange core/config.py::oidc_enabled() False liefert.

State/Nonce laufen über eine eigene, kurzlebige signierte Cookie statt
Server-Session-Speicher — bleibt konsistent mit "Backend bleibt zustandslos"
(CLAUDE.md Regel 3). Die JWT-/JWKS-Prüfung des ID-Tokens läuft über `joserfc`
(BSD-3-Clause, reines Python auf Basis von `cryptography`, das ohnehin schon
Abhängigkeit ist) statt selbst gebauter Signaturprüfung — Rule 4 ("keine
schweren SDKs") zielt auf Anbieter-SDKs, nicht auf eine schmale, geprüfte
Kryptobibliothek für ein sicherheitskritisches Protokoll. `algorithms=["RS256"]`
wird beim Decode explizit vorgegeben statt dem `alg`-Header des Tokens zu
vertrauen — sonst könnte ein manipuliertes Token selbst bestimmen, mit welchem
Verfahren (bis hin zu "none") es geprüft wird.

Design-Entscheidungen im Detail: docs/ENTSCHEIDUNGEN.md E-12.
"""

import logging
import re
import secrets
from urllib.parse import urlencode

import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from joserfc import jwt as jose_jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry
from sqlalchemy.orm import Session

import core.config as cfg
from core.users import create_oidc_user, get_by_oidc_subject
from models.database import User

logger = logging.getLogger(__name__)

OIDC_STATE_COOKIE_NAME = "doctus_oidc_state"
# Reicht für einen Login-Vorgang beim IdP (Redirect, Login-Formular, Redirect
# zurück) — deutlich kürzer als die 14-Tage-Session-Cookie, absichtlich.
OIDC_STATE_MAX_AGE_SECONDS = 600

_state_serializer = URLSafeTimedSerializer(cfg.SESSION_SECRET_KEY, salt="doctus-oidc-state")

# Discovery-Dokument und JWKS ändern sich beim laufenden Prozess praktisch nie —
# pro Prozess einmal geholt statt bei jedem Login erneut. Ein Deployment, das den
# IdP wechselt oder dessen Signaturschlüssel rotiert, braucht ohnehin einen
# Neustart (neue OIDC_ISSUER/-Secrets in .env), der den Cache mit auflöst.
_metadata_cache: dict | None = None
_jwks_cache: dict | None = None


class OidcError(Exception):
    """Nutzerlesbare Fehlermeldung für den Callback-Handler in api/auth.py."""


def _http_client() -> httpx.Client:
    return httpx.Client(timeout=10.0)


def redirect_uri() -> str:
    return f"{cfg.API_URL}/auth/oidc/callback"


def _discover() -> dict:
    global _metadata_cache
    if _metadata_cache is not None:
        return _metadata_cache
    url = f"{cfg.OIDC_ISSUER}/.well-known/openid-configuration"
    try:
        with _http_client() as client:
            resp = client.get(url)
            resp.raise_for_status()
            metadata = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("OIDC-Discovery gegen %s fehlgeschlagen: %s", url, exc)
        raise OidcError("Identity Provider ist gerade nicht erreichbar.") from exc
    _metadata_cache = metadata
    return metadata


def _jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    metadata = _discover()
    try:
        with _http_client() as client:
            resp = client.get(metadata["jwks_uri"])
            resp.raise_for_status()
            jwks = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("OIDC-JWKS-Abruf fehlgeschlagen: %s", exc)
        raise OidcError("Identity Provider ist gerade nicht erreichbar.") from exc
    _jwks_cache = jwks
    return jwks


def build_authorization_url() -> tuple[str, str]:
    """Liefert (Redirect-URL zum IdP, Wert für die signierte State-Cookie)."""
    metadata = _discover()
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    params = {
        "response_type": "code",
        "client_id": cfg.OIDC_CLIENT_ID,
        "redirect_uri": redirect_uri(),
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
    }
    url = f"{metadata['authorization_endpoint']}?{urlencode(params)}"
    cookie_value = _state_serializer.dumps({"state": state, "nonce": nonce})
    return url, cookie_value


def verify_state_cookie(cookie_value: str | None, returned_state: str | None) -> str:
    """Prüft den vom IdP zurückgelieferten State gegen die eigene signierte
    Cookie (CSRF-Schutz) und liefert die zugehörige Nonce zurück."""
    if not cookie_value:
        raise OidcError("Der Anmeldevorgang ist abgelaufen. Bitte erneut versuchen.")
    try:
        payload = _state_serializer.loads(cookie_value, max_age=OIDC_STATE_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired) as exc:
        raise OidcError("Der Anmeldevorgang ist abgelaufen. Bitte erneut versuchen.") from exc
    if not returned_state or not secrets.compare_digest(payload["state"], returned_state):
        raise OidcError("Der Anmeldevorgang konnte nicht bestätigt werden. Bitte erneut versuchen.")
    return payload["nonce"]


def exchange_code(code: str, expected_nonce: str) -> dict:
    """Tauscht den Authorization Code gegen Tokens, prüft das ID-Token
    (Signatur über JWKS, Issuer, Audience, Ablauf, Nonce) und liefert dessen
    Claims zurück — ab hier gelten sie als verifiziert echt vom IdP."""
    metadata = _discover()
    try:
        with _http_client() as client:
            resp = client.post(
                metadata["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri(),
                    "client_id": cfg.OIDC_CLIENT_ID,
                    "client_secret": cfg.OIDC_CLIENT_SECRET,
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("OIDC-Token-Austausch fehlgeschlagen: %s", exc)
        raise OidcError("Identity Provider ist gerade nicht erreichbar.") from exc

    if resp.status_code != 200:
        logger.warning("OIDC-Token-Endpunkt lieferte %s: %s", resp.status_code, resp.text[:500])
        raise OidcError("Anmeldung beim Identity Provider ist fehlgeschlagen.")

    id_token = resp.json().get("id_token")
    if not id_token:
        raise OidcError("Identity Provider hat kein ID-Token geliefert.")

    try:
        key_set = KeySet.import_key_set(_jwks())
        # algorithms=["RS256"] bewusst fest statt dem alg-Header des Tokens zu
        # folgen (Alg-Confusion-Schutz, siehe Moduldocstring).
        token = jose_jwt.decode(id_token, key_set, algorithms=["RS256"])
        claims_registry = JWTClaimsRegistry(
            iss={"essential": True, "value": cfg.OIDC_ISSUER},
            aud={"essential": True, "value": cfg.OIDC_CLIENT_ID},
        )
        claims_registry.validate(token.claims)  # prüft zusätzlich exp/nbf per Default
    except JoseError as exc:
        logger.warning("OIDC-ID-Token-Validierung fehlgeschlagen: %s", exc)
        raise OidcError("Identity Provider hat ein ungültiges ID-Token geliefert.") from exc

    claims = token.claims
    if claims.get("nonce") != expected_nonce:
        raise OidcError("Der Anmeldevorgang konnte nicht bestätigt werden. Bitte erneut versuchen.")

    return dict(claims)


_SLUG_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def _slugify_username(candidate: str) -> str:
    slug = _SLUG_RE.sub("-", candidate).strip("-").lower()
    return slug or "sso-user"


def _unique_username(db: Session, base: str) -> str:
    username = base
    suffix = 1
    while db.query(User).filter(User.username == username).first() is not None:
        suffix += 1
        username = f"{base}-{suffix}"
    return username


def provision_or_link_user(claims: dict, db: Session) -> User:
    """Erster Login: legt einen neuen Nutzer an (Rolle 'user', kein lokales
    Passwort). Jeder weitere Login findet ihn über 'sub' wieder.

    Bewusst KEIN automatisches Verknüpfen über die E-Mail-Adresse mit einem
    bestehenden lokalen Konto (E-12) — die Claims kommen zwar vom vertrauten
    IdP, aber ein zweiter, unabhängiger Fund derselben E-Mail ist ein zu
    riskanter Schlüssel für eine Kontoübernahme, falls ein IdP sie je falsch
    oder wiederverwendet ausliefert. 'sub' ist laut OIDC-Spezifikation stabil
    und pro IdP eindeutig.
    """
    subject = claims.get("sub")
    if not subject:
        raise OidcError("Identity Provider hat keine Nutzerkennung (sub) geliefert.")

    user = get_by_oidc_subject(db, subject)
    if user is not None:
        if not user.is_active:
            raise OidcError("Dieses Konto ist deaktiviert.")
        return user

    email = claims.get("email")
    base_candidate = (
        (email.split("@")[0] if email else None)
        or claims.get("preferred_username")
        or subject
    )
    username = _unique_username(db, _slugify_username(base_candidate))
    name = claims.get("name") or email or username

    return create_oidc_user(db, username=username, subject=subject, name=name, email=email)
