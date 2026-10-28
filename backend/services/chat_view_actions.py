"""
backend/services/chat_view_actions.py
=====================================
UI-Aktionen, die ein Agentenlauf dem Frontend anbietet (Graph-Nachbarschaft,
Callgraph, Code-/Quellen-Rundgang).

Eine Aktion entsteht nur aus einem erfolgreichen, strukturell geprüften
Werkzeugergebnis — nie aus Modellprosa. Ihre ID ist deterministisch aus Sitzung,
Runde, Tool-Call und Ziel abgeleitet, damit ein Wiederholen derselben Runde
dieselbe Aktion ergibt. Was der Client mit ihr gemacht hat, wird als Status an
der Assistenten-Nachricht vermerkt (update_view_action_status).
"""

import hashlib
import json
from typing import Optional

from sqlalchemy.orm import Session

from core.projects import assert_knowledge_source_visible, assert_project_visible
from doctus_models.database import ChatMessage, KnowledgeSource, User
from services.chat_errors import ChatInvalid, ChatNotFound

# Vom Client gemeldete Ergebnisse; „requested" setzt nur der Server.
VIEW_ACTION_STATUSES = frozenset(
    {"opened", "updated", "manual", "declined", "no_space", "rejected", "stale_context"}
)
_NOT_FOUND = "View-Aktion nicht gefunden"


def _view_action(
    event: dict,
    view: str,
    target: dict,
    identity: dict,
    session_id: int,
    turn_id: int,
    project_id: Optional[int],
) -> dict:
    target_key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()[
        :16
    ]
    action_key = f"{session_id}:{turn_id}:{event['id']}:{view}:{target_key}"
    return {
        "type": "view_action",
        "action_id": hashlib.sha256(action_key.encode("utf-8")).hexdigest()[:24],
        "session_id": session_id,
        "turn_id": turn_id,
        "project_id": project_id,
        "tool_call_id": event["id"],
        "view": view,
        "target": target,
        "status": "requested",
    }


