"""Nahtstellen des zerlegten Agent-Kerns: erster Belegschritt und Werkzeugauswahl."""

import asyncio

from services.agent_bootstrap import plan_bootstrap
from services.agent_tool_executor import AgentToolExecutor


def test_a_pinned_file_opens_a_window_around_its_line_and_no_repository_lists_entities():
    name, args, focus = plan_bootstrap(
        "Question: Was passiert hier?",
        repo_id=3,
        repo_available=True,
        pinned_file="app/cbl/COSGN00C.cbl",
        pinned_line=100,
        pinned_end_line=None,
    )
    assert (name, args, focus) == (
        "view_repo_file",
        {"file_path": "app/cbl/COSGN00C.cbl", "start_line": 85, "end_line": 130},
        set(),
    )

    assert plan_bootstrap(
        "Question: Wer ruft COSGN00C?",
        repo_id=None,
        repo_available=False,
        pinned_file=None,
        pinned_line=None,
        pinned_end_line=None,
    ) == ("get_repo_entities", {"limit": 20}, set())


class _Client:
    name = "fake-mcp"

    async def call_tool(self, name, args):
        return {"content": [{"type": "text", "text": f"mcp:{name}"}]}


def _executor(project_id):
    return AgentToolExecutor(
        repo_id=None,
        repo_available=False,
        project_id=project_id,
        db_session=None,
        audit_user_id=None,
        audit_chat_session_id=None,
        audit_chat_message_id=None,
        walkthrough_documents=[],
        mcp_tool_map={"search_knowledge": _Client()},
        prompt="Question: `Auth.login` erklären",
    )


def test_a_local_tool_that_is_not_available_falls_through_to_an_mcp_tool_of_the_same_name():
    executor = _executor(project_id=None)
    assert asyncio.run(executor.execute("search_knowledge", {}, "call-1")) == "mcp:search_knowledge"
    assert executor.execution_metadata("call-1")["mcp_server"] == "fake-mcp"
    assert asyncio.run(executor.execute("unknown_tool", {})) == (
        "Fehler: Werkzeug 'unknown_tool' ist nicht registriert."
    )
    assert executor.trace_target_names == {"login"}
