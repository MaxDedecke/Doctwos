"""Doctus-Deployer: startet und verwaltet lokale LLM-Container (Ollama, vLLM, llama.cpp).

Der Dienst ist die einzige Komponente mit Zugriff auf den Docker-Socket. Das Backend
spricht ihn über das interne Compose-Netzwerk mit einem gemeinsamen Token an. Er
startet ausschließlich Container aus den Engine-Definitionen in ``engines.py``
(feste Images und Argumente, kein Privileged-Modus, kein Host-Netzwerk, nur das
Modellvolume als Mount) und rührt keine fremden Container an: Verwaltet wird nur,
was das Label ``doctus.deployment`` trägt.
"""

from __future__ import annotations

import hmac
import logging
import os
import threading
from typing import Any

import docker
import httpx
from docker.errors import APIError, DockerException, NotFound
from docker.types import DeviceRequest
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from engines import CONTAINER_PREFIX, LABEL, DeploymentSpec, SpecError, plan

logger = logging.getLogger("deployer")
app = FastAPI(title="Doctus Deployer", docs_url=None, redoc_url=None, openapi_url=None)

TOKEN = os.getenv("DEPLOYER_TOKEN", "")
NETWORK = os.getenv("DEPLOYER_NETWORK", "doctus_default")
MODELS_VOLUME = os.getenv("DEPLOYER_MODELS_VOLUME", "doctus_llm_models")

_client: docker.DockerClient | None = None
# Fortschritt des Modell-Downloads je Deployment (nur Ollama; vLLM/llama.cpp laden beim Start selbst).
_pull_state: dict[str, dict[str, str]] = {}


def client() -> docker.DockerClient:
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


def require_token(authorization: str | None = Header(default=None)) -> None:
    if not TOKEN:
        raise HTTPException(status_code=503, detail="DEPLOYER_TOKEN ist nicht gesetzt")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), TOKEN.encode()):
        raise HTTPException(status_code=401, detail="Nicht autorisiert")


class DeploymentRequest(BaseModel):
    name: str
    engine: str
    model: str
    role: str = "chat"
    gpu: bool = False
    context_length: int = Field(default=8192)
    tool_parser: str | None = None


def container_name(name: str) -> str:
    return f"{CONTAINER_PREFIX}{name}"


def gpu_available() -> bool:
    try:
        return "nvidia" in (client().info().get("Runtimes") or {})
    except DockerException:
        return False


def _answers(container_name: str, engine: str) -> bool:
    """True, wenn der Server im Container auf seinen Health-/Discovery-Pfad antwortet."""
    port = {"ollama": 11434, "vllm": 8000, "llamacpp": 8080}.get(engine, 0)
    health = "/api/tags" if engine == "ollama" else "/health"
    try:
        return bool(port) and httpx.get(f"http://{container_name}:{port}{health}", timeout=1.5).status_code == 200
    except httpx.HTTPError:
        return False


def _describe(container, *, include_health: bool = True) -> dict[str, Any]:
    labels = container.labels or {}
    name = labels.get(LABEL, "")
    engine = labels.get("doctus.engine", "")
    state = container.status
    port = {"ollama": 11434, "vllm": 8000, "llamacpp": 8080}.get(engine, 0)
    ready = include_health and state == "running" and _answers(container.name, engine)
    pull = _pull_state.get(name, {})
    if state in {"created", "restarting"}:
        status = "starting"
    elif state != "running":
        status = "stopped" if state in {"exited", "paused", "dead"} else state
    elif pull.get("status") == "pulling":
        status = "pulling"
    elif pull.get("status") == "failed":
        status = "failed"
    else:
        status = "ready" if ready else "starting"
    base = f"http://{container.name}:{port}"
    return {
        "name": name, "container": container.name, "engine": engine,
        "role": labels.get("doctus.role", "chat"), "model": labels.get("doctus.model", ""),
        "gpu": labels.get("doctus.gpu") == "true", "status": status, "detail": pull.get("detail", ""),
        "base_url": base if engine == "ollama" else f"{base}/v1",
        "image": container.image.tags[0] if container.image and container.image.tags else "",
    }


def _find(name: str):
    try:
        container = client().containers.get(container_name(name))
    except NotFound:
        raise HTTPException(status_code=404, detail="Deployment nicht gefunden")
    if LABEL not in (container.labels or {}):
        raise HTTPException(status_code=404, detail="Deployment nicht gefunden")
    return container


