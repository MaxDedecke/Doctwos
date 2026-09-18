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

import json
import logging
import re
import secrets
import time
from urllib.parse import urlencode

import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from joserfc import jwt as jose_jwt
from joserfc.errors import InvalidKeyIdError, JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry
from sqlalchemy.orm import Session

import core.config as cfg
from core.users import create_oidc_user, get_by_oidc_subject
from models.database import Team, TeamMembership, User


logger = logging.getLogger(__name__)

OIDC_STATE_COOKIE_NAME = "doctus_oidc_state"
# Reicht für einen Login-Vorgang beim IdP (Redirect, Login-Formular, Redirect
# zurück) — deutlich kürzer als die 14-Tage-Session-Cookie, absichtlich.
OIDC_STATE_MAX_AGE_SECONDS = 600

_state_serializer = URLSafeTimedSerializer(cfg.SESSION_SECRET_KEY, salt="doctus-oidc-state")

# Discovery-Dokument und JWKS ändern sich beim laufenden Prozess praktisch nie —
# pro Prozess einmal geholt statt bei jedem Login erneut.
# Rotiert der IdP seine Signaturschlüssel (Keycloak im Normalbetrieb), wird der
# JWKS-Cache bei unbekannter kid einmalig neu geladen (O-160). Ein Mindestabstand
# (_JWKS_MIN_REFRESH_INTERVAL_SECONDS) verhindert DoS/Überlastung des IdP bei ungültigen Tokens.
_metadata_cache: dict | None = None
_jwks_cache: dict | None = None
_last_jwks_fetch: float = 0.0
_JWKS_MIN_REFRESH_INTERVAL_SECONDS = 10.0


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


def _jwks(force_refresh: bool = False) -> dict:
    global _jwks_cache, _last_jwks_fetch
    now = time.monotonic()
    if _jwks_cache is not None and not force_refresh:
        return _jwks_cache
    if (
        force_refresh
        and _jwks_cache is not None
        and (now - _last_jwks_fetch < _JWKS_MIN_REFRESH_INTERVAL_SECONDS)
    ):
        logger.warning(
            "OIDC-JWKS-Refresh übersprungen: letzter Abruf liegt erst %.1fs zurück (Minimum: %.1fs)",
            now - _last_jwks_fetch,
            _JWKS_MIN_REFRESH_INTERVAL_SECONDS,
        )
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
    _last_jwks_fetch = now
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
        try:
            token = jose_jwt.decode(id_token, key_set, algorithms=["RS256"])
        except InvalidKeyIdError as exc:
            # Rotiert der IdP seine Signaturschlüssel (Keycloak im Normalbetrieb),
            # kennt der gecachte JWKS den neuen kid noch nicht. Genau ein Refresh-Versuch (O-160).
            logger.info(
                "OIDC-ID-Token verweist auf unbekannten kid (%s) — versuche JWKS-Cache zu aktualisieren",
                exc,
            )
            key_set = KeySet.import_key_set(_jwks(force_refresh=True))
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


def _collect_claim_values(claims: dict, claim_path: str) -> set[str]:
    """Liest einen Wert oder eine Liste von Werten aus verschachtelten Dicts (z. B. 'realm_access.roles')."""
    if not claim_path:
        return set()
    curr = claims
    for part in claim_path.split("."):
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        else:
            return set()
    if isinstance(curr, list):
        return {str(x).strip() for x in curr if x}
    if isinstance(curr, str):
        return {s.strip() for s in curr.split(",") if s.strip()}
    return set()


def extract_idp_roles_and_groups(claims: dict) -> set[str]:
    """Extrahiert alle Rollen- und Gruppennamen aus den Token-Claims.

    Durchsucht die konfigurierten Claim-Schlüssel (cfg.OIDC_ROLES_CLAIM,
    cfg.OIDC_GROUPS_CLAIM) sowie Standard-Pfade für Keycloak, Entra ID und Okta.
    """
    results: set[str] = set()

    for key in [cfg.OIDC_ROLES_CLAIM, cfg.OIDC_GROUPS_CLAIM, "roles", "groups"]:
        if key:
            results.update(_collect_claim_values(claims, key))

    # Keycloak realm_access.roles
    realm_access = claims.get("realm_access")
    if isinstance(realm_access, dict):
        roles = realm_access.get("roles")
        if isinstance(roles, list):
            results.update(str(r).strip() for r in roles if r)

    # Keycloak resource_access.<client_id>.roles
    resource_access = claims.get("resource_access")
    if isinstance(resource_access, dict):
        for client_data in resource_access.values():
            if isinstance(client_data, dict):
                r_roles = client_data.get("roles")
                if isinstance(r_roles, list):
                    results.update(str(r).strip() for r in r_roles if r)

    return results


