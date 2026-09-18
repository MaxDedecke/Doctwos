"""
backend/api/config_router.py
=============================
Öffentlicher Konfigurations-Endpoint — kein Auth erforderlich.

GET /config/features gibt die Feature-Flags aus /config/features.json zurück.
Die Datei wird pro Request neu gelesen, sodass Änderungen ohne Rebuild wirksam werden.
Fehlt die Datei, wird ein leeres Objekt zurückgegeben (alle Defaults greifen im Frontend).
"""

import json
import logging
import os
import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import core.config as cfg
import core.oidc as oidc
from core.db_setup import get_db
from core.oidc import redirect_uri
from core.teams import require_admin
from models.database import Team

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/config", tags=["config"])

DEFAULT_FEATURES_PATH = "/config/features.json"


def _features_path() -> str:
    """Pro Request auflösen, nicht beim Import einfrieren. Ein Modul-Konstante
    hätte den Pfad an den Zeitpunkt des ersten Imports gebunden — genau das, was
    der Docstring oben ausschließt, und der Grund, warum FEATURES_CONFIG_PATH in
    Tests wirkungslos blieb."""
    return os.environ.get("FEATURES_CONFIG_PATH", DEFAULT_FEATURES_PATH)


def _with_auth_flags(data: dict) -> dict:
    """Kommt nicht aus features.json (kein Deployment soll SSO durch eine falsch
    kopierte Config-Datei versehentlich aus- oder anschalten) — liest stattdessen
    direkt core/config.py::oidc_enabled(), das dieselben OIDC_*-Env-Variablen wie
    core/oidc.py auswertet."""
    data.setdefault("auth", {})["ssoEnabled"] = cfg.oidc_enabled()
    return data


@router.get("/features")
def get_features():
    try:
        with open(_features_path(), "r") as f:
            data = json.load(f)

        env_allow = os.environ.get("ALLOW_CLOUD_LLM", "").lower()
        if env_allow in ("true", "1"):
            if "llm" not in data:
                data["llm"] = {}
            data["llm"]["allowCloudProviders"] = True
        elif env_allow in ("false", "0"):
            if "llm" not in data:
                data["llm"] = {}
            data["llm"]["allowCloudProviders"] = False

        return JSONResponse(content=_with_auth_flags(data))
    except FileNotFoundError:
        data = {}
        env_allow = os.environ.get("ALLOW_CLOUD_LLM", "").lower()
        if env_allow in ("true", "1"):
            data["llm"] = {"allowCloudProviders": True}
        return JSONResponse(content=_with_auth_flags(data))
    except Exception as e:
        logger.warning(f"Fehler beim Lesen von features.json: {e}")
        return JSONResponse(content=_with_auth_flags({}))


# ── Admin-Endpoints: System- & SSO-Konfiguration (O-164) ────────────────────


class OidcMappingSimulationRequest(BaseModel):
    roles: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)