def derive_view_action(
    event: dict,
    *,
    session_id: int,
    turn_id: int,
    project_id: Optional[int],
    call_flow_results: Optional[dict[str, dict]] = None,
) -> Optional[dict]:
    """Build one bounded walkthrough from the agent's explicit, validated offer."""
    if event.get("type") != "tool_result" or not isinstance(event.get("id"), str):
        return None
    result = event.get("result")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (TypeError, json.JSONDecodeError):
            return None
    if not isinstance(result, dict):
        return None

    tool_name = event.get("name")
    if tool_name == "show_graph_neighborhood":
        focus_id = result.get("focus_id")
        focus_label = result.get("focus_label")
        nodes = result.get("nodes")
        edges = result.get("edges")
        relationships = result.get("relationships")
        direction = result.get("direction")
        result_limit = result.get("limit")
        focus_node = (
            next(
                (node for node in nodes if isinstance(node, dict) and node.get("id") == focus_id),
                None,
            )
            if isinstance(nodes, list)
            else None
        )
        allowed_relationships = {"code_dependency", "documented", "manual"}
        if (
            result.get("status") != "ok"
            or project_id is None
            or not isinstance(focus_id, str)
            or not (focus_id.startswith("file:") or focus_id.startswith("doc:"))
            or not isinstance(focus_label, str)
            or not focus_label.strip()
            or not focus_node
            or not isinstance(edges, list)
            or not edges
            or len(edges) > 40
            or not isinstance(relationships, list)
            or not relationships
            or len(relationships) > len(allowed_relationships)
            or any(
                not isinstance(item, str) or item not in allowed_relationships
                for item in relationships
            )
            or len(set(relationships)) != len(relationships)
            or direction not in {"incoming", "outgoing", "both"}
            or result_limit != 40
        ):
            return None
        target = {
            "focus_id": focus_id,
            "focus_label": focus_label.strip()[:500],
            "direction": direction,
            "hops": 1,
            "limit": result_limit,
            "relationships": relationships,
        }
        return _view_action(event, "graph", target, target, session_id, turn_id, project_id)
    if tool_name == "inspect_change_impact":
        root = result.get("root")
        nodes = result.get("nodes")
        edges = result.get("edges")
        summary = result.get("impact_summary")
        if (
            result.get("status") != "ok"
            or not isinstance(root, dict)
            or not isinstance(root.get("id"), int)
            or isinstance(root.get("id"), bool)
            or not isinstance(nodes, list)
            or not any(isinstance(node, dict) and node.get("id") == root["id"] for node in nodes)
            or not isinstance(edges, list)
            or not edges
            or not isinstance(summary, dict)
        ):
            return None
        identity = {
            "root": root["id"],
            "edge_ids": [edge.get("id") for edge in edges[:120] if isinstance(edge, dict)],
            "summary": summary,
        }
        return _view_action(
            event, "callgraph", {"entity_id": root["id"]}, identity, session_id, turn_id, project_id
        )

    if (
        tool_name not in {"offer_code_walkthrough", "offer_source_walkthrough"}
        or result.get("status") != "ok"
    ):
        return None

    title = result.get("title")
    raw_steps = result.get("steps")
    minimum_steps = 1 if tool_name == "offer_source_walkthrough" else 2
    if (
        not isinstance(title, str)
        or not title.strip()
        or not isinstance(raw_steps, list)
        or not minimum_steps <= len(raw_steps) <= 6
    ):
        return None
    steps = []
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            return None
        if raw_step.get("kind") == "callgraph":
            if tool_name != "offer_code_walkthrough":
                return None
            trace_tool_call_id = raw_step.get("trace_tool_call_id")
            edge_id = raw_step.get("edge_id")
            flow = (
                call_flow_results.get(trace_tool_call_id)
                if isinstance(call_flow_results, dict) and isinstance(trace_tool_call_id, str)
                else None
            )
            if (
                not isinstance(edge_id, int)
                or isinstance(edge_id, bool)
                or not isinstance(flow, dict)
            ):
                return None
            edge = next(
                (
                    item
                    for item in flow.get("edges", [])
                    if isinstance(item, dict) and item.get("id") == edge_id
                ),
                None,
            )
            nodes = {
                item.get("id"): item for item in flow.get("nodes", []) if isinstance(item, dict)
            }
            source_id = edge.get("source") if edge else None
            target_id = edge.get("target") if edge else None
            source = nodes.get(source_id)
            target = nodes.get(target_id)
            explanation = raw_step.get("explanation")
            if (
                not edge
                or edge.get("resolution") != "resolved"
                or not isinstance(source_id, int)
                or isinstance(source_id, bool)
                or not isinstance(target_id, int)
                or isinstance(target_id, bool)
                or not source
                or not target
                or not str(source.get("name") or "").strip()
                or not str(target.get("name") or "").strip()
                or not isinstance(explanation, str)
                or not explanation.strip()
            ):
                return None
            steps.append(
                {
                    "kind": "callgraph",
                    "trace_tool_call_id": trace_tool_call_id,
                    "edge_id": edge_id,
                    "source_entity_id": source_id,
                    "target_entity_id": target_id,
                    "source_name": str(source.get("name") or "")[:240],
                    "target_name": str(target.get("name") or "")[:240],
                    "file_path": str(source.get("file_path") or "").replace("\\", "/")[:1000],
                    "start_line": edge.get("start_line"),
                    "end_line": edge.get("end_line"),
                    "explanation": explanation.strip()[:500],
                }
            )
            continue
        if raw_step.get("kind") not in (None, "code", "document"):
            return None
        if raw_step.get("kind") == "document":
            chunk_id = raw_step.get("chunk_id")
            source_id = raw_step.get("source_id")
            file_path = raw_step.get("file_path")
            explanation = raw_step.get("explanation")
            if (
                not isinstance(chunk_id, int)
                or isinstance(chunk_id, bool)
                or not isinstance(source_id, int)
                or isinstance(source_id, bool)
                or not isinstance(file_path, str)
                or not file_path.strip()
                or not isinstance(explanation, str)
                or not explanation.strip()
            ):
                return None
            steps.append(
                {
                    "kind": "document",
                    "chunk_id": chunk_id,
                    "source_id": source_id,
                    "file_path": file_path.strip()[:1000],
                    "start_line": raw_step.get("start_line"),
                    "end_line": raw_step.get("end_line"),
                    "page": raw_step.get("page"),
                    "section": raw_step.get("section"),
                    "source_type": raw_step.get("source_type"),
                    "url": raw_step.get("url"),
                    "excerpt": str(raw_step.get("excerpt") or "")[:1200],
                    "explanation": explanation.strip()[:500],
                }
            )
            continue
        file_path = raw_step.get("file_path")
        normalized_path = file_path.replace("\\", "/") if isinstance(file_path, str) else ""
        start_line = raw_step.get("start_line")
        end_line = raw_step.get("end_line")
        explanation = raw_step.get("explanation")
        if (
            not normalized_path
            or normalized_path.startswith("/")
            or ".." in normalized_path.split("/")
            or not isinstance(start_line, int)
            or isinstance(start_line, bool)
            or not isinstance(end_line, int)
            or isinstance(end_line, bool)
            or start_line < 1
            or end_line < start_line
            or not isinstance(explanation, str)
            or not explanation.strip()
        ):
            return None
        steps.append(
            {
                "file_path": normalized_path,
                "start_line": start_line,
                "end_line": end_line,
                "explanation": explanation.strip()[:500],
            }
        )

    target = {"title": title.strip()[:120], "steps": steps}
    return _view_action(event, "walkthrough", target, target, session_id, turn_id, project_id)


