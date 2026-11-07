"""Erster, deterministischer Belegschritt des Chat-Agenten.

Ollamas OpenAI-kompatibler Endpunkt beachtet ``tool_choice=required`` nicht verlässlich. Der erste Werkzeugaufruf
steht deshalb vor der ersten Modellantwort fest: angeheftete Datei, in der Frage genannte Quelldateien oder Entitäten.
Nennt die Frage Dateien, begrenzt der zurückgegebene Dateifokus alle Repository-Werkzeuge dieses Durchgangs.
"""

import os
import re

from services import agent_repo_tools as repo_tools


def plan_bootstrap(
    prompt: str,
    *,
    repo_id: int | None,
    repo_available: bool,
    pinned_file: str | None,
    pinned_line: int | None,
    pinned_end_line: int | None,
) -> tuple[str, dict, set[str]]:
    """Werkzeug, Argumente und Dateifokus des ersten Schritts."""
    focus: set[str] = set()
    if pinned_file and repo_available:
        start_line = pinned_line or 1
        end_line = pinned_end_line
        if end_line is None:
            end_line = start_line + 30
            start_line = max(1, start_line - 15)
        bootstrap_args = {
            "file_path": pinned_file,
            "start_line": start_line,
            "end_line": end_line,
        }
        bootstrap_name = "view_repo_file"
    elif repo_available:
        # Prefer an exact source file named in the question over the
        # generic first-20-entities bootstrap.  This prevents a random
        # entity (e.g. PAUDBUNL) from answering a COPAUA0C question.
        question_text = prompt.rsplit("Question:", 1)[-1] if "Question:" in prompt else prompt
        explicit_files = re.findall(
            r"(?i)(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:java|cbl|CBL|cpy|xsl|xml|jcl|pom)",
            question_text,
        )
        # Also resolve the common symbol-only forms used by the eval
        # questions (`UserServiceImpl`, `COPAUA0C.MAIN-PARA`).
        explicit_files.extend(
            f"{name}.java" for name in re.findall(r"\b([A-Za-z][A-Za-z0-9]*Impl)\b", question_text)
        )
        explicit_files.extend(
            f"{name}.cbl"
            for name in re.findall(
                r"\b([A-Z][A-Z0-9]{3,})\.(?:MAIN-PARA|[A-Z0-9-]+)\b", question_text
            )
        )
        # COBOL questions often mention only the PROGRAM-ID. Resolve a
        # matching tracked source file before falling back to unrelated
        # first-page entities from the same project.
        explicit_files.extend(
            f"{name}.cbl" for name in re.findall(r"\b([A-Z][A-Z0-9]{5,})\b", question_text)
        )
        available_paths = repo_tools._repository_file_paths(repo_id)
        candidates: list[str] = []
        for requested in explicit_files:
            requested = requested.replace("\\", "/").lstrip("./").lower()
            basename = os.path.basename(requested)
            candidates.extend(
                [
                    path
                    for path in available_paths
                    if os.path.basename(path).lower() == basename
                    and ("/" not in requested or path.lower().endswith(requested))
                ][:40]
            )
        # Preserve prompt order and avoid duplicate paths.
        candidates = list(dict.fromkeys(candidates))
        if candidates:
            # This scope is enforced by every local repository tool for
            # the rest of the turn.  It is intentionally set before the
            # bootstrap call, so a model cannot replace an explicitly
            # named program with a semantically similar neighbour.
            focus.update(path.replace("\\", "/").lstrip("./").lower() for path in candidates)
            explicit_entity_names: list[str] = []
            for raw in re.findall(r"`([^`]+)`", question_text):
                value = raw.strip()
                if re.search(r"(?i)\.(?:java|cbl|cpy|xsl|xml|jcl|pom)$", value) or "/" in value:
                    continue
                # `Class.method` and `PROGRAM.PARAGRAPH` name both a
                # source file and a concrete index entity.  The entity
                # lookup below is exact and remains constrained to the
                # resolved paths, so duplicate simple names stay visible
                # rather than being selected by a generic bootstrap.
                explicit_entity_names.extend(
                    part
                    for part in value.split(".")
                    if re.fullmatch(r"[A-Za-z][A-Za-z0-9:_-]*", part)
                )
            for owner, member in re.findall(
                r"\b([A-Z][A-Z0-9]{3,}|[A-Za-z][A-Za-z0-9]*Impl)\.([A-Za-z][A-Za-z0-9-]*)\b",
                question_text,
            ):
                if member.lower() not in {"cbl", "java", "cpy", "xsl", "xml", "jcl"}:
                    explicit_entity_names.extend((owner, member))
            explicit_entity_names = list(dict.fromkeys(explicit_entity_names))
            # If the question contains a module/path hint, prefer the
            # candidate matching that hint; otherwise a unique basename is
            # safe and deterministic.
            hinted = [
                path
                for path in candidates
                if any(
                    part.lower() in path.lower() for part in ("core/rest-cxf", "app/", "flowable")
                )
            ]
            selected = (hinted or candidates)[0]
            if explicit_entity_names:
                bootstrap_args = {
                    "entity_names": explicit_entity_names,
                    "file_paths": candidates,
                    "limit": 40,
                }
                bootstrap_name = "get_repo_entities"
            else:
                # COBOL declarations and COPY statements commonly span
                # the DATA DIVISION before the first paragraph. Include
                # that bounded region in the initial evidence window.
                end_line = 300 if selected.lower().endswith(".cbl") else 150
                bootstrap_args = {"file_path": selected, "start_line": 1, "end_line": end_line}
                bootstrap_name = "view_repo_file"
        else:
            bootstrap_args = {"limit": 20}
            bootstrap_name = "get_repo_entities"
    else:
        # Unpinned project questions still need a grounded first step.
        # Keep the result small; the model can issue a more specific
        # get_repo_entities/search tool call afterwards if needed.
        bootstrap_args = {"limit": 20}
        bootstrap_name = "get_repo_entities"
    return bootstrap_name, bootstrap_args, focus
