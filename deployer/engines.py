"""Engine-Definitionen des Deployers: feste Images, feste Argumentlisten, keine freien Eingaben.

Jede Engine (Ollama, vLLM, llama.cpp) wird aus einer kleinen, geprüften Spezifikation
in eine Container-Konfiguration übersetzt. Es gibt bewusst keinen Pfad, über den ein
Aufrufer beliebige Kommandozeilen, Images, Mounts oder Netzwerke vorgeben kann.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

ENGINES = ("ollama", "vllm", "llamacpp")
ROLES = ("chat", "embedding")
TOOL_PARSERS = ("hermes", "llama3_json", "mistral", "qwen3_coder", "pythonic")

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
# Modellkennungen: Ollama (name:tag), Hugging Face (org/repo[:quant]), GGUF-Dateien unter /models.
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}$")

CONTAINER_PREFIX = "doctus-llm-"
LABEL = "doctus.deployment"

# Images lassen sich je Kunde per Umgebungsvariable festschreiben (Digest/Tag), sonst gelten diese Standardwerte.
DEFAULT_IMAGES = {
    "ollama": "ollama/ollama:latest",
    "vllm": "vllm/vllm-openai:latest",
    "llamacpp": "ghcr.io/ggml-org/llama.cpp:server",
    "llamacpp-cuda": "ghcr.io/ggml-org/llama.cpp:server-cuda",
}
PORTS = {"ollama": 11434, "vllm": 8000, "llamacpp": 8080}


class SpecError(ValueError):
    """Ungültige Deployment-Angabe (führt zu HTTP 400)."""


@dataclass
class DeploymentSpec:
    name: str
    engine: str
    model: str
    role: str = "chat"
    gpu: bool = False
    context_length: int = 8192
    tool_parser: str | None = None
    hf_token_set: bool = False


@dataclass
class ContainerPlan:
    image: str
    command: list[str] | None
    environment: dict[str, str]
    mount_target: str
    port: int
    health_path: str
    labels: dict[str, str] = field(default_factory=dict)


def image_for(engine: str, gpu: bool) -> str:
    if engine == "llamacpp" and gpu:
        return os.getenv("LLAMACPP_CUDA_IMAGE", DEFAULT_IMAGES["llamacpp-cuda"])
    env = {"ollama": "OLLAMA_IMAGE", "vllm": "VLLM_IMAGE", "llamacpp": "LLAMACPP_IMAGE"}[engine]
    return os.getenv(env, DEFAULT_IMAGES[engine])


def validate(spec: DeploymentSpec) -> None:
    if not NAME_RE.match(spec.name):
        raise SpecError("Name: 2–31 Zeichen, nur a-z, 0-9 und Bindestrich, beginnt mit Buchstabe oder Ziffer")
    if spec.engine not in ENGINES:
        raise SpecError("Unbekannte Engine")
    if spec.role not in ROLES:
        raise SpecError("Rolle muss chat oder embedding sein")
    if not MODEL_RE.match(spec.model) or ".." in spec.model:
        raise SpecError("Ungültige Modellkennung")
    if not 512 <= spec.context_length <= 1_048_576:
        raise SpecError("Kontextlänge muss zwischen 512 und 1048576 liegen")
    if spec.tool_parser is not None and spec.tool_parser not in TOOL_PARSERS:
        raise SpecError("Unbekannter Tool-Parser")
    if spec.engine == "vllm" and not spec.gpu:
        raise SpecError("vLLM benötigt eine GPU")


def plan(spec: DeploymentSpec) -> ContainerPlan:
    """Baut die Container-Konfiguration; reine Funktion, damit sie ohne Docker testbar bleibt."""
    validate(spec)
    port = PORTS[spec.engine]
    image = image_for(spec.engine, spec.gpu)
    labels = {LABEL: spec.name, "doctus.engine": spec.engine, "doctus.role": spec.role}

    if spec.engine == "ollama":
        return ContainerPlan(
            image=image, command=None,
            environment={
                "OLLAMA_HOST": f"0.0.0.0:{port}",
                "OLLAMA_CONTEXT_LENGTH": str(spec.context_length),
                "OLLAMA_KEEP_ALIVE": "-1",
                "OLLAMA_FLASH_ATTENTION": "1",
            },
            mount_target="/root/.ollama", port=port, health_path="/api/tags", labels=labels,
        )

    if spec.engine == "llamacpp":
        # llama-server: lokale GGUF-Datei unter /models oder Hugging-Face-Repo (-hf, Cache in /models).
        local_file = spec.model.startswith("/models/") or spec.model.endswith(".gguf")
        source = ["-m", spec.model if spec.model.startswith("/") else f"/models/{spec.model}"] if local_file else ["-hf", spec.model]
        command = [*source, "--host", "0.0.0.0", "--port", str(port), "-c", str(spec.context_length),
                   "--alias", spec.model]
        if spec.gpu:
            command += ["-ngl", "999"]
        if spec.role == "embedding":
            command += ["--embedding", "--pooling", "mean"]
        else:
            command += ["--jinja"]
        return ContainerPlan(
            image=image, command=command, environment={"LLAMA_CACHE": "/models"},
            mount_target="/models", port=port, health_path="/health", labels=labels,
        )

    # vLLM: OpenAI-kompatibler Server; Hugging-Face-Cache liegt im Modellvolume.
    command = [spec.model, "--host", "0.0.0.0", "--port", str(port),
               "--max-model-len", str(spec.context_length), "--served-model-name", spec.model]
    if spec.role == "embedding":
        command += ["--task", "embed"]
    else:
        command += ["--enable-auto-tool-choice", "--tool-call-parser", spec.tool_parser or "hermes"]
    environment = {"HF_HOME": "/models/huggingface"}
    return ContainerPlan(
        image=image, command=command, environment=environment,
        mount_target="/models", port=port, health_path="/health", labels=labels,
    )