def _pull_ollama(name: str, model: str) -> None:
    """Lädt das Modell in den Ollama-Container (blockierend, läuft im Hintergrundthread)."""
    _pull_state[name] = {"status": "pulling", "detail": model}
    try:
        container = _find(name)
        for _ in range(60):
            container.reload()
            if container.status == "running" and _answers(container.name, "ollama"):
                result = container.exec_run(["ollama", "pull", model])
                if result.exit_code == 0:
                    _pull_state.pop(name, None)
                else:
                    _pull_state[name] = {"status": "failed", "detail": result.output.decode(errors="replace")[-500:]}
                return
            threading.Event().wait(2)
        _pull_state[name] = {"status": "failed", "detail": "Container wurde nicht bereit"}
    except Exception as exc:  # noqa: BLE001 - Fehler landet im Status, nicht im Thread
        logger.exception("ollama pull failed")
        _pull_state[name] = {"status": "failed", "detail": str(exc)[:500]}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/capabilities", dependencies=[Depends(require_token)])
def capabilities() -> dict[str, Any]:
    return {"gpu": gpu_available(), "engines": ["ollama", "vllm", "llamacpp"]}


@app.get("/deployments", dependencies=[Depends(require_token)])
def list_deployments() -> list[dict[str, Any]]:
    containers = client().containers.list(all=True, filters={"label": LABEL})
    return [_describe(container) for container in containers]


@app.get("/deployments/{name}", dependencies=[Depends(require_token)])
def get_deployment(name: str) -> dict[str, Any]:
    return _describe(_find(name))


@app.post("/deployments", status_code=201, dependencies=[Depends(require_token)])
def create_deployment(request: DeploymentRequest) -> dict[str, Any]:
    spec = DeploymentSpec(**request.model_dump())
    try:
        container_plan = plan(spec)
    except SpecError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if spec.gpu and not gpu_available():
        raise HTTPException(status_code=400, detail="Auf diesem Host ist keine NVIDIA-GPU-Laufzeit verfügbar")
    labels = {**container_plan.labels, "doctus.model": spec.model, "doctus.gpu": str(spec.gpu).lower()}
    environment = dict(container_plan.environment)
    hf_token = os.getenv("HF_TOKEN")
    if hf_token and spec.engine in {"vllm", "llamacpp"}:
        environment["HF_TOKEN"] = hf_token
    try:
        client().containers.get(container_name(spec.name))
        raise HTTPException(status_code=409, detail="Ein Deployment mit diesem Namen existiert bereits")
    except NotFound:
        pass
    try:
        container = client().containers.run(
            container_plan.image,
            command=container_plan.command,
            name=container_name(spec.name),
            detach=True,
            environment=environment,
            labels=labels,
            network=NETWORK,
            volumes={MODELS_VOLUME: {"bind": container_plan.mount_target, "mode": "rw"}},
            device_requests=[DeviceRequest(count=-1, capabilities=[["gpu"]])] if spec.gpu else None,
            restart_policy={"Name": "unless-stopped"},
            ipc_mode="host" if spec.engine == "vllm" else None,
            log_config={"type": "json-file", "config": {"max-size": "10m", "max-file": "3"}},
        )
    except APIError as exc:
        raise HTTPException(status_code=502, detail=f"Docker: {exc.explanation or exc}")
    if spec.engine == "ollama":
        threading.Thread(target=_pull_ollama, args=(spec.name, spec.model), daemon=True).start()
    return _describe(container, include_health=False)


@app.post("/deployments/{name}/start", dependencies=[Depends(require_token)])
def start_deployment(name: str) -> dict[str, Any]:
    container = _find(name)
    _pull_state.pop(name, None)
    container.start()
    container.reload()
    return _describe(container, include_health=False)


@app.post("/deployments/{name}/stop", dependencies=[Depends(require_token)])
def stop_deployment(name: str) -> dict[str, Any]:
    container = _find(name)
    container.stop(timeout=30)
    container.reload()
    return _describe(container, include_health=False)


@app.delete("/deployments/{name}", status_code=204, dependencies=[Depends(require_token)])
def delete_deployment(name: str) -> None:
    container = _find(name)
    container.remove(force=True)
    _pull_state.pop(name, None)


@app.get("/deployments/{name}/logs", dependencies=[Depends(require_token)])
def deployment_logs(name: str, tail: int = Query(default=200, ge=1, le=2000)) -> dict[str, str]:
    container = _find(name)
    return {"logs": container.logs(tail=tail).decode(errors="replace")}
