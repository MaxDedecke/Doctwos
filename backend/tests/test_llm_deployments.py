"""Lokale LLM-Deployments (Ollama, vLLM, llama.cpp) über den Deployer und Standard-Stack ohne LLM-Container."""

from unittest.mock import MagicMock

import pytest

import core.config as cfg
from models.database import AIProfile, EmbeddingProfile
from services import ai_settings
from services.deployer_client import DeployerError


class FakeDeployer:
    def __init__(self):
        self.created = []
        self.deleted = []

    def create_deployment(self, spec):
        self.created.append(spec)
        port = {"ollama": 11434, "vllm": 8000, "llamacpp": 8080}[spec["engine"]]
        suffix = "" if spec["engine"] == "ollama" else "/v1"
        return {"name": spec["name"], "engine": spec["engine"], "status": "starting",
                "base_url": f"http://doctus-llm-{spec['name']}:{port}{suffix}"}

    def delete_deployment(self, name):
        self.deleted.append(name)


@pytest.fixture
def deployer(monkeypatch):
    fake = FakeDeployer()
    monkeypatch.setattr("api.system.deployer_client.create_deployment", fake.create_deployment)
    monkeypatch.setattr("api.system.deployer_client.delete_deployment", fake.delete_deployment)
    return fake


def _body(**overrides):
    body = {"name": "t-llamacpp-chat", "display_name": "Test llama.cpp", "engine": "llamacpp",
            "model": "org/model-GGUF:Q4_K_M", "role": "chat", "gpu": False, "context_length": 8192}
    body.update(overrides)
    return body


def _cleanup(db_session, model, name):
    db_session.query(model).filter(model.deployment_name == name).delete()
    db_session.commit()


# --- Standard-Stack ohne LLM-Container ---------------------------------------------------

def test_no_bootstrap_profiles_without_endpoint(monkeypatch):
    monkeypatch.setattr(cfg, "BOOTSTRAP_LLM_ENDPOINT", False)
    monkeypatch.setattr(cfg, "BOOTSTRAP_EMBEDDING_ENDPOINT", False)
    db = MagicMock()
    db.query.return_value.order_by.return_value.all.return_value = []
    settings = MagicMock()
    assert ai_settings.ensure_profiles(db, settings) == []
    assert ai_settings.ensure_embedding_profiles(db, settings) == []
    db.add.assert_not_called()


def test_bootstrap_profile_is_seeded_for_legacy_or_explicit_endpoint(monkeypatch):
    monkeypatch.setattr(cfg, "BOOTSTRAP_LLM_ENDPOINT", True)
    db = MagicMock()
    db.query.return_value.order_by.return_value.all.return_value = []
    profiles = ai_settings.ensure_profiles(db, MagicMock())
    assert len(profiles) == 1 and profiles[0].kind == "local"


def test_missing_profiles_raise_a_clear_message(monkeypatch):
    monkeypatch.setattr(ai_settings, "get_settings", lambda db: MagicMock(active_profile_id=None, active_embedding_profile_id=None))
    monkeypatch.setattr(ai_settings, "ensure_profiles", lambda db, settings: [])
    monkeypatch.setattr(ai_settings, "ensure_embedding_profiles", lambda db, settings: [])
    with pytest.raises(LookupError, match="Kein LLM-Profil"):
        ai_settings.get_active_profile(MagicMock())
    with pytest.raises(LookupError, match="Kein Embedding-Profil"):
        ai_settings.get_active_embedding_profile(MagicMock())


# --- Profile für lokale Deployments --------------------------------------------------------

@pytest.mark.parametrize("engine,protocol,path,suffix", [
    ("llamacpp", "openai_chat", "/chat/completions", ":8080/v1"),
    ("vllm", "openai_chat", "/chat/completions", ":8000/v1"),
    ("ollama", "ollama", "/api/chat", ":11434"),
])
def test_chat_deployment_creates_local_profile(client, db_session, deployer, engine, protocol, path, suffix):
    name = f"t-{engine}-chat"
    response = client.post("/llm-deployments", json=_body(name=name, engine=engine, gpu=engine == "vllm"))
    assert response.status_code == 201, response.text
    try:
        profile = response.json()["profile"]
        assert profile["kind"] == "local" and profile["provider"] == engine and profile["protocol"] == protocol
        assert profile["llm_path"] == path and profile["llm_base_url"] == f"http://doctus-llm-{name}{suffix}"
        assert profile["deployment_name"] == name and profile["name"] == "Test llama.cpp"
        assert deployer.created[0]["engine"] == engine
    finally:
        _cleanup(db_session, AIProfile, name)


