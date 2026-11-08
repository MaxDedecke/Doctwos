"""Werkzeugergebnisse des Chat-Agenten begrenzen, bevor sie in den Modellkontext gehen."""

from typing import Any

from services.linked_record_projection import compact_linked_records

from services.reviewed_evidence import NOTICE, compact_insights, compact_builds, fit_result


# O-168: die lokalen Repo-Werkzeuge (list_repo_files/view_repo_file/
# search_repo_code/get_repo_entities) sind alle schon auf vernünftige Größen
# gedeckelt (300 Zeilen, 250 Dateien, 80 Treffer). MCP-Werkzeuge (Jira/
# Confluence etc.) sind das nicht -- ein einzelnes großes Confluence-Dokument
# oder Jira-Ticket kann unbegrenzt groß sein. Über bis zu MAX_AGENT_TURNS Runden mit
# mehreren Werkzeugaufrufen pro Runde summiert sich das ungedeckelt in der
# `messages`-Liste, die bei jeder weiteren Runde komplett erneut ans Modell
# geschickt wird. Deckel hier statt in mcp_client.py: dort wäre der Kontext
# (wie viele Runden noch offen sind, was das Modell sonst schon gesehen hat)
# nicht bekannt; execute_tool() ist außerdem der einzige Punkt, den alle
# Anbieter-Adapter (services/agent_providers.py) gemeinsam durchlaufen.
MAX_MCP_TOOL_RESULT_CHARS = 8000

# Auch als Marker genutzt, um in _tool_events zu erkennen, ob ein bestimmtes
# Werkzeugergebnis gekürzt wurde (_cap_tool_result gibt nur den fertigen String
# zurück, execute_tool() bleibt bewusst bei "-> str" statt eines Tupels, weil
# jeder Anbieter-Adapter das Ergebnis direkt als Nachrichteninhalt verwendet). Das gesetzte "truncated"-Flag löst
# in AgentSteps.tsx ein immer sichtbares Badge im (auch eingeklappten) Header
# aus, statt dass die Kürzung nur im ausgeklappten Werkzeugergebnis auffällt.
_TOOL_RESULT_TRUNCATION_MARKER = "[… gekürzt:"


def _cap_tool_result(text: str, max_chars: int = MAX_MCP_TOOL_RESULT_CHARS) -> str:
    """Kürzt ein MCP-Werkzeugergebnis auf max_chars und hängt eine sichtbare
    Kürzungsnotiz an. Die Notiz landet unverändert im 'tool_result'-Schritt,
    den das Frontend (AgentSteps.tsx) je Werkzeugaufruf anzeigt -- die
    Kürzung ist also für den Nutzer nachvollziehbar, nicht still."""
    if len(text) <= max_chars:
        return text
    removed = len(text) - max_chars
    return (
        f"{text[:max_chars]}\n\n"
        f"{_TOOL_RESULT_TRUNCATION_MARKER} {removed} weitere Zeichen entfernt, um das "
        "Kontextfenster des Sprachmodells nicht zu sprengen. Bei Bedarf gezielter "
        "nachfragen, um den fehlenden Teil zu bekommen.]"
    )


def _tool_result_was_truncated(tool_res: str) -> bool:
    return _TOOL_RESULT_TRUNCATION_MARKER in tool_res


def _compact_change_package_for_agent(package: dict) -> dict:
    """Keep chat evidence useful and bounded; the shared HTTP API remains complete."""
    if package.get("error"):
        return package

    def compact_path(path: Any) -> Any:
        if not isinstance(path, dict):
            return None
        return {
            "root_entity_id": path.get("root_entity_id"),
            "hops": path.get("hops"),
            "edges": [
                {
                    name: edge.get(name)
                    for name in (
                        "edge_id",
                        "from_entity_id",
                        "to_entity_id",
                        "relationship",
                        "resolution",
                        "evidence_file",
                        "evidence_start_line",
                        "evidence_end_line",
                    )
                }
                for edge in path.get("edges", [])[:3]
                if isinstance(edge, dict)
            ],
        }

    code = []
    for node in package.get("affected_code", [])[:6]:
        if not isinstance(node, dict):
            continue
        compact_node = {
            name: node.get(name)
            for name in (
                "id",
                "name",
                "qualified_name",
                "type",
                "file_path",
                "source_id",
                "start_line",
                "end_line",
            )
            if name in node
        }
        compact_node["relationship_path"] = compact_path(node.get("relationship_path"))
        if isinstance(node.get("evidence"), dict) and node["evidence"].get("unresolved_candidates"):
            compact_node["evidence"] = node["evidence"]
        code.append(compact_node)

    tests = package.get("tests", {})
    responsibility = package.get("responsibility", {})
    impact = package.get("change_impact", {})
    result = {
        "schema_version": package.get("schema_version"),
        "status": package.get("status"),
        "impact_status": package.get("impact_status"),
        "target": package.get("target"),
        "scope": package.get("scope"),
        "impact_summary": impact.get("impact_summary") if isinstance(impact, dict) else None,
        "insights": compact_insights(package.get("insights", [])),
        "ci_builds": compact_builds(package.get("ci_builds") or {}),
        "project_evidence_notice": NOTICE,
        "affected_code": code,
        "linked_knowledge": compact_linked_records(
            package.get("linked_knowledge", []), 4, include_text=True
        ),
        "historical_issues": compact_linked_records(
            package.get("historical_issues", []), 4, include_text=True
        ),
        "tests": {
            "status": tests.get("status") if isinstance(tests, dict) else "unknown",
            "items": tests.get("items", [])[:5] if isinstance(tests, dict) else [],
            "truncated": tests.get("truncated", False) if isinstance(tests, dict) else False,
            "coverage_claim": "none",
            "note": tests.get("note") if isinstance(tests, dict) else None,
        },
        "responsibility": {
            "status": responsibility.get("status")
            if isinstance(responsibility, dict)
            else "unknown",
            "items": responsibility.get("items", [])[:5]
            if isinstance(responsibility, dict)
            else [],
            "unknown_files": responsibility.get("unknown_files", [])[:5]
            if isinstance(responsibility, dict)
            else [],
            "partial": responsibility.get("partial", False)
            if isinstance(responsibility, dict)
            else True,
            "note": responsibility.get("note") if isinstance(responsibility, dict) else None,
        },
        "evidence_gaps": package.get("evidence_gaps", []),
        "limitations": package.get("limitations", []),
        "presentation_truncated": {
            "insights": len(package.get("insights", [])) > 5,
            "ci_builds": bool((package.get("ci_builds") or {}).get("truncated"))
            or len((package.get("ci_builds") or {}).get("items", [])) > 5,
            "affected_code": len(package.get("affected_code", [])) > len(code),
            "linked_knowledge": len(package.get("linked_knowledge", [])) > 4,
            "historical_issues": len(package.get("historical_issues", [])) > 4,
            "tests": bool(tests.get("truncated")) if isinstance(tests, dict) else False,
        },
    }
    return fit_result(result, 8000)


# Unified Agent Execution Loop
