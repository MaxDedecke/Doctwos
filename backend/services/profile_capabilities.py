"""
backend/services/profile_capabilities.py
========================================
Geprüfte Fähigkeiten eines KI-Profils: der gemeinsame Funktionsvertrag zwischen Profil und Chat.

Das Protokoll allein belegt nicht, dass das konkrete Modell Werkzeuge zuverlässig bedient. Die Prüfung
läuft deshalb über dieselben Provider-Adapter wie die Agentenschleife und hält fest:

    tools            Das Modell ruft das angebotene Werkzeug strukturiert auf.
    tool_arguments   Die Argumente sind ein gültiges JSON-Objekt mit dem verlangten Wert.
    tool_roundtrip   Das Modell verwendet das Werkzeugergebnis in seiner Antwort.
    streaming        Die Antwort kommt in Stücken (Live-Anzeige möglich).
    reasoning        Der Server liefert Denken getrennt von der Antwort.
    reasoning_summary  Nur Responses API: Zusammenfassungen des Denkens werden angenommen.

Ein Ergebnis gilt nur für Modell, Protokoll und Adresse, mit denen es entstand; nach einer Änderung am
Profil ist es veraltet und das Profil gilt wieder als ungeprüft. Ungeprüfte Profile verhalten sich wie
bisher (Werkzeuge laut Protokoll). Nur ein ausdrücklich negatives Ergebnis schaltet den Agenten ab; der
Chat antwortet dann aus dem abgerufenen Kontext (Standard-RAG).
"""

import json
import logging
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Optional

import httpx

import core.config as cfg

logger = logging.getLogger(__name__)

# Protokolle, für die es eine Werkzeugschleife gibt (services/agent_providers*.py). ``ollama`` ist auch das
# Protokoll entfernter Ollama-Profile (O-259): Fähigkeit hängt am Protokoll, nicht an ``remote``.
AGENT_TOOL_PROTOCOLS = frozenset(
    {"ollama", "openai_chat", "openai_responses", "anthropic", "gemini"}
)
_PROBE_TOOL = {
    "name": "codena_probe",
    "description": "Prüfwerkzeug von Codena. Liefert ein Kennwort zu einem Wort.",
    "inputSchema": {
        "type": "object",
        "properties": {"word": {"type": "string", "description": "Das zu prüfende Wort."}},
        "required": ["word"],
    },
}
_PROBE_WORD = "Codena"
_PROBE_SECRET = "KIWI-4711"
_PROBE_SYSTEM = (
    "Du bist ein Prüfprogramm. Folge den Anweisungen genau und antworte so kurz wie möglich."
)


def agent_provider(profile) -> str:
    """Anbieterschlüssel, unter dem die Agentenschleife den Adapter wählt."""
    if profile.protocol == "openai_responses":
        return "openai_responses"
    return (profile.provider or "").lower()


def agent_endpoint_path(profile) -> Optional[str]:
    return (
        profile.llm_path
        if profile.protocol in {"openai_chat", "openai_responses", "ollama"}
        else None
    )


def stored_capabilities(profile) -> Optional[dict[str, Any]]:
    """Letztes Prüfergebnis, solange es zu Modell, Protokoll und Adresse des Profils passt."""
    capabilities = getattr(profile, "capabilities_json", None)
    if not isinstance(capabilities, dict):
        return None
    current = (profile.llm_model, profile.protocol, profile.llm_base_url)
    checked = (
        capabilities.get("model"),
        capabilities.get("protocol"),
        capabilities.get("base_url"),
    )
    return capabilities if checked == current else None


def supports_tools(profile) -> bool:
    """Werkzeugschleife für dieses Profil: Protokoll mit Adapter und kein negatives Prüfergebnis."""
    if (getattr(profile, "protocol", "") or "").lower() not in AGENT_TOOL_PROTOCOLS:
        return False
    capabilities = stored_capabilities(profile)
    return capabilities is None or capabilities.get("tools") is not False


def requests_reasoning_summary(profile) -> bool:
    capabilities = stored_capabilities(profile)
    return bool(capabilities and capabilities.get("reasoning_summary"))


