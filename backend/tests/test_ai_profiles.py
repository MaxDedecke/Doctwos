from models.database import AIProfile, AISettings
from services.ai_settings import apply_profile


class _ReachableResponse:
    def raise_for_status(self):
        return None


class _ProfileTestClient:
    def __init__(self, calls):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, url, headers):
        self.calls.append((url, headers))
        return _ReachableResponse()


def _payload(**overrides):
    data = {
        "name": "Remote GPU",
        "kind": "remote",
        "provider": "openai",
        "protocol": "openai_chat",
        "llm_model": "qwen3:32b",
        "llm_base_url": "https://gpu.internal:11434/v1",
        "llm_path": "/chat/completions",
        "llm_api_key": "chat-secret",
        "embedding_provider": "ollama",
        "embedding_model": "qwen3-embedding:4b",
        "embedding_base_url": "https://gpu.internal:11434",
        "embedding_path": "/api/embed",
        "embedding_api_key": "embedding-secret",
        "embedding_dimension": 1024,
        "embedding_context_length": 8192,
        "llm_context_length": 16384,
    }
    data.update(overrides)
    return data


def test_profiles_are_server_side_and_secrets_are_redacted(client, db_session):
    response = client.post("/ai-profiles", json=_payload())
    assert response.status_code == 201, response.text
    profile_id = response.json()["id"]
    assert response.json()["llm_api_key_set"] is True
    assert "chat-secret" not in response.text

    listed = client.get("/ai-profiles")
    profile = next(item for item in listed.json()["profiles"] if item["id"] == profile_id)
    assert profile["kind"] == "remote"
    assert profile["protocol"] == "openai_chat"
    assert profile["embedding_path"] == "/api/embed"
    assert "embedding-secret" not in listed.text

    db_session.query(AIProfile).filter(AIProfile.id == profile_id).delete()
    db_session.commit()


def test_remote_openai_compatible_profile_is_not_cloud_gated(client, db_session, monkeypatch):
    created = client.post("/ai-profiles", json=_payload()).json()
    monkeypatch.setattr("api.system.cfg.cloud_llm_allowed", lambda: False)
    response = client.post(f"/ai-profiles/{created['id']}/activate")
    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is True

    local = db_session.query(AIProfile).filter(AIProfile.kind == "local").first()
    settings = db_session.query(AISettings).order_by(AISettings.id).first()
    apply_profile(settings, local)
    db_session.commit()
    db_session.query(AIProfile).filter(AIProfile.id == created["id"]).delete()
    db_session.commit()


def test_cloud_profile_requires_deployment_opt_in(client, db_session, monkeypatch):
    created = client.post(
        "/ai-profiles",
        json=_payload(
            name="OpenAI",
            kind="cloud",
            provider="openai",
            protocol="openai_responses",
            llm_model="gpt-6-astra",
            llm_base_url="https://api.openai.com/v1",
            llm_path="/responses",
        ),
    ).json()
    monkeypatch.setattr("api.system.cfg.cloud_llm_allowed", lambda: False)
    response = client.post(f"/ai-profiles/{created['id']}/activate")
    assert response.status_code == 403
    db_session.query(AIProfile).filter(AIProfile.id == created["id"]).delete()
    db_session.commit()


def test_system_and_active_profiles_cannot_be_deleted(client, db_session):
    settings = db_session.query(AISettings).order_by(AISettings.id).first()
    profile = db_session.query(AIProfile).filter(AIProfile.id == settings.active_profile_id).first()
    response = client.delete(f"/ai-profiles/{profile.id}")
    assert response.status_code == 409


def test_profile_update_preserves_omitted_secret(client, db_session):
    created = client.post("/ai-profiles", json=_payload()).json()
    profile_id = created["id"]
    response = client.patch(f"/ai-profiles/{profile_id}", json={"name": "Renamed"})
    assert response.status_code == 200
    profile = db_session.query(AIProfile).filter(AIProfile.id == profile_id).first()
    assert profile.llm_api_key == "chat-secret"
    db_session.delete(profile)
    db_session.commit()


def test_profile_test_checks_chat_and_embedding_endpoints_separately(
    client, db_session, monkeypatch
):
    created = client.post("/ai-profiles", json=_payload()).json()
    calls = []
    monkeypatch.setattr("api.system.httpx.AsyncClient", lambda **_kwargs: _ProfileTestClient(calls))

    response = client.post(f"/ai-profiles/{created['id']}/test")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "ok": True,
        "chat": "reachable",
        "embedding": "reachable",
    }
    assert calls == [
        (
            "https://gpu.internal:11434/v1/models",
            {"Content-Type": "application/json", "Authorization": "Bearer chat-secret"},
        ),
        (
            "https://gpu.internal:11434/api/tags",
            {
                "Content-Type": "application/json",
                "Authorization": "Bearer embedding-secret",
            },
        ),
    ]
    db_session.query(AIProfile).filter(AIProfile.id == created["id"]).delete()
    db_session.commit()
