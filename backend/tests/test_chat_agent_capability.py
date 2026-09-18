"""Regression coverage for profile-based chat-agent capability selection."""

from types import SimpleNamespace

from api.chat import _agent_profile_supports_tools
from services.chat_service import classify_chat_intent


def test_remote_ollama_profile_is_agent_capable():
    """O-259: remote Ollama uses the same supported OpenAI-compatible tool loop."""
    profile = SimpleNamespace(kind="remote", protocol="ollama")

    assert _agent_profile_supports_tools(profile) is True


def test_unknown_profile_protocol_does_not_enter_agent_loop():
    profile = SimpleNamespace(kind="remote", protocol="future_protocol")

    assert _agent_profile_supports_tools(profile) is False


def test_smalltalk_skips_retrieval_and_agent_even_with_project_scope():
    intent = classify_chat_intent("Hallo!", project_id=731)

    assert intent.kind == "smalltalk"
    assert intent.use_retrieval is False
    assert intent.use_agent is False


def test_project_question_uses_grounded_agent_path():
    intent = classify_chat_intent("Was ist das für ein Projekt?", project_id=731)

    assert intent.kind == "project_question"
    assert intent.use_retrieval is True
    assert intent.use_agent is True


def test_graph_question_is_marked_for_project_agent():
    intent = classify_chat_intent("Zeige mir den Call Graph", project_id=731)

    assert intent.kind == "call_graph"
    assert intent.use_retrieval is True
    assert intent.use_agent is True
