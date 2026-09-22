"""Conservative static structure analysis for POSIX-like shell scripts.

This is intentionally a lexer-sized parser.  It never expands variables,
evaluates substitutions, follows includes, or starts a command.  A construct
is emitted only if its target is literal in the source.
"""
from __future__ import annotations

import posixpath
import re
import shlex
from pathlib import PurePosixPath
from urllib.parse import urlparse

from code_parser import CodeParser
from core.model import Chunk, Entity, ParseResult, ParsedEdge

_FUNCTION = re.compile(r"^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\s*\))?\s*\{")
_INCLUDE = re.compile(r"^\s*(?:source|\.)\s+(.+?)\s*(?:#.*)?$")
_DYNAMIC = re.compile(r"[\$`]|\$\(")


def _relative(path: str, value: str) -> str | None:
    value = value.strip()
    parsed = urlparse(value)
    if not value or parsed.scheme or parsed.netloc or value.startswith("/") or _DYNAMIC.search(value):
        return None
    base = PurePosixPath(path.replace("\\", "/")).parent.as_posix()
    return posixpath.normpath(posixpath.join(base, value)).lstrip("./") or "."


def _logical_lines(source: str):
    """Yield (physical-start-line, text), preserving continuation evidence."""
    lines = source.splitlines()
    index = 0
    heredoc_end: str | None = None
    while index < len(lines):
        line_no, text = index + 1, lines[index]
        index += 1
        if heredoc_end is not None:
            if text.strip() == heredoc_end:
                heredoc_end = None
            continue
        marker = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)", text)
        if marker:
            heredoc_end = marker.group(1)
        while text.rstrip().endswith("\\") and index < len(lines):
            text = text.rstrip()[:-1] + " " + lines[index].lstrip()
            index += 1
        yield line_no, text


def _tokens(text: str) -> list[str] | None:
    try:
        return shlex.split(text, comments=True, posix=True)
    except ValueError:
        return None


def _function_spans(lines: list[tuple[int, str]], last_line: int) -> list[tuple[str, int, int]]:
    """Find conservative function spans without evaluating shell syntax."""
    functions: list[tuple[str, int, int]] = []
    for index, (line, text) in enumerate(lines):
        match = _FUNCTION.match(text)
        if not match:
            continue
        depth = text.count("{") - text.count("}")
        end = line
        follow = index + 1
        while depth > 0 and follow < len(lines):
            end, body = lines[follow]
            depth += body.count("{") - body.count("}")
            follow += 1
        functions.append((match.group(1), line, max(line, end if depth <= 0 else last_line)))
    return functions


