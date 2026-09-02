"""
backend/core/config.py
=======================
Zentrale Konfiguration für den Doctus-Backend-Service.

Alle Umgebungsvariablen und geteilten Konstanten sind hier definiert.
Router-Module importieren von hier statt aus main.py oder aus den Funktionen
heraus — so ist ein Modell-Wechsel oder URL-Änderung an einer Stelle erledigt.

Mutable State:
    current_llm_model ist absichtlich mutierbar, da der /model-info POST-Endpoint
    das aktive LLM im laufenden Betrieb über die UI umschalten kann.
    Diese Änderung gilt nur bis zum nächsten Neustart des Containers.
"""

import json
import os
from celery import Celery

# ── Logging ───────────────────────────────────────────────────────────────────

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


# MCP audit entries are retained for a bounded period so the audit table cannot
# grow without limit. Deployments can choose a stricter customer policy via env.
MCP_AUDIT_RETENTION_DAYS: int = _positive_int_env("MCP_AUDIT_RETENTION_DAYS", 90)

# ── Ollama ────────────────────────────────────────────────────────────────────

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3")

# ── OpenAI-Reasoning-Modelle ─────────────────────────────────────────────────
# Klassische o1/o3/o4-Serie sowie die Reasoning-Stufen der GPT-5.6-Familie
# (Sol/Terra/Luna) lehnen einen vom Default (1) abweichenden "temperature"-Wert
# mit HTTP 400 ab. Lebt hier statt in agent.py/mcp_client.py, weil beide
# Module sich sonst gegenseitig importieren müssten (agent.py importiert schon
# MCPClient aus mcp_client.py).
_OPENAI_REASONING_MODEL_PREFIXES = ("o1", "o3", "o4")
_OPENAI_REASONING_MODEL_SUFFIXES = ("-sol", "-terra", "-luna")


def openai_model_supports_custom_temperature(model: str) -> bool:
    name = (model or "").lower()
    if name.startswith(_OPENAI_REASONING_MODEL_PREFIXES):
        return False
    if name.endswith(_OPENAI_REASONING_MODEL_SUFFIXES):
        return False
    return True

# Das aktive LLM-Modell — kann per /model-info POST zur Laufzeit geändert werden.
# Bis zur ersten Auslieferung ist das lokale LLM bewusst deaktiviert: der
# CPU-only-Pilot lädt nur bge-m3. Ein Liefer-/GPU-Host setzt OLLAMA_LLM_MODEL
# explizit auf den validierten Modell-Tag (siehe .env.example/DEPLOYMENT.md).
OLLAMA_LLM_MODEL: str = os.getenv("OLLAMA_LLM_MODEL", "disabled")


def resolve_ollama_model(requested: str | None = None) -> str:
    """Ollama-Modellname für einen Chat/JSON-Call: Request-Override, sonst
    OLLAMA_LLM_MODEL."""
    model = (requested or OLLAMA_LLM_MODEL).strip()
    if not model or model == "disabled":
        raise RuntimeError(
            "Lokales Ollama-LLM ist für dieses Deployment deaktiviert; "
            "LLM_MODEL auf einem ausreichend dimensionierten Host konfigurieren."
        )
    return model

# ── Queue & Datenbank ─────────────────────────────────────────────────────────

REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Celery-Client im Backend (nur zum Einreihen von Tasks — Ausführung im Parser-Worker)
celery_app = Celery("tasks", broker=REDIS_URL)

# ── Dateisystem ───────────────────────────────────────────────────────────────

REPOS_ROOT: str = "/repos"
UPLOADS_DIR: str = "/repos/uploads"

# ── Auth (lokal) ──────────────────────────────────────────────────────────────
# Doctus authentifiziert lokal gegen die eigene users-Tabelle (F-001): kein IdP,
# kein Netzzugang, keine Fremdkomponente im Betriebshandbuch. Die Session-Schicht
# darunter (signierte HTTP-only-Cookie) ist unverändert die aus dem Template.

# Signiert die App-eigene Session-Cookie.
# Kein Default: eine leere/fehlende Signierung macht Session- und OAuth-State-Cookies
# fälschbar. install.sh/install-offline.sh generieren den Wert automatisch — wer die
# Container anders hochzieht (docker-compose direkt, k8s, ...) muss ihn selbst setzen.
SESSION_SECRET_KEY: str = os.getenv("SESSION_SECRET_KEY", "")
if not SESSION_SECRET_KEY:
    raise RuntimeError(
        "SESSION_SECRET_KEY ist nicht gesetzt. Generieren mit: "
        "openssl rand -base64 32 — und in .env eintragen."
    )

# Für CORS (Cookies + allow_origins=["*"] ist inkompatibel) und Redirect nach Login
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

# ── Superuser-Bootstrap (F-001) ───────────────────────────────────────────────
# Beim ersten Start wird genau ein Superuser angelegt. Ist kein Passwort gesetzt,
# generiert core/db_setup.py eines und schreibt es EINMALIG ins Startlog — die
# Software ist damit ohne DB-Zugriff in Betrieb zu nehmen.
BOOTSTRAP_SUPERUSER: str = os.getenv("BOOTSTRAP_SUPERUSER", "admin")
BOOTSTRAP_SUPERUSER_PASSWORD: str = os.getenv("BOOTSTRAP_SUPERUSER_PASSWORD", "")
BOOTSTRAP_SUPERUSER_EMAIL: str = os.getenv("BOOTSTRAP_SUPERUSER_EMAIL", "")

# ── Cloud-LLM-Opt-in-Gate ─────────────────────────────────────────────────────
# Zentral hier statt pro Aufrufer dupliziert: jeder Call-Site, der einen
# Cloud-Provider (OpenAI/Gemini/Anthropic) tatsächlich aufrufen könnte —
# aktuell Chat (api/chat.py) — muss vor dem Aufruf cloud_llm_allowed() prüfen.

CLOUD_LLM_PROVIDERS: set[str] = {"openai", "gemini", "anthropic"}


def cloud_llm_allowed() -> bool:
    """
    Liest dieselbe config/features.json wie api/config_router.py. Default False
    (deckt sich mit frontend/lib/features.ts::DEFAULT_FEATURES.llm.allowCloudProviders),
    damit ein Deployment ohne/mit kaputter Config-Datei On-Premise-only bleibt, im
    Sinne von docs/POSITIONING.md's "keine Cloud-Abhängigkeiten"-Zusage — Cloud-LLM-
    Profile (OpenAI/Gemini/Anthropic) sind ein expliziter Opt-in pro Kunde.

    Pfad wird bei jedem Aufruf frisch aus der Env gelesen (nicht als Modul-Konstante
    gecacht) — Tests setzen FEATURES_CONFIG_PATH per monkeypatch zur Laufzeit.
    """
    env_allow = os.environ.get("ALLOW_CLOUD_LLM", "").lower()
    if env_allow in ("true", "1"):
        return True
    if env_allow in ("false", "0"):
        return False

    path = os.environ.get("FEATURES_CONFIG_PATH", "/config/features.json")
    try:
        with open(path, "r") as f:
            return bool(json.load(f).get("llm", {}).get("allowCloudProviders", False))
    except Exception:
        return False
