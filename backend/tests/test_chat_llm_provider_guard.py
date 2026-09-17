import json

from core.config import cloud_llm_allowed as _cloud_llm_allowed
from models.database import AIProfile


def _cloud_profile(db_session):
    profile = AIProfile(
        name="Guard OpenAI",
        kind="cloud",
        provider="openai",
        protocol="openai_responses",
        llm_model="gpt-6-astra",
        llm_base_url="https://api.openai.com/v1",
        llm_path="/responses",
        embedding_provider="ollama",
        embedding_model="bge-m3",
        embedding_base_url="http://ollama:11434",
        embedding_path="/api/embed",
        embedding_dimension=1024,
        embedding_context_length=8192,
        llm_context_length=8192,
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


def test_cloud_llm_allowed_reads_deployment_config(tmp_path, monkeypatch):
    monkeypatch.delenv("ALLOW_CLOUD_LLM", raising=False)
    config_file = tmp_path / "features.json"
    config_file.write_text(json.dumps({"llm": {"allowCloudProviders": True}}))
    monkeypatch.setenv("FEATURES_CONFIG_PATH", str(config_file))
    assert _cloud_llm_allowed() is True


def test_cloud_llm_allowed_defaults_false_when_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("ALLOW_CLOUD_LLM", raising=False)
    config_file = tmp_path / "features.json"
    config_file.write_text(json.dumps({"connectors": {"local": True}}))
    monkeypatch.setenv("FEATURES_CONFIG_PATH", str(config_file))
    assert _cloud_llm_allowed() is False


def test_cloud_llm_allowed_defaults_false_when_config_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("ALLOW_CLOUD_LLM", raising=False)
    monkeypatch.setenv("FEATURES_CONFIG_PATH", str(tmp_path / "does-not-exist.json"))
    assert _cloud_llm_allowed() is False


def test_chat_endpoint_rejects_cloud_provider_when_disabled_by_default(
    client, db_session, monkeypatch
):
    # Explicit False, not just the config default — this deployment's mounted
    # config/features.json may set allowCloudProviders: true for demo purposes,
    # which would otherwise make this test flaky depending on where it runs.
    monkeypatch.setattr("api.chat.cfg.cloud_llm_allowed", lambda: False)
    profile = _cloud_profile(db_session)
    try:
        res = client.post("/chat", json={"message": "Hallo", "llm_profile_id": profile.id})
        assert res.status_code == 403
        assert "allowCloudProviders" in res.json()["detail"]
    finally:
        db_session.delete(profile)
        db_session.commit()


def test_cloud_llm_allowed_respects_env_override_true(monkeypatch):
    monkeypatch.setenv("ALLOW_CLOUD_LLM", "true")
    assert _cloud_llm_allowed() is True


def test_cloud_llm_allowed_respects_env_override_false(tmp_path, monkeypatch):
    config_file = tmp_path / "features.json"
    config_file.write_text(json.dumps({"llm": {"allowCloudProviders": True}}))
    monkeypatch.setenv("FEATURES_CONFIG_PATH", str(config_file))
    monkeypatch.setenv("ALLOW_CLOUD_LLM", "false")
    assert _cloud_llm_allowed() is False


def test_features_endpoint_respects_env_override_true(client, tmp_path, monkeypatch):
    monkeypatch.delenv("ALLOW_CLOUD_LLM", raising=False)
    config_file = tmp_path / "features.json"
    config_file.write_text(json.dumps({"llm": {"allowCloudProviders": False}}))
    monkeypatch.setenv("FEATURES_CONFIG_PATH", str(config_file))

    # Without override, should be False
    res = client.get("/config/features")
    assert res.json().get("llm", {}).get("allowCloudProviders") is False

    # With override, should be True
    monkeypatch.setenv("ALLOW_CLOUD_LLM", "true")
    res2 = client.get("/config/features")
    assert res2.json().get("llm", {}).get("allowCloudProviders") is True