def parse_shell_file(source: str, path: str, **_: object) -> ParseResult:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    root = Entity(type="shell_script", name=PurePosixPath(path).name or path, start_line=1,
        end_line=max(1, len(source.splitlines())), qualified_name=normalized,
        meta={"language": "shell", "is_file_root": True})
    entities = [root]
    edges: list[ParsedEdge] = []

    def add_edge(kind: str, value: str, line: int, *, target_type: str | None = None, **meta: object) -> None:
        target = _relative(path, value)
        edges.append(ParsedEdge(type=kind, src_name=normalized, dst_name=target or value or "<dynamic>",
            resolution="unresolved" if target else "dynamic", src_start_line=line, src_end_line=line,
            meta={"language": "shell", "target_file_path": target, "target_entity_type": target_type,
                  "source_file_path": normalized, **meta}))

    logical_lines = list(_logical_lines(source))
    functions = _function_spans(logical_lines, root.end_line)
    function_names: dict[str, int] = {}
    function_qnames: list[tuple[str, int, int, str]] = []
    for name, start, end in functions:
        # Shell permits a later definition to replace an earlier function.
        # Keep both source locations indexable; a repeated bare QName would
        # violate the per-file entity constraint and reject the whole file.
        occurrence = function_names.get(name, 0) + 1
        function_names[name] = occurrence
        suffix = "" if occurrence == 1 else f"#{occurrence}"
        qualified_name = f"{normalized}::function:{name}{suffix}"
        function_qnames.append((name, start, end, qualified_name))
        entities.append(Entity(type="shell_function", name=name, start_line=start, end_line=end,
            parent_name=root.name, parent_qualified_name=normalized,
            qualified_name=qualified_name, meta={"language": "shell"}))
        edges.append(ParsedEdge(type="DECLARES", src_name=normalized, dst_name=name,
            resolution="resolved", src_start_line=start, src_end_line=start,
            meta={"language": "shell", "target_qualified_name": qualified_name,
                  "source_file_path": normalized, "declaration_kind": "function"}))

    def source_for(line: int) -> str:
        active = [item for item in function_qnames if item[1] <= line <= item[2]]
        return active[-1][3] if active else normalized

    def add_local_call(command: str, line: int) -> bool:
        # A definition is callable only after its declaration has run.  This
        # is exact for normal sequential scripts and avoids linking a command
        # to a later, merely same-named function.
        candidates = [item for item in function_qnames if item[0] == command and item[1] <= line]
        if not candidates:
            return False
        target = candidates[-1]
        edges.append(ParsedEdge(type="CALLS", src_name=source_for(line), dst_name=command,
            resolution="resolved", src_start_line=line, src_end_line=line,
            meta={"language": "shell", "target_qualified_name": target[3],
                  "target_file_path": normalized, "source_file_path": normalized,
                  "resolution_scope": "local_function"}))
        return True

    for line, text in logical_lines:
        match = _FUNCTION.match(text)
        if match:
            # One-line functions are common in launch scripts. Analyse their
            # first literal command as well; braces are syntax, not command
            # arguments. Multiline bodies naturally arrive on later lines.
            text = text[match.end():].split(";", 1)[0].rstrip("}").strip()
            if not text:
                continue
        include = _INCLUDE.match(text)
        if include:
            tokens = _tokens(include.group(1))
            value = tokens[0] if tokens and len(tokens) == 1 else include.group(1).strip()
            add_edge("SOURCES", value, line, target_type="shell_script", include_syntax="source" if text.lstrip().startswith("source") else ".")
            continue
        tokens = _tokens(text)
        if not tokens:
            continue
        command = tokens[0]
        if add_local_call(command, line):
            continue
        if command in {"sh", "bash", "dash", "ksh", "zsh"} and len(tokens) >= 2:
            candidate = next((token for token in tokens[1:] if not token.startswith("-")), "")
            if candidate:
                add_edge("EXECUTES_SCRIPT", candidate, line, target_type="shell_script", interpreter=command)
        elif command in {"xsltproc", "saxon", "saxon9", "xalan"} and len(tokens) >= 2:
            candidate = next((token for token in tokens[1:] if not token.startswith("-")), "")
            if candidate:
                add_edge("TRANSFORMS_WITH", candidate, line, target_type="xslt_stylesheet", tool=command)
        elif command == "java":
            candidates = [token for token in tokens[1:] if not token.startswith("-")]
            if candidates:
                class_name = candidates[-1]
                if _DYNAMIC.search(class_name):
                    add_edge("STARTS_JAVA", class_name, line, java_class=class_name)
                else:
                    edges.append(ParsedEdge(type="STARTS_JAVA", src_name=normalized, dst_name=class_name,
                        resolution="unresolved", src_start_line=line, src_end_line=line,
                        meta={"language": "shell", "java_class": class_name, "target_qualified_name": class_name,
                              "source_file_path": normalized}))
        elif command.startswith("./") or command.endswith((".sh", ".bash", ".zsh")):
            add_edge("EXECUTES_SCRIPT", command, line, target_type="shell_script")

    chunks = [Chunk(content=item["content"], start_line=item["start_line"], end_line=item["end_line"],
        meta={"language": "shell", "symbol_type": "source"}) for item in CodeParser("shell").chunk_file(source)]
    return ParseResult(program_name=PurePosixPath(path).stem or "script", path=path, source_format="free",
        entities=entities, edges=edges, chunks=chunks)
