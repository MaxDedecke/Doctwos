"""
Tests für backend/api/system.py (O-113).

`/health` und `/models` sprechen Ollama an -- hier über einen Fake-AsyncClient
simuliert statt gegen eine echte Instanz zu laufen: dieses Environment hat
keinen erreichbaren Ollama mit geladenem Chat-Modell, gegen den getestet
werden könnte, und beide Routen sollen davon unabhängig deterministisch
bleiben.

Schwerpunkt liegt auf `POST /model-info` (O-035): der Endpunkt mutiert
`cfg.OLLAMA_LLM_MODEL` als **globalen Prozess-State** -- laut Moduldocstring
gewollt, aber nirgends per Test festgehalten. Die Tests hier pinnen genau
dieses Verhalten fest (ein Aufruf wirkt auf JEDEN nachfolgenden Request, nicht
nur den eigenen), damit eine künftige Umstellung auf request-/profilgebundene
Modellwahl (O-035) als bewusste, sichtbare Verhaltensänderung im Diff auftaucht
statt stillschweigend zu passieren -- der Test dazu ist unten als solcher
markiert und muss kippen, sobald O-035 umgesetzt wird.

Jeder Test, der `cfg.OLLAMA_LLM_MODEL`/`cfg.OLLAMA_EMBED_MODEL` verändert,
pinnt den Ausgangswert vorher per `monkeypatch.setattr(cfg, "...", cfg....)`
fest, damit die Mutation nicht über den eigenen Testfall hinaus wirkt.
"""

import api.system as system_api
import core.config as cfg


class _FakeOllamaResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


class _FakeOllamaClient:
    """Steht für httpx.AsyncClient ein, damit /health und /models nicht von
    einer echten, erreichbaren Ollama-Instanz abhängen."""

    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, *args, **kwargs):
        if self._raises:
            raise self._raises
        return self._response


def _patch_ollama_http(monkeypatch, *, response=None, raises=None):
    monkeypatch.setattr(
        system_api.httpx,
        "AsyncClient",
        lambda *a, **k: _FakeOllamaClient(response=response, raises=raises),
    )


def test_root_reports_running(unauthenticated_client):
    res = unauthenticated_client.get("/")
    assert res.status_code == 200
    assert res.json() == {"message": "Doctus AI Backend is running"}


# ── GET /health ────────────────────────────────────────────────────────────


def test_health_reports_healthy_when_everything_reachable(unauthenticated_client, monkeypatch):
    _patch_ollama_http(monkeypatch, response=_FakeOllamaResponse(200))
    res = unauthenticated_client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "healthy"
    assert body["checks"] == {"database": "ok", "redis": "ok", "ollama": "ok"}


def test_health_reports_degraded_and_503_when_ollama_unreachable(
    unauthenticated_client, monkeypatch
):
    _patch_ollama_http(monkeypatch, raises=RuntimeError("connection refused"))
    res = unauthenticated_client.get("/health")
    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "degraded"
    assert "error" in body["checks"]["ollama"]
    # Ein Ollama-Ausfall darf die anderen, unabhängigen Prüfungen nicht anfärben.
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] == "ok"


def test_health_reports_degraded_when_ollama_returns_non_200(unauthenticated_client, monkeypatch):
    _patch_ollama_http(monkeypatch, response=_FakeOllamaResponse(500))
    res = unauthenticated_client.get("/health")
    assert res.status_code == 503
    assert res.json()["checks"]["ollama"] == "error: HTTP 500"


def test_health_reports_degraded_when_redis_unreachable(unauthenticated_client, monkeypatch):
    _patch_ollama_http(monkeypatch, response=_FakeOllamaResponse(200))

    def _raise(*a, **k):
        raise RuntimeError("redis down")

    monkeypatch.setattr(system_api.redis, "from_url", _raise)
    res = unauthenticated_client.get("/health")
    assert res.status_code == 503
    assert "error" in res.json()["checks"]["redis"]


