"""Client für den Deployer-Dienst (lokale LLM-Container), siehe deployer/ und E-16.

Das Backend hat keinen Docker-Zugriff; es bittet den Deployer über das interne Netzwerk
(Bearer-Token) um Start, Stopp, Status und Logs. Fehler werden als ``DeployerError`` mit
einer für Admins lesbaren Meldung und einem passenden HTTP-Status weitergegeben.
"""

from __future__ import annotations

from typing import Any

import httpx

import core.config as cfg


class DeployerError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _request(method: str, path: str, *, timeout: float = 30.0, **kwargs: Any) -> Any:
    if not cfg.DEPLOYER_TOKEN:
        raise DeployerError(
            "Lokale Deployments sind nicht eingerichtet: DEPLOYER_TOKEN fehlt in der .env.", 503
        )
    try:
        response = httpx.request(
            method, f"{cfg.DEPLOYER_URL}{path}", timeout=timeout,
            headers={"Authorization": f"Bearer {cfg.DEPLOYER_TOKEN}"}, **kwargs,
        )
    except httpx.HTTPError as exc:
        raise DeployerError(f"Deployer nicht erreichbar: {exc}", 503) from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise DeployerError(str(detail), response.status_code if response.status_code < 500 else 502)
    return response.json() if response.content else None


def capabilities() -> dict[str, Any]:
    return _request("GET", "/capabilities", timeout=10.0)


def list_deployments() -> list[dict[str, Any]]:
    return _request("GET", "/deployments", timeout=20.0)


def get_deployment(name: str) -> dict[str, Any]:
    return _request("GET", f"/deployments/{name}", timeout=10.0)


def create_deployment(spec: dict[str, Any]) -> dict[str, Any]:
    return _request("POST", "/deployments", json=spec, timeout=60.0)


def start_deployment(name: str) -> dict[str, Any]:
    return _request("POST", f"/deployments/{name}/start")


def stop_deployment(name: str) -> dict[str, Any]:
    return _request("POST", f"/deployments/{name}/stop", timeout=60.0)


def delete_deployment(name: str) -> None:
    _request("DELETE", f"/deployments/{name}", timeout=60.0)


def deployment_logs(name: str, tail: int = 200) -> str:
    return _request("GET", f"/deployments/{name}/logs", params={"tail": tail})["logs"]
