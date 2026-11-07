"""Ausführung der Werkzeuge des Chat-Agenten mit dem Zustand eines Durchgangs.

Früher eine 530-Zeilen-Closure in agent.run_agent_loop. Eine Methode je Werkzeug; der Zustand (Dateifokus, exakt
aufgelöste Entitäten, bestätigte Aufrufketten, MCP-Messwerte) gilt nur für einen Durchgang.
"""

import logging
import json
import re
import time
from typing import Any, Optional
from doctus_models.database import CodeEntity, KnowledgeSource, User
from core.projects import get_visible_project_ids
from core.teams import get_visible_team_ids
from services.mcp_audit import record_mcp_tool_call
from services.call_flow import trace_call_flow
from services.change_impact import inspect_change_impact
from services.change_package import inspect_change_package
from api.graph import get_graph_neighborhood
from services.search import search_nodes

from services import agent_repo_tools as repo_tools

from services.agent_tool_results import _cap_tool_result, _compact_change_package_for_agent

logger = logging.getLogger(__name__)


def _trace_target_names(prompt: str) -> set[str]:
    """In Backticks genannte Ziele (`Klasse.methode`, `PROGRAMM.PARAGRAPH`); call_flow darf nur auf sie zeigen."""
    question_for_focus = prompt.rsplit("Question:", 1)[-1] if "Question:" in prompt else prompt
    trace_target_names: set[str] = set()
    for raw in re.findall(r"`([^`]+)`", question_for_focus):
        value = raw.strip()
        if re.search(r"(?i)\.(?:java|cbl|cpy|xsl|xml|jcl|pom)$", value) or "/" in value:
            continue
        parts = [
            part for part in value.split(".") if re.fullmatch(r"[A-Za-z][A-Za-z0-9:_-]*", part)
        ]
        if parts:
            # A dotted reference names the concrete member/paragraph after
            # the dot (`COPAUA0C.MAIN-PARA`, `UserServiceImpl.create`).
            trace_target_names.add(parts[-1].casefold())
    return trace_target_names