def test_health_reports_degraded_when_database_unreachable(unauthenticated_client, monkeypatch):
    _patch_ollama_http(monkeypatch, response=_FakeOllamaResponse(200))

    def _raise(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(system_api.engine, "connect", _raise)
    res = unauthenticated_client.get("/health")
    assert res.status_code == 503
    assert "error" in res.json()["checks"]["database"]


def test_health_does_not_require_login(unauthenticated_client, monkeypatch):
    # Kein 401 -- /health muss auch ohne Session antworten (Monitoring-Sonde).
    _patch_ollama_http(monkeypatch, response=_FakeOllamaResponse(200))
    res = unauthenticated_client.get("/health")
    assert res.status_code != 401


# ── GET /version ───────────────────────────────────────────────────────────


def test_version_reports_build_env_vars(unauthenticated_client, monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc1234")
    monkeypatch.setenv("BUILD_TIME", "2026-09-14T00:00:00Z")
    res = unauthenticated_client.get("/version")
    assert res.status_code == 200
    assert res.json() == {"git_sha": "abc1234", "build_time": "2026-09-14T00:00:00Z"}


def test_version_defaults_to_unknown_without_build_env(unauthenticated_client, monkeypatch):
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("BUILD_TIME", raising=False)
    res = unauthenticated_client.get("/version")
    assert res.json() == {"git_sha": "unknown", "build_time": "unknown"}


# ── GET /model-info ────────────────────────────────────────────────────────


def test_get_model_info_is_public_and_reflects_current_config(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(cfg, "OLLAMA_LLM_MODEL", "mistral-nemo:test")
    monkeypatch.setattr(cfg, "OLLAMA_EMBED_MODEL", "bge-m3")
    res = unauthenticated_client.get("/model-info")
    assert res.status_code == 200
    assert res.json() == {"llm": "mistral-nemo:test", "embedding": "bge-m3"}


# ── POST /model-info (O-035: mutiert globalen Prozess-State) ───────────────


def test_update_model_info_requires_admin(member_client, monkeypatch):
    monkeypatch.setattr(cfg, "OLLAMA_LLM_MODEL", cfg.OLLAMA_LLM_MODEL)  # Auto-Restore
    res = member_client.post("/model-info", json={"llm": "mistral-nemo:o-113-test"})
    assert res.status_code == 403
    assert cfg.OLLAMA_LLM_MODEL != "mistral-nemo:o-113-test"


def test_update_model_info_requires_login(unauthenticated_client):
    res = unauthenticated_client.post("/model-info", json={"llm": "mistral-nemo:o-113-test"})
    assert res.status_code == 401


def test_update_model_info_mutates_global_config_for_every_subsequent_request(client, monkeypatch):
    """Pinnt das aktuell (laut Moduldocstring bewusst) gewollte O-035-Verhalten
    fest: `POST /model-info` ändert `cfg.OLLAMA_LLM_MODEL` als Modul-Attribut;
    `GET /model-info` liest es direkt und ohne jeden Bezug zu Nutzer/Session --
    ein späterer, unabhängiger Aufruf sieht denselben neuen Wert. Wird O-035
    umgesetzt (request-/profilgebundene Modellwahl statt globaler Mutation),
    MUSS genau dieser Test kippen -- das ist beabsichtigt und der Beleg für
    die Verhaltensänderung, nicht ein Bug in diesem Test."""
    monkeypatch.setattr(cfg, "OLLAMA_LLM_MODEL", cfg.OLLAMA_LLM_MODEL)  # Auto-Restore
    res = client.post("/model-info", json={"llm": "mistral-nemo:o-113-test"})
    assert res.status_code == 200
    assert res.json() == {"llm": "mistral-nemo:o-113-test", "embedding": cfg.OLLAMA_EMBED_MODEL}
    assert cfg.OLLAMA_LLM_MODEL == "mistral-nemo:o-113-test"

    res = client.get("/model-info")
    assert res.json()["llm"] == "mistral-nemo:o-113-test"


def test_update_model_info_leaves_embedding_model_untouched(client, monkeypatch):
    monkeypatch.setattr(cfg, "OLLAMA_LLM_MODEL", cfg.OLLAMA_LLM_MODEL)  # Auto-Restore
    original_embed = cfg.OLLAMA_EMBED_MODEL
    res = client.post("/model-info", json={"llm": "mistral-nemo:o-113-test-2"})
    assert res.status_code == 200
    assert res.json()["embedding"] == original_embed
    assert cfg.OLLAMA_EMBED_MODEL == original_embed


# ── GET /models ──────────────────────────────────────────────────────────────


def test_get_models_lists_installed_ollama_models(unauthenticated_client, monkeypatch):
    _patch_ollama_http(
        monkeypatch,
        response=_FakeOllamaResponse(
            200, {"models": [{"name": "bge-m3"}, {"name": "mistral-nemo"}]}
        ),
    )
    res = unauthenticated_client.get("/models")
    assert res.status_code == 200
    assert res.json() == {"models": ["bge-m3", "mistral-nemo"]}


def test_get_models_falls_back_to_configured_models_when_ollama_unreachable(
    unauthenticated_client, monkeypatch
):
    monkeypatch.setattr(cfg, "OLLAMA_LLM_MODEL", "mistral-nemo:configured")
    monkeypatch.setattr(cfg, "OLLAMA_EMBED_MODEL", "bge-m3")
    _patch_ollama_http(monkeypatch, raises=RuntimeError("connection refused"))
    res = unauthenticated_client.get("/models")
    assert res.status_code == 200
    assert res.json() == {"models": ["mistral-nemo:configured", "bge-m3"]}


def test_get_models_falls_back_when_ollama_returns_non_200(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(cfg, "OLLAMA_LLM_MODEL", "mistral-nemo:configured")
    monkeypatch.setattr(cfg, "OLLAMA_EMBED_MODEL", "bge-m3")
    _patch_ollama_http(monkeypatch, response=_FakeOllamaResponse(500))
    res = unauthenticated_client.get("/models")
    assert res.json() == {"models": ["mistral-nemo:configured", "bge-m3"]}
