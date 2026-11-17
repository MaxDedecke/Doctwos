import asyncio
import logging
import os
import json
import httpx
from typing import Dict, List, Any, Optional, AsyncGenerator
import core.config as cfg
from mcp_client import MCPClient
from doctus_models.database import User
from services.agent_providers import (
    ModelTurn,
    ProviderAdapter,
    ToolCall,
    make_provider_adapter,
)

from services import agent_repo_tools as repo_tools
from services.agent_bootstrap import plan_bootstrap
from services.agent_mcp_tools import collect_mcp_tools
from services.agent_prompt import build_system_prompt
from services.agent_tool_defs import local_tool_definitions, select_tools_for_question
from services.agent_tool_executor import AgentToolExecutor
from services.agent_tool_results import _tool_result_was_truncated
from services import agent_text_tool_calls as text_calls

logger = logging.getLogger(__name__)


def _question_of(prompt: str) -> str:
    """Die Frage des Nutzers ohne den vorangestellten Kontextblock."""
    question = (prompt.rsplit("Question:", 1)[-1] if "Question:" in prompt else prompt).strip()
    return question.removesuffix("Answer:").strip()


async def _prefetch_evidence(
    db_session,
    user_id: Optional[int],
    project_id: int,
    prompt: str,
    max_chars: Optional[int] = None,
    overview: bool = False,
) -> Optional[tuple[str, dict, str]]:
    """Run the answer_context evidence pack for the symbols named in the question.

    Returns (tool name, arguments, JSON result) when at least one named symbol resolves, otherwise None so the
    regular bootstrap applies. With ``overview`` the project overview counts as a result too: it replaces the
    generic bootstrap for questions that name neither a symbol nor a file. Failures never block the chat."""
    if user_id is None:
        return None
    question = _question_of(prompt)[:1400]
    try:
        from services.answer_context import build_answer_context

        user = db_session.query(User).filter(User.id == user_id).first()
        if user is None:
            return None
        result = await asyncio.to_thread(
            build_answer_context,
            db_session,
            user,
            project_id,
            question=question,
            max_chars=max_chars or cfg.CHAT_EVIDENCE_CHARS,
            overview=overview,
        )
    except Exception as exc:  # evidence is an accelerator; the model can still use its tools
        logger.warning("Chat evidence prefetch failed (%s)", type(exc).__name__)
        try:
            db_session.rollback()
        except Exception:
            pass
        return None
    if not (
        result.get("resolved")
        or result.get("concept_hits")
        or (overview and result.get("overview"))
    ):
        return None
    args = {"symbols": [item["symbol"] for item in result["resolved"]], "topic": question[:200]}
    return "answer_context", args, json.dumps(result, ensure_ascii=False)


MAX_AGENT_TURNS = 8
# Letzte Runde: keine Werkzeuge mehr, stattdessen Antwort aus den bisher abgerufenen Belegen. Ohne
# diese Runde endet ein Lauf, der das Recherchebudget aufbraucht, ohne jede Antwort (obwohl Quellen vorliegen).
_FINAL_TURN_INSTRUCTION = (
    "Das Recherchebudget ist ausgeschöpft. Rufe keine weiteren Werkzeuge auf. Beantworte die Frage jetzt "
    "ausschließlich mit den bisher abgerufenen Belegen, nenne Fundstellen mit Zeilen und benenne ausdrücklich, "
    "was die Recherche nicht klären konnte."
)
_INVALID_ARGUMENTS_RESULT = (
    "Fehler: Die Argumente für '{name}' waren kein gültiges JSON-Objekt; das Werkzeug wurde nicht "
    "ausgeführt. Rufe es erneut mit einem gültigen JSON-Objekt auf."
)
_NO_RESEARCH_ANSWER = (
    "Ich konnte die projektbezogene Frage nicht verlässlich über "
    "das Repository-Tool prüfen. Bitte wiederhole die Frage kurz."
)