def test_embedding_deployment_creates_embedding_profile(client, db_session, deployer):
    name = "t-llamacpp-embed"
    response = client.post("/llm-deployments", json=_body(name=name, role="embedding", model="bge-m3-q8_0.gguf", dimension=1024))
    assert response.status_code == 201, response.text
    try:
        profile = response.json()["profile"]
        assert profile["provider"] == "openai" and profile["path"] == "/embeddings"
        assert profile["base_url"] == f"http://doctus-llm-{name}:8080/v1" and profile["deployment_name"] == name
    finally:
        _cleanup(db_session, EmbeddingProfile, name)


def test_ollama_embedding_deployment_uses_native_api(client, db_session, deployer):
    name = "t-ollama-embed"
    response = client.post("/llm-deployments", json=_body(name=name, engine="ollama", role="embedding", model="bge-m3"))
    assert response.status_code == 201, response.text
    try:
        assert response.json()["profile"]["provider"] == "ollama"
        assert response.json()["profile"]["path"] == "/api/embed"
    finally:
        _cleanup(db_session, EmbeddingProfile, name)


def test_container_is_removed_when_the_profile_cannot_be_created(client, deployer):
    response = client.post("/llm-deployments", json=_body(name="t-broken", model=""))
    assert response.status_code == 400
    assert deployer.deleted == ["t-broken"]


def test_generic_endpoint_cannot_create_local_profiles_for_arbitrary_urls(client):
    response = client.post("/ai-profiles", json={
        "name": "Sneaky", "kind": "local", "provider": "vllm", "protocol": "openai_chat", "llm_model": "m",
        "llm_base_url": "http://internal-admin:9000/v1", "llm_path": "/chat/completions",
        "embedding_provider": "ollama", "embedding_model": "bge-m3"})
    assert response.status_code == 400


def test_deleting_a_deployment_profile_removes_its_container(client, db_session, deployer):
    name = "t-delete-me"
    created = client.post("/llm-deployments", json=_body(name=name)).json()["profile"]
    # Das erste Profil wird automatisch aktiv und ist dann nicht löschbar; für den Test ein zweites aktivieren.
    other = client.post("/ai-profiles", json={
        "name": "Other", "kind": "remote", "provider": "openai", "protocol": "openai_chat", "llm_model": "m",
        "llm_base_url": "https://x.example/v1", "llm_path": "/chat/completions",
        "embedding_provider": "ollama", "embedding_model": "bge-m3", "embedding_base_url": "https://x.example"}).json()
    try:
        assert client.post(f"/ai-profiles/{other['id']}/activate").status_code == 200
        assert client.delete(f"/ai-profiles/{created['id']}").status_code == 204
        assert deployer.deleted == [name]
    finally:
        db_session.query(AIProfile).filter(AIProfile.id.in_([created["id"], other["id"]])).delete()
        db_session.commit()


def test_deployer_errors_are_reported_with_their_status(client, monkeypatch):
    def unavailable():
        raise DeployerError("Deployer nicht erreichbar: boom", 503)
    monkeypatch.setattr("api.system.deployer_client.capabilities", unavailable)
    response = client.get("/llm-deployments")
    assert response.status_code == 503 and "nicht erreichbar" in response.json()["detail"]


def test_missing_token_means_local_deployments_are_unavailable(client, monkeypatch):
    monkeypatch.setattr(cfg, "DEPLOYER_TOKEN", "")
    response = client.get("/llm-deployments")
    assert response.status_code == 503 and "DEPLOYER_TOKEN" in response.json()["detail"]


def test_unknown_control_action_is_rejected(client):
    assert client.post("/llm-deployments/x/destroy").status_code == 404
