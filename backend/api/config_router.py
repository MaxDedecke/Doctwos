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

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import core.config as cfg

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
