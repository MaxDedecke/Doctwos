import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engines  # noqa: E402
from engines import DeploymentSpec, SpecError, plan  # noqa: E402


def spec(**overrides):
    values = dict(name="chat-a", engine="llamacpp", model="unsloth/Qwen3-8B-GGUF:Q4_K_M", role="chat", gpu=False, context_length=8192)
    values.update(overrides)
    return DeploymentSpec(**values)


def test_llamacpp_chat_uses_jinja_and_hf_download():
    result = plan(spec())
    assert result.command[:2] == ["-hf", "unsloth/Qwen3-8B-GGUF:Q4_K_M"]
    assert "--jinja" in result.command and "--embedding" not in result.command
    assert result.port == 8080 and result.health_path == "/health"


def test_llamacpp_gguf_file_is_read_from_models_volume():
    result = plan(spec(model="qwen/model.gguf", gpu=True))
    assert result.command[:2] == ["-m", "/models/qwen/model.gguf"]
    assert result.command[result.command.index("-ngl") + 1] == "999"
    assert result.image.endswith("server-cuda")


def test_llamacpp_embedding_mode():
    command = plan(spec(role="embedding", model="bge-m3-q8.gguf")).command
    assert "--embedding" in command and "--pooling" in command and "--jinja" not in command


def test_vllm_chat_enables_tool_calling_with_parser():
    result = plan(spec(engine="vllm", gpu=True, model="Qwen/Qwen2.5-Coder-14B-Instruct", tool_parser="hermes"))
    assert result.command[0] == "Qwen/Qwen2.5-Coder-14B-Instruct"
    assert "--enable-auto-tool-choice" in result.command
    assert result.command[result.command.index("--tool-call-parser") + 1] == "hermes"
    assert result.port == 8000


def test_vllm_requires_gpu():
    with pytest.raises(SpecError):
        plan(spec(engine="vllm", gpu=False))


def test_ollama_has_no_command_and_pulls_later():
    result = plan(spec(engine="ollama", model="qwen3:8b"))
    assert result.command is None and result.port == 11434
    assert result.environment["OLLAMA_CONTEXT_LENGTH"] == "8192"


@pytest.mark.parametrize("bad", ["", "../etc/passwd", "a b", "x;rm -rf /", "-m", "a" * 300])
def test_bad_model_ids_are_rejected(bad):
    with pytest.raises(SpecError):
        plan(spec(model=bad))


@pytest.mark.parametrize("bad", ["", "A", "x", "-x", "x_y", "doctus llm", "a" * 40])
def test_bad_names_are_rejected(bad):
    with pytest.raises(SpecError):
        plan(spec(name=bad))


def test_unknown_engine_role_and_parser_are_rejected():
    for override in ({"engine": "tgi"}, {"role": "rerank"}, {"tool_parser": "evil --flag"}, {"context_length": 10}):
        with pytest.raises(SpecError):
            plan(spec(**override))


def test_image_can_be_pinned_per_customer(monkeypatch):
    monkeypatch.setenv("VLLM_IMAGE", "registry.local/vllm@sha256:abc")
    assert plan(spec(engine="vllm", gpu=True, model="org/m")).image == "registry.local/vllm@sha256:abc"


# --- API ---------------------------------------------------------------------------------

@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("DEPLOYER_TOKEN", "secret")
    import importlib
    import app as app_module
    importlib.reload(app_module)
    from fastapi.testclient import TestClient
    fake = MagicMock()
    fake.info.return_value = {"Runtimes": {"nvidia": {}, "runc": {}}}
    app_module._client = fake
    return TestClient(app_module.app), fake, app_module


HEAD = {"Authorization": "Bearer secret"}


def test_requests_without_valid_token_are_rejected(api):
    client, _, _ = api
    assert client.get("/deployments").status_code == 401
    assert client.get("/deployments", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/health").status_code == 200


def test_create_starts_labelled_container_on_internal_network(api):
    from docker.errors import NotFound
    client, fake, app_module = api
    fake.containers.get.side_effect = NotFound("x")
    fake.containers.run.return_value = SimpleNamespace(
        name="doctus-llm-chat-a", status="created", labels={engines.LABEL: "chat-a", "doctus.engine": "llamacpp", "doctus.model": "m"},
        image=SimpleNamespace(tags=["img"]),
    )
    response = client.post("/deployments", headers=HEAD, json={"name": "chat-a", "engine": "llamacpp", "model": "org/m"})
    assert response.status_code == 201
    kwargs = fake.containers.run.call_args.kwargs
    assert kwargs["name"] == "doctus-llm-chat-a" and kwargs["network"] == app_module.NETWORK
    assert list(kwargs["volumes"]) == [app_module.MODELS_VOLUME]
    assert "privileged" not in kwargs and "ports" not in kwargs and kwargs["labels"][engines.LABEL] == "chat-a"
    assert response.json()["base_url"] == "http://doctus-llm-chat-a:8080/v1"


def test_gpu_request_fails_without_nvidia_runtime(api):
    client, fake, _ = api
    fake.info.return_value = {"Runtimes": {"runc": {}}}
    response = client.post("/deployments", headers=HEAD, json={"name": "v1", "engine": "vllm", "model": "org/m", "gpu": True})
    assert response.status_code == 400


def test_invalid_spec_is_a_400(api):
    client, _, _ = api
    response = client.post("/deployments", headers=HEAD, json={"name": "x y", "engine": "ollama", "model": "m"})
    assert response.status_code == 400


def test_foreign_containers_are_not_managed(api):
    client, fake, _ = api
    fake.containers.get.return_value = SimpleNamespace(name="doctus-llm-db", labels={}, status="running")
    assert client.delete("/deployments/db", headers=HEAD).status_code == 404