async def _run_turn(adapter, client, turn_index: int, tool_choice) -> tuple[Any, int, int]:
    """Ein Modellzug; liefert den Zug und die Zahl der Text- und Denkstücke."""
    from services.agent_providers import ModelTurn, Reasoning

    turn, text_pieces, reasoning_pieces = None, 0, 0
    async for item in adapter.complete(client, turn_index, tool_choice):
        if isinstance(item, ModelTurn):
            turn = item
        elif isinstance(item, Reasoning):
            reasoning_pieces += 1
        elif item:
            text_pieces += 1
    return turn, text_pieces, reasoning_pieces


async def _probe(profile, reasoning_summary: bool) -> dict[str, Any]:
    from services.agent_providers import make_provider_adapter

    adapter = make_provider_adapter(
        agent_provider(profile),
        api_key=profile.llm_api_key,
        base_url=profile.llm_base_url,
        endpoint_path=agent_endpoint_path(profile),
        ollama_base_url=profile.llm_base_url or cfg.default_ollama_base_url(),
        model_name=profile.llm_model,
        system_prompt=_PROBE_SYSTEM,
        tools=[_PROBE_TOOL],
        history=[],
        prompt=f"Rufe das Werkzeug codena_probe mit word='{_PROBE_WORD}' auf.",
        temperature=0.0,
        context_length=profile.llm_context_length,
        reasoning_summary=reasoning_summary,
    )
    result: dict[str, Any] = {"tools": False, "tool_arguments": False, "tool_roundtrip": False}
    async with httpx.AsyncClient(timeout=180.0) as client:
        # Ollama kennt kein ``required``; der Adapter bietet die Werkzeuge dann einfach an.
        turn, text_pieces, reasoning_pieces = await _run_turn(adapter, client, 0, "required")
        call = next((c for c in turn.tool_calls if c.name == _PROBE_TOOL["name"]), None)
        streamed = text_pieces > 0
        if call is not None:
            result["tools"] = True
            arguments = call.arguments
            result["tool_arguments"] = (
                isinstance(arguments, dict)
                and str(arguments.get("word", "")).strip().lower() == _PROBE_WORD.lower()
            )
            adapter.add_tool_results([call], [json.dumps({"kennwort": _PROBE_SECRET})], turn)
            adapter.add_user_text("Nenne nur das Kennwort aus dem Werkzeugergebnis.")
            answer, text_pieces, more_reasoning = await _run_turn(adapter, client, 1, "none")
            reasoning_pieces += more_reasoning
            streamed = streamed or text_pieces > 0
            result["tool_roundtrip"] = _PROBE_SECRET.lower() in (answer.text or "").lower()
    result["streaming"] = bool(adapter.streams and streamed)
    result["reasoning"] = reasoning_pieces > 0
    if profile.protocol == "openai_responses":
        result["reasoning_summary"] = reasoning_summary
    return result


async def probe_capabilities(profile) -> dict[str, Any]:
    """Prüft das Profil mit einem kleinen Werkzeuglauf; Fehler beim Aufruf lassen die Fähigkeiten offen."""
    started = monotonic()
    result: dict[str, Any] = {
        "model": profile.llm_model,
        "protocol": profile.protocol,
        "base_url": profile.llm_base_url,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }
    try:
        try:
            result.update(await _probe(profile, profile.protocol == "openai_responses"))
        except httpx.HTTPStatusError:
            if profile.protocol != "openai_responses":
                raise
            # Modelle ohne Denkzusammenfassung lehnen ``reasoning.summary`` ab; dann ohne prüfen.
            result.update(await _probe(profile, False))
    except Exception as exc:
        logger.warning("Fähigkeitsprüfung für Profil %s fehlgeschlagen: %s", profile.id, exc)
        result.update(
            tools=None, tool_arguments=None, tool_roundtrip=None, streaming=None, reasoning=None
        )
        result["error"] = (str(exc) or type(exc).__name__)[:300]
    result["duration_ms"] = round((monotonic() - started) * 1000)
    return result