def _tool_events(call: ToolCall, result: str, metadata: dict) -> tuple[dict, dict]:
    return (
        {"type": "tool_call", "name": call.name, "arguments": call.arguments, "id": call.id},
        {
            "type": "tool_result",
            "name": call.name,
            "result": result,
            "id": call.id,
            "truncated": _tool_result_was_truncated(result),
            **metadata,
        },
    )


async def _research_loop(
    adapter: ProviderAdapter,
    execute_tool,
    execution_metadata,
    agent_steps: list,
    *,
    must_research: bool,
    researched: bool,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Anbieterunabhängige Werkzeugschleife.

    - Recherchebudget: höchstens MAX_AGENT_TURNS Modellaufrufe; der letzte ohne
      Werkzeuge mit der Aufforderung, aus den Belegen zu antworten.
    - Erzwungene Recherche (``must_research``): Bis ein Werkzeug gelaufen ist,
      wird ``tool_choice=required`` verlangt und Antworttext zurückgehalten.
      Manche Server behandeln ``required`` stillschweigend wie ``auto``; eine
      solche Antwort wird verworfen und einmal wiederholt, danach gibt es eine
      feste Meldung statt ungeprüften Texts.
    - Ein Zug ohne Text und ohne Werkzeugaufruf wird einmal wiederholt: Server
      verwerfen einen Werkzeugaufruf mit ungültigem JSON stillschweigend, und ein
      erneuter Zug liefert meist eine brauchbare Ausgabe.
    - Werkzeugargumente, die kein JSON-Objekt sind, gehen als Fehlermeldung an
      das Modell zurück statt den Lauf abzubrechen.
    - Fehler der Modellaufrufe werden nicht abgefangen; der Aufrufer fällt auf
      Standard-RAG zurück bzw. meldet Kapazitätsfehler.
    """
    retried = False
    offered = text_calls.tool_names(adapter.tools)
    async with httpx.AsyncClient(timeout=120.0) as client:
        for turn_index in range(MAX_AGENT_TURNS):
            final = turn_index == MAX_AGENT_TURNS - 1
            pending = must_research and not researched and not final
            if final:
                adapter.add_user_text(_FINAL_TURN_INSTRUCTION)
            tool_choice = "none" if final else "required" if pending else None

            turn: Optional[ModelTurn] = None
            recovered = False
            for attempt in range(2):
                markup = text_calls.MarkupFilter()
                async for item in adapter.complete(client, turn_index, tool_choice):
                    if isinstance(item, ModelTurn):
                        turn = item
                    elif not pending:
                        visible = markup.feed(item)
                        if visible:
                            yield {"type": "content_chunk", "content": visible}
                if not pending:
                    rest = markup.flush()
                    if rest:
                        yield {"type": "content_chunk", "content": rest}
                found = (
                    None if turn.tool_calls else text_calls.recover(turn.text, offered, turn_index)
                )
                if found and final:
                    # Im Abschlusszug gibt es keine Werkzeuge mehr; das Markup gehört nicht in die Antwort.
                    turn.text = found[0]
                elif found:
                    logger.warning(
                        "Modellzug %s schrieb Werkzeugaufrufe als Text; ausgeführt: %s",
                        turn_index,
                        [call.name for call in found[1]],
                    )
                    turn.text, turn.tool_calls = found
                    recovered = True
                yield {
                    "type": "model_usage",
                    "turn": turn_index,
                    "prompt_tokens": turn.prompt_tokens,
                    "completion_tokens": turn.completion_tokens,
                    "finish_reason": turn.finish_reason,
                }
                if turn.finish_reason == "length":
                    logger.warning(
                        "Modellzug %s endete an der Token- bzw. Kontextgrenze (prompt_tokens=%s)",
                        turn_index,
                        turn.prompt_tokens,
                    )
                if turn.text.strip() or (turn.tool_calls and not final):
                    break
                if attempt == 0:
                    logger.warning("Modellzug %s war leer; wird einmal wiederholt", turn_index)
            calls = [] if final else turn.tool_calls
            if turn.text and (calls or not pending):
                agent_steps.append({"type": "thought", "content": turn.text})
                if pending or not adapter.streams:
                    yield {"type": "content_chunk", "content": turn.text}

            if calls:
                results = []
                for call in calls:
                    call_event, _ = _tool_events(call, "", {})
                    agent_steps.append(call_event)
                    yield dict(call_event)
                    if isinstance(call.arguments, dict):
                        result = await execute_tool(call.name, call.arguments, call.id)
                    else:
                        result = _INVALID_ARGUMENTS_RESULT.format(name=call.name)
                    _, result_event = _tool_events(call, result, execution_metadata(call.id))
                    agent_steps.append(result_event)
                    yield dict(result_event)
                    results.append(result)
                # Ein als Text erkannter Aufruf steht nicht in der Assistenten-Nachricht des Servers; sie wird nachgebildet.
                adapter.add_tool_results(calls, results, None if recovered else turn)
                researched = True
                yield {"type": "turn_completed", "has_tool_calls": True}
                continue

            if pending:
                if not retried:
                    retried = True
                    logger.warning(
                        "LLM ignorierte tool_choice=required; erzwinge einen zweiten Tool-Versuch"
                    )
                    continue
                yield {"type": "turn_completed", "has_tool_calls": False}
                yield {"type": "answer", "content": _NO_RESEARCH_ANSWER, "agent_steps": agent_steps}
                return

            yield {"type": "turn_completed", "has_tool_calls": False}
            yield {"type": "answer", "content": turn.text, "agent_steps": agent_steps}
            return


async def run_agent_loop(
    provider: str,
    model_name: str,
    api_key: str,
    base_url: str,
    system_prompt: str,
    prompt: str,
    temperature: float,
    repo_id: Optional[int],
    db_session,
    mcp_clients: List[MCPClient],
    ollama_base_url: str = "http://ollama:11434",
    chat_history: Optional[List[Dict[str, str]]] = None,
    project_id: Optional[int] = None,
    pinned_file: Optional[str] = None,
    pinned_line: Optional[int] = None,
    pinned_end_line: Optional[int] = None,
    audit_user_id: Optional[int] = None,
    audit_chat_session_id: Optional[int] = None,
    audit_chat_message_id: Optional[int] = None,
    endpoint_path: Optional[str] = None,
    require_initial_tool_call: bool = False,
    walkthrough_documents: Optional[List[Dict[str, Any]]] = None,
    mcp_initialization_status: Optional[List[Dict[str, Any]]] = None,
    evidence_chars: Optional[int] = None,
    context_length: Optional[int] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Runs the agent loop. Automatically combines local repository tools and MCP tools,
    presents them to the LLM via a provider adapter and resolves model tool calls in the
    shared research loop (_research_loop, up to MAX_AGENT_TURNS model calls),
    tracks thoughts and actions into an 'agent_steps' timeline, yielding steps in real-time.
    """

    agent_steps = []

    # 1. Define Local Repo/Project Tools
    # Only offer file-level repo tools if the repo was actually cloned to disk --
    # a Repository DB row can exist (e.g. clone still running, clone failed, or a
    # demo/AEC project whose real content lives in KnowledgeSources instead of a
    # git repo) without /repos/{id} ever existing, in which case every one of
    # these tools would just fail and mislead the model into thinking the
    # project's content is unavailable.
    repo_available = bool(repo_id) and os.path.isdir(repo_tools.get_repo_path(repo_id))
    walkthrough_documents = walkthrough_documents or []
    # Eine Rückfrage wie „ja, mach das“ erbt die Absicht der vorigen Nutzerfrage.
    previous_question = next(
        (m["content"] for m in reversed(chat_history or []) if m.get("role") == "user"), ""
    )
    local_tools_def = select_tools_for_question(
        local_tool_definitions(repo_available, walkthrough_documents, project_id),
        f"{_question_of(prompt)}\n{previous_question}",
    )
    mcp_tools_def, mcp_tool_map, mcp_preflight = await collect_mcp_tools(
        mcp_clients, mcp_initialization_status
    )
    agent_steps.append(mcp_preflight)
    yield mcp_preflight

    all_tools = local_tools_def + mcp_tools_def

    # 3. Securely handle no-tools fallback
    if not all_tools:
        # No tools available, exit generator so main.py falls back to standard LLM call
        return

    full_system_prompt = build_system_prompt(system_prompt, {tool["name"] for tool in all_tools})
    executor = AgentToolExecutor(
        repo_id=repo_id,
        repo_available=repo_available,
        project_id=project_id,
        db_session=db_session,
        audit_user_id=audit_user_id,
        audit_chat_session_id=audit_chat_session_id,
        audit_chat_message_id=audit_chat_message_id,
        walkthrough_documents=walkthrough_documents,
        mcp_tool_map=mcp_tool_map,
        prompt=prompt,
        evidence_chars=evidence_chars,
    )

    # Ollama's OpenAI-compatible endpoint does not reliably honor
    # ``tool_choice=required``. Make the first evidence-producing action
    # deterministic and feed its result into the model before it formulates
    # an answer.
    bootstrap_tool: Optional[ToolCall] = None
    bootstrap_result: Optional[str] = None
    prefetched = None
    if require_initial_tool_call and project_id and not pinned_file and cfg.CHAT_EVIDENCE_PREFETCH:
        prefetched = await _prefetch_evidence(
            db_session, audit_user_id, project_id, prompt, evidence_chars
        )
    if prefetched is not None:
        bootstrap_name, bootstrap_args, bootstrap_result = prefetched
    elif require_initial_tool_call and project_id:
        bootstrap_name, bootstrap_args, focus = plan_bootstrap(
            prompt,
            repo_id=repo_id,
            repo_available=repo_available,
            pinned_file=pinned_file,
            pinned_line=pinned_line,
            pinned_end_line=pinned_end_line,
        )
        # Nennt die Frage weder Symbol noch Datei, bliebe nur die Liste der ersten Entitäten; der
        # Projektüberblick aus dem Index trägt für solche Fragen deutlich mehr.
        generic = bootstrap_name == "get_repo_entities" and bootstrap_args == {"limit": 20}
        if generic and cfg.CHAT_EVIDENCE_PREFETCH:
            prefetched = await _prefetch_evidence(
                db_session, audit_user_id, project_id, prompt, evidence_chars, overview=True
            )
        if prefetched is not None:
            bootstrap_name, bootstrap_args, bootstrap_result = prefetched
        else:
            # Vor dem ersten Aufruf setzen: Alle Repository-Werkzeuge bleiben auf die genannten Dateien begrenzt.
            executor.file_focus_paths.update(focus)
            bootstrap_result = await executor.execute(bootstrap_name, bootstrap_args)
    if bootstrap_result is not None:
        bootstrap_tool = ToolCall("bootstrap-0", bootstrap_name, bootstrap_args)
        for event in _tool_events(bootstrap_tool, bootstrap_result, {}):
            agent_steps.append(event)
            yield dict(event)

    adapter = make_provider_adapter(
        provider,
        api_key=api_key,
        base_url=base_url,
        endpoint_path=endpoint_path,
        ollama_base_url=ollama_base_url,
        model_name=model_name,
        system_prompt=full_system_prompt,
        tools=all_tools,
        history=chat_history or [],
        prompt=prompt,
        temperature=temperature,
        context_length=context_length,
    )
    if adapter is None:
        return
    if bootstrap_tool is not None:
        adapter.add_tool_results([bootstrap_tool], [bootstrap_result], None)
    async for event in _research_loop(
        adapter,
        executor.execute,
        executor.execution_metadata,
        agent_steps,
        must_research=require_initial_tool_call,
        researched=bootstrap_tool is not None,
    ):
        yield event
