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

    functions: list[tuple[str, int]] = []
    for line, text in _logical_lines(source):
        match = _FUNCTION.match(text)
        if match:
            functions.append((match.group(1), line))
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

    function_names: dict[str, int] = {}
    for index, (name, start) in enumerate(functions):
        end = functions[index + 1][1] - 1 if index + 1 < len(functions) else root.end_line
        # Shell permits a later definition to replace an earlier function.
        # Keep both source locations indexable; a repeated bare QName would
        # violate the per-file entity constraint and reject the whole file.
        occurrence = function_names.get(name, 0) + 1
        function_names[name] = occurrence
        suffix = "" if occurrence == 1 else f"#{occurrence}"
        entities.append(Entity(type="shell_function", name=name, start_line=start, end_line=max(start, end),
            parent_name=root.name, parent_qualified_name=normalized,
            qualified_name=f"{normalized}::function:{name}{suffix}",
            meta={"language": "shell"}))
    chunks = [Chunk(content=item["content"], start_line=item["start_line"], end_line=item["end_line"],
        meta={"language": "shell", "symbol_type": "source"}) for item in CodeParser("shell").chunk_file(source)]
    return ParseResult(program_name=PurePosixPath(path).stem or "script", path=path, source_format="free",
        entities=entities, edges=edges, chunks=chunks)