def get_oidc_user_role(idp_items: set[str]) -> str:
    """Ermittelt die Doctus-Rolle ('superuser' oder 'user') anhand von OIDC_ADMIN_ROLES."""
    if not cfg.OIDC_ADMIN_ROLES:
        return "user"
    admin_roles = {r.strip() for r in cfg.OIDC_ADMIN_ROLES.split(",") if r.strip()}
    if idp_items & admin_roles:
        return "superuser"
    return "user"


def get_oidc_target_teams(idp_items: set[str]) -> set[str]:
    """Ermittelt die Namen der Doctus-Teams anhand OIDC_DEFAULT_TEAM und OIDC_TEAM_MAPPING."""
    target_teams: set[str] = set()

    if cfg.OIDC_DEFAULT_TEAM:
        target_teams.add(cfg.OIDC_DEFAULT_TEAM.strip())

    if cfg.OIDC_TEAM_MAPPING:
        mapping: dict[str, str] = {}
        mapping_str = cfg.OIDC_TEAM_MAPPING.strip()
        if mapping_str.startswith("{"):
            try:
                mapping = json.loads(mapping_str)
            except Exception as exc:
                logger.warning("Ungültiges JSON in OIDC_TEAM_MAPPING: %s", exc)
        else:
            for pair in mapping_str.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    mapping[k.strip()] = v.strip()
                elif ":" in pair:
                    k, v = pair.split(":", 1)
                    mapping[k.strip()] = v.strip()

        for item in idp_items:
            # Exakter Treffer oder ohne führenden Schrägstrich (z. B. "/dev" -> "dev")
            team_name = mapping.get(item) or mapping.get(item.lstrip("/"))
            if team_name:
                target_teams.add(team_name)

    return target_teams


def sync_oidc_user_teams_and_role(db: Session, user: User, claims: dict) -> None:
    """Aktualisiert Rolle und Team-Mitgliedschaften basierend auf den IdP-Claims."""
    idp_items = extract_idp_roles_and_groups(claims)

    if cfg.OIDC_ADMIN_ROLES:
        new_role = get_oidc_user_role(idp_items)
        if user.role != new_role:
            logger.info(
                "OIDC-Rolle für Nutzer %s aktualisiert: %s -> %s",
                user.username,
                user.role,
                new_role,
            )
            user.role = new_role

    target_team_names = get_oidc_target_teams(idp_items)
    if target_team_names:
        for team_name in target_team_names:
            team = db.query(Team).filter(Team.name == team_name).first()
            if not team:
                logger.warning(
                    "OIDC-Team '%s' existiert in Doctus nicht — Zuordnung für %s übersprungen.",
                    team_name,
                    user.username,
                )
                continue
            existing = (
                db.query(TeamMembership)
                .filter(TeamMembership.user_id == user.id, TeamMembership.team_id == team.id)
                .first()
            )
            if not existing:
                db.add(TeamMembership(user_id=user.id, team_id=team.id))
                logger.info("OIDC-Nutzer %s zu Team '%s' hinzugefügt.", user.username, team_name)


def provision_or_link_user(claims: dict, db: Session) -> User:
    """Erster Login: legt einen neuen Nutzer an (Standardrolle 'user', kein lokales
    Passwort). Jeder weitere Login findet ihn über 'sub' wieder.
    Wurden OIDC_ADMIN_ROLES oder OIDC_DEFAULT_TEAM / OIDC_TEAM_MAPPING konfiguriert
    (O-164), werden Rolle und Teamzugehörigkeiten synchronisiert.

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
        sync_oidc_user_teams_and_role(db, user, claims)
        db.commit()
        return user

    email = claims.get("email")
    base_candidate = (
        (email.split("@")[0] if email else None) or claims.get("preferred_username") or subject
    )
    username = _unique_username(db, _slugify_username(base_candidate))
    name = claims.get("name") or email or username

    idp_items = extract_idp_roles_and_groups(claims)
    role = get_oidc_user_role(idp_items)

    user = create_oidc_user(
        db,
        username=username,
        subject=subject,
        name=name,
        email=email,
        role=role,
        commit=False,
    )
    db.flush()
    sync_oidc_user_teams_and_role(db, user, claims)
    db.commit()
    db.refresh(user)

    return user
