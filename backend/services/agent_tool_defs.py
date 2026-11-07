"""Werkzeugbeschreibungen (JSON-Schemas) des Chat-Agenten, abhängig von Repository, Dokumenten und Projekt."""

from typing import Any


def local_tool_definitions(
    repo_available: bool, walkthrough_documents: list[dict[str, Any]], project_id: int | None
) -> list[dict]:
    local_tools_def: list[dict] = []
    if repo_available:
        local_tools_def.extend(
            [
                {
                    "name": "list_repo_files",
                    "description": "Lists files in the repository recursively or in a subdirectory. Useful to inspect the project layout.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "directory": {
                                "type": "string",
                                "description": "Optional subdirectory to list files from (defaults to root).",
                            }
                        },
                    },
                },
                {
                    "name": "view_repo_file",
                    "description": "Reads lines from a file in the repository (1-indexed, inclusive). Use this to read the source code of files.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the file relative to the repository root.",
                            },
                            "start_line": {
                                "type": "integer",
                                "description": "Line number to start reading from (defaults to 1).",
                            },
                            "end_line": {
                                "type": "integer",
                                "description": "Line number to stop reading at (defaults to 150).",
                            },
                        },
                        "required": ["file_path"],
                    },
                },
                {
                    "name": "search_repo_code",
                    "description": "Searches for a string (case-insensitive) across code files in the repository. Use this to find references or usage.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The text query or symbol to search for.",
                            }
                        },
                        "required": ["query"],
                    },
                },
                {
                    "name": "offer_code_walkthrough",
                    "description": (
                        "Offers one optional, guided code and call-flow walkthrough in the chat. Use this only after "
                        "you have explained a class, flow, or concept and inspected every referenced "
                        "location. The user starts it explicitly and then moves through the steps with "
                        "Back and Next; code steps open and highlight inspected code, while callgraph steps "
                        "highlight a resolved edge from a successful trace_call_flow result made earlier in "
                        "this turn. For a callgraph step use kind='callgraph', trace_tool_call_id copied from "
                        "that result's tool_call_id field, and edge_id from its edges. Prefer 2-6 meaningful "
                        "steps. Do not call this once per file."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Short title for the guided explanation.",
                            },
                            "steps": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 6,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "kind": {"type": "string", "enum": ["code", "callgraph"]},
                                        "file_path": {"type": "string"},
                                        "start_line": {"type": "integer", "minimum": 1},
                                        "end_line": {"type": "integer", "minimum": 1},
                                        "trace_tool_call_id": {"type": "string"},
                                        "edge_id": {"type": "integer", "minimum": 1},
                                        "explanation": {
                                            "type": "string",
                                            "description": "A concise explanation of what to notice at this step.",
                                        },
                                    },
                                    "required": ["explanation"],
                                },
                            },
                        },
                        "required": ["title", "steps"],
                    },
                },
            ]
        )
    if walkthrough_documents:
        local_tools_def.append(
            {
                "name": "offer_source_walkthrough",
                "description": (
                    "Offers one optional guided walkthrough through document evidence already retrieved "
                    "for this answer. Use it after explaining the evidence, with 1-6 meaningful steps. "
                    "Each chunk_id must come from an <untrusted_source> context block. The UI opens the "
                    "internal document view and shows the exact indexed excerpt; do not invent pages or sections."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "steps": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 6,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "chunk_id": {"type": "integer", "minimum": 1},
                                    "explanation": {"type": "string"},
                                },
                                "required": ["chunk_id", "explanation"],
                            },
                        },
                    },
                    "required": ["title", "steps"],
                },
            }
        )
    if project_id:
        local_tools_def.append(
            {
                "name": "search_knowledge",
                "description": (
                    "Runs a bounded lexical search in the current project over indexed code entity names/paths "
                    "and document titles/paths. It does not perform semantic or full-text chunk search, "
                    "and path matches are weak evidence; prefer answer_context or explain_symbol for questions "
                    "about specific code."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "minLength": 1, "maxLength": 200},
                        "types": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["entity", "document"]},
                            "minItems": 1,
                            "maxItems": 2,
                            "uniqueItems": True,
                        },
                        "source_id": {"type": "integer", "minimum": 1},
                    },
                    "required": ["query"],
                },
            }
        )
        local_tools_def.append(
            {
                "name": "show_graph_neighborhood",
                "description": (
                    "Loads a read-only, bounded knowledge-graph neighborhood around an indexed entity "
                    "in the current project. Use get_repo_entities first to obtain its exact entity_id. "
                    "Use only relationships that help explain the answer; code_dependency is indexed "
                    "parser structure, documented links point to source documents, and manual links are "
                    "reviewed knowledge links. The graph view action is offered to the user separately."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "integer", "minimum": 1},
                        "relationships": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["code_dependency", "documented", "manual"],
                            },
                            "minItems": 1,
                            "maxItems": 3,
                            "uniqueItems": True,
                        },
                        "direction": {"type": "string", "enum": ["incoming", "outgoing", "both"]},
                    },
                    "required": ["entity_id"],
                },
            }
        )
        if not repo_available:
            local_tools_def.append(
                {
                    "name": "offer_code_walkthrough",
                    "description": (
                        "Offers a guided call-flow walkthrough using only resolved edges from successful "
                        "trace_call_flow results in this turn. The user starts and repeats it explicitly; "
                        "each step highlights its call edge in the existing Call Graph view."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "steps": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 6,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "kind": {"type": "string", "enum": ["callgraph"]},
                                        "trace_tool_call_id": {"type": "string"},
                                        "edge_id": {"type": "integer", "minimum": 1},
                                        "explanation": {"type": "string"},
                                    },
                                    "required": [
                                        "kind",
                                        "trace_tool_call_id",
                                        "edge_id",
                                        "explanation",
                                    ],
                                },
                            },
                        },
                        "required": ["title", "steps"],
                    },
                }
            )
        local_tools_def.append(
            {
                "name": "get_repo_entities",
                "description": "Retrieves parsed program symbols/code entities (classes, functions, elements) from the project index.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Optional search filter for entity name.",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 80,
                            "description": "Optional maximum number of entities to return.",
                        },
                        "entity_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional exact entity names; combines with a file focus when present.",
                        },
                    },
                },
            }
        )
        local_tools_def.append(
            {
                "name": "trace_call_flow",
                "description": (
                    "Follows the indexed, directed call flow from one code entity for up to "
                    "five hops. Use get_repo_entities first to obtain an entity ID. The result "
                    "contains code locations and Mermaid flowchart source for a chat diagram. "
                    "The tool result includes its tool_call_id; cite that ID if using one of its "
                    "resolved edges as a callgraph step in offer_code_walkthrough. "
                    "A class resolves to its unique Java main or sole method; otherwise choose "
                    "a relevant entry_candidates method using source evidence, or ask the user."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "integer",
                            "description": "ID returned by get_repo_entities.",
                        },
                        "hops": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 5,
                            "description": "Number of call hops to trace; defaults to 5.",
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["outgoing", "incoming", "both"],
                            "description": "outgoing explains what happens after an entry point is called.",
                        },
                    },
                    "required": ["entity_id"],
                },
            }
        )
        local_tools_def.append(
            {
                "name": "inspect_change_impact",
                "description": (
                    "Read-only, bounded analysis of what may be affected by changing one indexed "
                    "entity or file. Use incoming direction for callers/dependents, outgoing for "
                    "dependencies used by the target, or both for context. The result separates "
                    "statically resolved code edges, approved semantic cross-references, and "
                    "unresolved/dynamic name matches. It is not a complete runtime-impact proof. "
                    "Provide an entity_id from get_repo_entities, a repository-relative file_path "
                    "already found in repository context, or both when the entity belongs to that file. "
                    "When both selectors are given, the analysis covers the whole file."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Optional. If paired with file_path, it must belong to that file; the whole file is then analyzed.",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Optional repository-relative path. Include to analyze all indexed entities in the file.",
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["incoming", "outgoing", "both"],
                            "description": "incoming finds callers/dependents affected by a change.",
                        },
                        "hops": {"type": "integer", "minimum": 0, "maximum": 3},
                        "limit": {"type": "integer", "minimum": 10, "maximum": 80},
                    },
                },
            }
        )
        local_tools_def.append(
            {
                "name": "inspect_change_package",
                "description": (
                    "Build a bounded, read-only evidence package for preparing a code change. It combines "
                    "O-196's indexed impact graph with approved code/document links, linked Jira records, "
                    "statically related test/spec entities, relationship paths with source lines, and "
                    "CODEOWNERS candidates when available. It labels keyword classifications and gaps; "
                    "unknown tests or owners are not evidence of absence or complete coverage. Use this "
                    "when the user asks what rules, documentation, earlier issues, tests, or people should "
                    "be checked before changing an indexed entity or file. It can also derive the target files from two Git revisions; use base_ref and head_ref together, plus source_id if the project has multiple Git sources."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Optional. Entity ID returned by get_repo_entities.",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Optional exact repository-relative indexed file path.",
                        },
                        "source_id": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Git source ID; needed for a diff when several Git sources exist.",
                        },
                        "base_ref": {
                            "type": "string",
                            "description": "Git base revision; supply together with head_ref instead of entity_id/file_path.",
                        },
                        "head_ref": {
                            "type": "string",
                            "description": "Git target revision; supply together with base_ref instead of entity_id/file_path.",
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["incoming", "outgoing", "both"],
                            "description": "incoming finds callers and dependents affected by a change.",
                        },
                        "hops": {"type": "integer", "minimum": 0, "maximum": 3},
                        "limit": {"type": "integer", "minimum": 10, "maximum": 80},
                    },
                },
            }
        )
    return local_tools_def