class ViewActionTracker:
    """Leitet während eines Agentenlaufs Aktionen ab und hält sie dedupliziert.

    Callgraph-Schritte eines Rundgangs verweisen auf ein früheres
    ``trace_call_flow``-Ergebnis derselben Runde; der Tracker merkt sich diese.
    """

    def __init__(self, session_id: int, turn_id: int, project_id: Optional[int]):
        self.session_id = session_id
        self.turn_id = turn_id
        self.project_id = project_id
        self.actions: list[dict] = []
        self._call_flows: dict[str, dict] = {}

    def observe(self, event: dict) -> Optional[dict]:
        """Gibt eine neue Aktion zurück, wenn ``event`` eine anbietet."""
        if (
            event.get("type") == "tool_result"
            and event.get("name") == "trace_call_flow"
            and isinstance(event.get("id"), str)
        ):
            result = event.get("result")
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except (TypeError, json.JSONDecodeError):
                    result = None
            if isinstance(result, dict) and result.get("status") == "ok":
                self._call_flows[event["id"]] = result
        action = derive_view_action(
            event,
            session_id=self.session_id,
            turn_id=self.turn_id,
            project_id=self.project_id,
            call_flow_results=self._call_flows,
        )
        if not action or any(a["action_id"] == action["action_id"] for a in self.actions):
            return None
        self.actions.append(action)
        return action

    def merge_into(self, agent_steps: list) -> list:
        """Die finalen Agentenschritte ersetzen die gestreamten; Aktionen dürfen dabei nicht verloren gehen."""
        known = {
            step.get("action_id")
            for step in agent_steps
            if isinstance(step, dict) and step.get("type") == "view_action"
        }
        return agent_steps + [a for a in self.actions if a["action_id"] not in known]


def _assert_action_visible(db: Session, user: User, step: dict) -> None:
    project_id = step.get("project_id")
    if isinstance(project_id, int) and not isinstance(project_id, bool):
        assert_project_visible(project_id, user, db, _NOT_FOUND)
        return
    if project_id is not None or step.get("view") != "walkthrough":
        raise ChatNotFound(_NOT_FOUND)
    # Ein Rundgang ohne Projekt besteht nur aus Dokumentschritten; jede
    # beteiligte Wissensquelle muss für den Nutzer sichtbar sein.
    target = step.get("target") or {}
    source_ids = {
        item.get("source_id")
        for item in target.get("steps", [])
        if isinstance(item, dict) and item.get("kind") == "document"
    }
    if not source_ids or any(not isinstance(source_id, int) for source_id in source_ids):
        raise ChatNotFound(_NOT_FOUND)
    for source_id in source_ids:
        source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
        if not source:
            raise ChatNotFound(_NOT_FOUND)
        assert_knowledge_source_visible(source, user, db, _NOT_FOUND)


def update_view_action_status(
    db: Session, message: ChatMessage, action_id: str, status: str, user: User
) -> None:
    """Vermerkt das vom Client beobachtete Ergebnis, ohne es als Modellergebnis auszugeben."""
    if status not in VIEW_ACTION_STATUSES:
        raise ChatInvalid("Ungültiger View-Aktionsstatus")
    metadata = dict(message.metadata_json or {})
    steps = metadata.get("agent_steps")
    if not isinstance(steps, list):
        raise ChatNotFound(_NOT_FOUND)

    updated = False
    next_steps = []
    for step in steps:
        if (
            isinstance(step, dict)
            and step.get("type") == "view_action"
            and step.get("action_id") == action_id
            and step.get("session_id") == message.session_id
        ):
            _assert_action_visible(db, user, step)
            next_steps.append({**step, "status": status})
            updated = True
        else:
            next_steps.append(step)
    if not updated:
        raise ChatNotFound(_NOT_FOUND)

    metadata["agent_steps"] = next_steps
    message.metadata_json = metadata
    db.commit()