class AgentToolExecutor:
    def __init__(
        self,
        *,
        repo_id: Optional[int],
        repo_available: bool,
        project_id: Optional[int],
        db_session,
        audit_user_id: Optional[int],
        audit_chat_session_id: Optional[int],
        audit_chat_message_id: Optional[int],
        walkthrough_documents: list[dict[str, Any]],
        mcp_tool_map: dict[str, Any],
        prompt: str,
    ) -> None:
        self.repo_id = repo_id
        self.repo_available = repo_available
        self.project_id = project_id
        self.db_session = db_session
        self.audit_user_id = audit_user_id
        self.audit_chat_session_id = audit_chat_session_id
        self.audit_chat_message_id = audit_chat_message_id
        self.walkthrough_documents = walkthrough_documents
        self.mcp_tool_map = mcp_tool_map
        # Erfolgreiche Aufrufketten gelten nur für diesen Durchgang; nur auf sie darf eine Tour verweisen.
        self.validated_call_flows: dict[str, dict] = {}
        self.file_focus_paths: set[str] = set()
        self.exact_trace_entities: dict[int, dict[str, Any]] = {}
        self.trace_target_names = _trace_target_names(prompt)
        self.mcp_execution_metrics: dict[str, dict[str, Any]] = {}

    def execution_metadata(self, tool_call_id: Optional[str]) -> dict[str, Any]:
        return self.mcp_execution_metrics.pop(tool_call_id, {}) if tool_call_id else {}

    def _remember_exact_trace_entities(self, result: dict) -> None:
        for entity in result.get("entities", []):
            if not isinstance(entity, dict) or not isinstance(entity.get("id"), int):
                continue
            self.exact_trace_entities[entity["id"]] = entity

    def _is_in_file_focus(self, path: str) -> bool:
        if not self.file_focus_paths:
            return True
        normalized = str(path or "").replace("\\", "/").lstrip("./").lower()
        return normalized in self.file_focus_paths

    def _available(self, name: str) -> bool:
        return bool(
            {
                "list_repo_files": self.repo_available,
                "view_repo_file": self.repo_available,
                "search_repo_code": self.repo_available,
                "offer_code_walkthrough": (self.repo_available or self.project_id),
                "offer_source_walkthrough": self.walkthrough_documents,
                "get_repo_entities": self.project_id,
                "trace_call_flow": self.project_id,
                "show_graph_neighborhood": self.project_id,
                "search_knowledge": self.project_id,
                "inspect_change_impact": self.project_id,
                "inspect_change_package": self.project_id,
            }.get(name, False)
        )

    async def execute(self, name: str, args: dict, tool_call_id: Optional[str] = None) -> str:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is not None and self._available(name):
            return await handler(args, tool_call_id)
        if name in self.mcp_tool_map:
            return await self._call_mcp_tool(name, args, tool_call_id)
        return f"Fehler: Werkzeug '{name}' ist nicht registriert."

    async def _tool_list_repo_files(self, args: dict, tool_call_id: Optional[str]) -> str:
        dir_val = args.get("directory", "")
        res = repo_tools.list_repo_files(self.repo_id, dir_val)
        if self.file_focus_paths and "files" in res:
            res["files"] = [path for path in res["files"] if self._is_in_file_focus(path)]
            res["total_files"] = len(res["files"])
            res["truncated"] = False
        return json.dumps(res)

    async def _tool_view_repo_file(self, args: dict, tool_call_id: Optional[str]) -> str:
        path_val = args.get("file_path", "")
        start_val = args.get("start_line", 1)
        end_val = args.get("end_line", 150)
        if self.file_focus_paths and not self._is_in_file_focus(path_val):
            focused_matches = [
                path
                for path in repo_tools.find_repo_files(self.repo_id, path_val)
                if self._is_in_file_focus(path)
            ]
            if len(focused_matches) == 1:
                path_val = focused_matches[0]
            else:
                return json.dumps(
                    {
                        "error": "Die Frage ist auf eine konkrete Datei begrenzt; diese Datei liegt außerhalb des Dateifokus.",
                        "file_focus": sorted(self.file_focus_paths),
                    }
                )
        res = repo_tools.view_repo_file(self.repo_id, path_val, start_val, end_val)
        if res.get("error") and path_val:
            # Models sometimes infer the wrong COBOL subdirectory from a
            # neighboring program. Resolve only an unambiguous basename;
            # never guess when multiple files share that name.
            matches = repo_tools.find_repo_files(self.repo_id, path_val)
            if len(matches) == 1:
                resolved = repo_tools.view_repo_file(self.repo_id, matches[0], start_val, end_val)
                if not resolved.get("error"):
                    resolved["requested_file_path"] = path_val
                    resolved["path_was_resolved"] = True
                    res = resolved
        return json.dumps(res)

    async def _tool_search_repo_code(self, args: dict, tool_call_id: Optional[str]) -> str:
        query_val = args.get("query", "")
        res = repo_tools.search_repo_code(self.repo_id, query_val)
        if self.file_focus_paths:
            res["matches"] = [
                match for match in res["matches"] if self._is_in_file_focus(match.get("file", ""))
            ]
            res["total_matches"] = len(res["matches"])
            res["truncated"] = False
        return json.dumps(res)

    async def _tool_offer_code_walkthrough(self, args: dict, tool_call_id: Optional[str]) -> str:
        title = str(args.get("title", "")).strip()[:120]
        raw_steps = args.get("steps")
        if not title or not isinstance(raw_steps, list) or not 2 <= len(raw_steps) <= 6:
            return json.dumps({"error": "A walkthrough needs a title and 2 to 6 steps."})
        steps = []
        for raw_step in raw_steps:
            if not isinstance(raw_step, dict):
                return json.dumps({"error": "Every walkthrough step must be an object."})
            explanation = str(raw_step.get("explanation", "")).strip()[:500]
            if not explanation:
                return json.dumps({"error": "Every walkthrough step needs an explanation."})
            if raw_step.get("kind") == "callgraph":
                trace_tool_call_id = raw_step.get("trace_tool_call_id")
                edge_id = raw_step.get("edge_id")
                flow = (
                    self.validated_call_flows.get(trace_tool_call_id)
                    if isinstance(trace_tool_call_id, str)
                    else None
                )
                if not isinstance(edge_id, int) or isinstance(edge_id, bool) or flow is None:
                    return json.dumps(
                        {
                            "error": "A graph step must reference an earlier successful call-flow result and one of its edges."
                        }
                    )
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
                ):
                    return json.dumps(
                        {
                            "error": f"Call-flow edge '{edge_id}' is not a resolved edge in the referenced result."
                        }
                    )
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
                        "explanation": explanation,
                    }
                )
                continue
            if raw_step.get("kind") not in (None, "code"):
                return json.dumps({"error": "Walkthrough step kind must be code or callgraph."})
            if not self.repo_available:
                return json.dumps(
                    {
                        "error": "Code walkthrough steps require an available repository; use only validated callgraph steps."
                    }
                )
            file_path = str(raw_step.get("file_path", "")).replace("\\", "/").strip()
            try:
                start_line = int(raw_step.get("start_line", 1))
                end_line = int(raw_step.get("end_line", start_line))
            except (TypeError, ValueError):
                return json.dumps({"error": "Walkthrough line numbers must be integers."})
            inspected = repo_tools.view_repo_file(self.repo_id, file_path, start_line, end_line)
            if inspected.get("error") or inspected.get("start_line", 0) < 1 or not explanation:
                return json.dumps({"error": f"Invalid walkthrough step for '{file_path}'."})
            steps.append(
                {
                    "file_path": inspected["file_path"].replace("\\", "/"),
                    "start_line": inspected["start_line"],
                    "end_line": inspected["end_line"],
                    "explanation": explanation,
                }
            )
        return json.dumps({"status": "ok", "title": title, "steps": steps})

    async def _tool_offer_source_walkthrough(self, args: dict, tool_call_id: Optional[str]) -> str:
        title = str(args.get("title", "")).strip()[:120]
        raw_steps = args.get("steps")
        candidates = {
            item.get("chunk_id"): item
            for item in self.walkthrough_documents
            if isinstance(item, dict) and isinstance(item.get("chunk_id"), int)
        }
        if not title or not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= 6:
            return json.dumps({"error": "A source walkthrough needs a title and 1 to 6 steps."})
        steps = []
        for raw_step in raw_steps:
            if not isinstance(raw_step, dict):
                return json.dumps({"error": "Every walkthrough step must be an object."})
            chunk_id = raw_step.get("chunk_id")
            candidate = candidates.get(chunk_id)
            explanation = str(raw_step.get("explanation", "")).strip()[:500]
            if not candidate or not explanation:
                return json.dumps(
                    {"error": f"Document chunk '{chunk_id}' is not available for this turn."}
                )
            steps.append({**candidate, "kind": "document", "explanation": explanation})
        return json.dumps({"status": "ok", "title": title, "steps": steps})

    async def _tool_get_repo_entities(self, args: dict, tool_call_id: Optional[str]) -> str:
        query_val = args.get("query", "")
        focused_paths = sorted(self.file_focus_paths) or None
        res = repo_tools.get_repo_entities(
            self.project_id,
            self.db_session,
            query_val,
            args.get("limit", 80),
            focused_paths,
            args.get("entity_names"),
        )
        if args.get("entity_names") and not res.get("error"):
            self._remember_exact_trace_entities(res)
        return json.dumps(res)

    async def _tool_trace_call_flow(self, args: dict, tool_call_id: Optional[str]) -> str:
        entity_id = args.get("entity_id")
        candidate = (
            self.exact_trace_entities.get(entity_id)
            if isinstance(entity_id, int) and not isinstance(entity_id, bool)
            else None
        )
        if (self.file_focus_paths or self.trace_target_names) and candidate is None:
            return json.dumps(
                {
                    "error": "Call-Flow erfordert zuerst eine exakte, dateigebundene Entity-Auflösung.",
                    "resolution_status": "entity_not_exactly_resolved",
                    "expected_names": sorted(self.trace_target_names),
                    "candidates": list(self.exact_trace_entities.values()),
                }
            )
        if (
            candidate is not None
            and self.trace_target_names
            and str(candidate.get("name") or "").casefold() not in self.trace_target_names
        ):
            return json.dumps(
                {
                    "error": "Die gewählte Entity entspricht nicht dem in der Frage genannten Ziel.",
                    "resolution_status": "entity_name_mismatch",
                    "expected_names": sorted(self.trace_target_names),
                    "selected": candidate,
                }
            )
        res = trace_call_flow(
            self.db_session,
            project_id=self.project_id,
            entity_id=entity_id,
            hops=args.get("hops", 5),
            direction=args.get("direction", "outgoing"),
        )
        if (
            isinstance(tool_call_id, str)
            and res.get("status") == "ok"
            and isinstance(res.get("edges"), list)
            and isinstance(res.get("nodes"), list)
        ):
            self.validated_call_flows[tool_call_id] = res
            res = {**res, "tool_call_id": tool_call_id}
        return json.dumps(res)

    async def _tool_show_graph_neighborhood(self, args: dict, tool_call_id: Optional[str]) -> str:
        entity_id = args.get("entity_id")
        if not isinstance(entity_id, int) or isinstance(entity_id, bool) or entity_id < 1:
            return json.dumps({"error": "A positive indexed entity_id is required."})
        direction = args.get("direction", "both")
        if direction not in {"incoming", "outgoing", "both"}:
            return json.dumps({"error": "direction must be incoming, outgoing, or both."})
        allowed_relationships = {"code_dependency", "documented", "manual"}
        relationships = args.get("relationships", ["code_dependency", "documented", "manual"])
        if (
            not isinstance(relationships, list)
            or not relationships
            or len(relationships) > len(allowed_relationships)
            or any(
                not isinstance(item, str) or item not in allowed_relationships
                for item in relationships
            )
            or len(set(relationships)) != len(relationships)
        ):
            return json.dumps(
                {"error": "relationships must contain unique supported relationship types."}
            )
        entity = (
            self.db_session.query(CodeEntity)
            .filter(
                CodeEntity.id == entity_id,
                CodeEntity.project_id == self.project_id,
            )
            .first()
        )
        user = (
            self.db_session.query(User).filter(User.id == self.audit_user_id).first()
            if self.audit_user_id is not None
            else None
        )
        if not entity or not user:
            return json.dumps(
                {"error": "The indexed entity is unavailable in the current project context."}
            )
        try:
            graph = get_graph_neighborhood(
                node_id=f"entity:{entity_id}",
                project_id=self.project_id,
                relationships=",".join(relationships),
                status="approved",
                direction=direction,
                hops=1,
                limit=40,
                cursor=None,
                db=self.db_session,
                user=user,
            )
        except Exception as ex:
            logger.warning("Knowledge graph neighborhood lookup failed: %s", ex)
            return json.dumps({"error": "The graph neighborhood could not be loaded."})
        focus_id = graph.get("focus_id")
        focus_node = next(
            (
                node
                for node in graph.get("nodes", [])
                if isinstance(node, dict) and node.get("id") == focus_id
            ),
            None,
        )
        if not isinstance(focus_id, str) or not focus_node:
            return json.dumps({"error": "The indexed entity has no visible graph neighborhood."})
        raw_edges = graph.get("edges", [])
        matching_edges = []
        if isinstance(raw_edges, list):
            for edge in raw_edges:
                if not isinstance(edge, dict):
                    continue
                relation = edge.get("relation_type")
                edge_direction = edge.get("direction") or "undirected"
                source = edge.get("source")
                target = edge.get("target")
                source_id = source.get("id") if isinstance(source, dict) else source
                target_id = target.get("id") if isinstance(target, dict) else target

                # The graph endpoint applies direction to code dependencies.
                # Apply it here for the other edge types, which it returns
                # without directional filtering.
                if relation == "documented" and direction == "outgoing":
                    continue
                if str(edge.get("id", "")).startswith("kl:") and edge_direction == "directed":
                    if direction == "outgoing" and source_id != focus_id:
                        continue
                    if direction == "incoming" and target_id != focus_id:
                        continue
                matching_edges.append(edge)
        edges = matching_edges[:40]
        visible_node_ids = {focus_id}
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            for endpoint in (edge.get("source"), edge.get("target")):
                endpoint_id = endpoint.get("id") if isinstance(endpoint, dict) else endpoint
                if isinstance(endpoint_id, str):
                    visible_node_ids.add(endpoint_id)
        nodes = [
            node
            for node in graph.get("nodes", [])
            if isinstance(node, dict) and node.get("id") in visible_node_ids
        ]
        was_truncated = len(matching_edges) > len(edges) or bool(graph.get("has_more"))
        return json.dumps(
            {
                **graph,
                "nodes": nodes,
                "edges": edges,
                "has_more": was_truncated,
                "truncated": was_truncated,
                "status": "ok",
                "focus_label": str(focus_node.get("label") or focus_node.get("name") or "")[:500],
                "direction": direction,
                "hops": 1,
                "limit": 40,
                "relationships": relationships,
            }
        )

    async def _tool_search_knowledge(self, args: dict, tool_call_id: Optional[str]) -> str:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 200:
            return json.dumps({"error": "query must contain 1 to 200 characters."})
        types = args.get("types", ["entity", "document"])
        allowed_types = {"entity", "document"}
        if (
            not isinstance(types, list)
            or not types
            or len(types) > len(allowed_types)
            or any(not isinstance(item, str) or item not in allowed_types for item in types)
            or len(set(types)) != len(types)
        ):
            return json.dumps({"error": "types must contain unique supported search types."})
        source_id = args.get("source_id")
        if source_id is not None and (
            not isinstance(source_id, int)
            or isinstance(source_id, bool)
            or source_id < 1
            or "document" not in types
        ):
            return json.dumps(
                {"error": "source_id requires document search and a positive source ID."}
            )
        user = (
            self.db_session.query(User).filter(User.id == self.audit_user_id).first()
            if self.audit_user_id is not None
            else None
        )
        if not user:
            return json.dumps({"error": "The current user context is unavailable."})
        visible_project_ids = get_visible_project_ids(user, self.db_session)
        if visible_project_ids is not None and self.project_id not in visible_project_ids:
            return json.dumps({"error": "The current project is not available to this user."})
        if source_id is not None:
            source = (
                self.db_session.query(KnowledgeSource)
                .filter(KnowledgeSource.id == source_id)
                .first()
            )
            visible_team_ids = get_visible_team_ids(user, self.db_session)
            if (
                not source
                or source.project_id != self.project_id
                or (visible_team_ids is not None and source.team_id not in visible_team_ids)
            ):
                return json.dumps(
                    {"error": "The selected source is unavailable in the current project context."}
                )
            types = ["document"]
        try:
            results, counts = search_nodes(
                self.db_session,
                q=query.strip(),
                types=",".join(types),
                project_id=self.project_id,
                source_id=source_id,
                limit=10,
                visible_team_ids=get_visible_team_ids(user, self.db_session),
                visible_project_ids=visible_project_ids,
            )
        except Exception as ex:
            logger.warning("Knowledge search failed: %s", ex)
            return json.dumps({"error": "The knowledge search could not be completed."})
        has_more = any(
            int(counts.get(search_type, 0) or 0)
            > sum(
                1
                for result in results
                if isinstance(result, dict) and result.get("node_type") == search_type
            )
            for search_type in types
        )
        return json.dumps(
            {
                "status": "ok",
                "query": query.strip(),
                "types": types,
                "project_id": self.project_id,
                "source_id": source_id,
                "limit": 10,
                "results": results[:20],
                "counts": {
                    search_type: int(counts.get(search_type, 0) or 0) for search_type in types
                },
                "has_more": has_more,
                "truncated": has_more,
            },
            ensure_ascii=False,
        )

    async def _tool_inspect_change_impact(self, args: dict, tool_call_id: Optional[str]) -> str:
        res = inspect_change_impact(
            self.db_session,
            project_id=self.project_id,
            entity_id=args.get("entity_id"),
            file_path=args.get("file_path"),
            direction=args.get("direction", "incoming"),
            hops=args.get("hops", 2),
            limit=args.get("limit", 40),
        )
        return json.dumps(res)

    async def _tool_inspect_change_package(self, args: dict, tool_call_id: Optional[str]) -> str:
        res = inspect_change_package(
            self.db_session,
            project_id=self.project_id,
            entity_id=args.get("entity_id"),
            file_path=args.get("file_path"),
            source_id=args.get("source_id"),
            base_ref=args.get("base_ref"),
            head_ref=args.get("head_ref"),
            direction=args.get("direction", "incoming"),
            hops=args.get("hops", 2),
            limit=args.get("limit", 40),
        )
        return _cap_tool_result(
            json.dumps(_compact_change_package_for_agent(res), ensure_ascii=False)
        )

    async def _call_mcp_tool(self, name: str, args: dict, tool_call_id: Optional[str]) -> str:
        mcp_client = self.mcp_tool_map[name]
        started_at = time.perf_counter()
        success = False
        error_message = None
        try:
            tool_res = await mcp_client.call_tool(name, args)
            success = not bool(tool_res.get("isError") or tool_res.get("error"))
            if not success:
                error_message = tool_res.get("error") or "MCP server returned an error"
            text_content = ""
            for item in tool_res.get("content", []):
                if item.get("type") == "text":
                    text_content += item.get("text", "")
            if not text_content:
                text_content = json.dumps(tool_res)
            return _cap_tool_result(text_content)
        except Exception as ex:
            error_message = ex
            return f"Fehler beim Aufruf des MCP-Tools: {ex}"
        finally:
            self.mcp_execution_metrics[tool_call_id or name] = {
                "mcp_server": mcp_client.name,
                "mcp_status": "success" if success else "error",
                "mcp_duration_ms": int((time.perf_counter() - started_at) * 1000),
            }
            if self.audit_user_id is not None:
                record_mcp_tool_call(
                    self.db_session,
                    user_id=self.audit_user_id,
                    chat_session_id=self.audit_chat_session_id,
                    chat_message_id=self.audit_chat_message_id,
                    project_id=self.project_id,
                    knowledge_source_id=getattr(mcp_client, "source_id", None),
                    server_name=mcp_client.name,
                    tool_name=name,
                    arguments=args,
                    success=success,
                    duration_ms=self.mcp_execution_metrics[tool_call_id or name]["mcp_duration_ms"],
                    error_message=error_message,
                )