@router.get("/system", dependencies=[Depends(require_admin)])
def get_system_config(db: Session = Depends(get_db)):
    """Liefert Administratoren eine strukturierte Übersicht der aktuellen
    Laufzeit-, Authentifizierungs- und SSO-Konfiguration (ohne Klartext-Secrets).
    """
    mapping: dict[str, str] = {}
    if cfg.OIDC_TEAM_MAPPING:
        mapping_str = cfg.OIDC_TEAM_MAPPING.strip()
        if mapping_str.startswith("{"):
            try:
                mapping = json.loads(mapping_str)
            except Exception:
                mapping = {"error": "Ungültiges JSON in OIDC_TEAM_MAPPING"}
        else:
            for pair in mapping_str.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    mapping[k.strip()] = v.strip()
                elif ":" in pair:
                    k, v = pair.split(":", 1)
                    mapping[k.strip()] = v.strip()

    existing_teams = [t[0] for t in db.query(Team.name).order_by(Team.name).all()]

    sso_info = {
        "enabled": cfg.oidc_enabled(),
        "issuer": cfg.OIDC_ISSUER or None,
        "client_id": cfg.OIDC_CLIENT_ID or None,
        "client_secret_configured": bool(cfg.OIDC_CLIENT_SECRET),
        "redirect_uri": redirect_uri() if (cfg.oidc_enabled() or cfg.API_URL) else None,
        "default_team": cfg.OIDC_DEFAULT_TEAM or None,
        "default_team_exists": (cfg.OIDC_DEFAULT_TEAM in existing_teams)
        if cfg.OIDC_DEFAULT_TEAM
        else None,
        "admin_roles": [r.strip() for r in cfg.OIDC_ADMIN_ROLES.split(",") if r.strip()]
        if cfg.OIDC_ADMIN_ROLES
        else [],
        "team_mapping": mapping,
        "roles_claim": cfg.OIDC_ROLES_CLAIM or "roles",
        "groups_claim": cfg.OIDC_GROUPS_CLAIM or "groups",
    }

    system_info = {
        "version": os.environ.get("DOCTUS_VERSION", "latest"),
        "api_url": cfg.API_URL,
        "frontend_url": cfg.FRONTEND_URL,
        "log_level": cfg.LOG_LEVEL,
        "mcp_audit_retention_days": cfg.MCP_AUDIT_RETENTION_DAYS,
        "watched_folder": os.environ.get("WATCHED_FOLDER") or None,
        "llm_model": cfg.OLLAMA_LLM_MODEL,
        "embed_model": cfg.OLLAMA_EMBED_MODEL,
        "context_window": cfg.OLLAMA_NUM_CTX,
    }

    secrets_info = {
        "master_encryption_key_configured": bool(os.getenv("MASTER_ENCRYPTION_KEY")),
        "session_secret_key_configured": bool(cfg.SESSION_SECRET_KEY),
    }

    return {
        "sso": sso_info,
        "system": system_info,
        "secrets": secrets_info,
        "existing_teams": existing_teams,
    }


@router.post("/oidc/test-connection", dependencies=[Depends(require_admin)])
def test_oidc_connection():
    """Testet die Erreichbarkeit des konfigurierten OIDC-Issuers und ruft dessen
    Discovery-Metadaten ab.
    """
    if not cfg.OIDC_ISSUER:
        return {
            "success": False,
            "error": "Kein OIDC_ISSUER konfiguriert.",
        }

    start_time = time.monotonic()
    try:
        meta = oidc._discover()
        duration_ms = round((time.monotonic() - start_time) * 1000, 1)
        return {
            "success": True,
            "duration_ms": duration_ms,
            "issuer": meta.get("issuer"),
            "authorization_endpoint": meta.get("authorization_endpoint"),
            "token_endpoint": meta.get("token_endpoint"),
            "userinfo_endpoint": meta.get("userinfo_endpoint"),
            "jwks_uri": meta.get("jwks_uri"),
            "end_session_endpoint": meta.get("end_session_endpoint"),
        }
    except Exception as exc:
        duration_ms = round((time.monotonic() - start_time) * 1000, 1)
        return {
            "success": False,
            "duration_ms": duration_ms,
            "error": str(exc),
        }


@router.post("/oidc/simulate-mapping", dependencies=[Depends(require_admin)])
def simulate_oidc_mapping(
    req: OidcMappingSimulationRequest,
    db: Session = Depends(get_db),
):
    """Simuliert für gegebene Rollen und Gruppen die resultierende Doctus-Rolle
    und die zugeordneten Teams gemäß aktueller OIDC-Konfiguration.
    """
    claims = {
        "roles": req.roles,
        "groups": req.groups,
    }
    idp_items = oidc.extract_idp_roles_and_groups(claims)
    computed_role = oidc.get_oidc_user_role(idp_items)
    target_teams = oidc.get_oidc_target_teams(idp_items)

    existing_teams = {t[0] for t in db.query(Team.name).all()}
    teams_result = [
        {
            "name": team_name,
            "exists": team_name in existing_teams,
        }
        for team_name in sorted(list(target_teams))
    ]

    return {
        "computed_role": computed_role,
        "extracted_items": sorted(list(idp_items)),
        "teams": teams_result,
    }
