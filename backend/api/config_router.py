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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/config", tags=["config"])

FEATURES_PATH = os.environ.get("FEATURES_CONFIG_PATH", "/config/features.json")


@router.get("/features")
def get_features():
    try:
        with open(FEATURES_PATH, "r") as f:
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

        return JSONResponse(content=data)
    except FileNotFoundError:
        data = {}
        env_allow = os.environ.get("ALLOW_CLOUD_LLM", "").lower()
        if env_allow in ("true", "1"):
            data["llm"] = {"allowCloudProviders": True}
        return JSONResponse(content=data)
    except Exception as e:
        logger.warning(f"Fehler beim Lesen von features.json: {e}")
        return JSONResponse(content={})
