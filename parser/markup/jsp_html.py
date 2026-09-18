"""Conservative, source-only JSP and HTML structure extraction.

JSP is deliberately not fed to the Java parser: directives and scriptlets are
recorded with their physical ranges, while HTML navigation is parsed as markup.
No referenced file is read and no embedded code is executed.
"""
from __future__ import annotations

import posixpath
import re
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import urlparse

from core.model import Chunk, Entity, ParseResult, ParsedEdge

_DIRECTIVE = re.compile(r"<%@\s*(?P<kind>include|taglib)\b(?P<body>.*?)%>", re.I | re.S)
_SCRIPTLET = re.compile(r"<%(?!@|--)(?P<body>.*?)%>", re.S)
_EL = re.compile(r"\$\{(?P<body>[^}\r\n]+)\}")
_ATTR = re.compile(r"\b(?P<name>[\w:-]+)\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)", re.S)


def _line(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _target(path: str, value: str) -> str | None:
    value = value.strip()
    parsed = urlparse(value)
    if not value or parsed.scheme or parsed.netloc or value.startswith(("#", "//")) or any(x in value for x in ("${", "<%", "{", "}")):
        return None
    base = PurePosixPath(path.replace("\\", "/")).parent.as_posix()
    # JSP include paths beginning with / are application-root relative; retain
    # that literal relationship as a repository path for the static resolver.
    candidate = value.split("?", 1)[0].split("#", 1)[0]
    if candidate.startswith("/"):
        return posixpath.normpath(candidate).lstrip("/") or "."
    return posixpath.normpath(posixpath.join(base, candidate)).lstrip("./") or "."


class _HTMLFacts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.facts: list[tuple[str, dict[str, str], int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.facts.append((tag.lower(), {k.lower(): v or "" for k, v in attrs}, self.getpos()[0]))

    handle_startendtag = handle_starttag


def parse_jsp_or_html(source: str, path: str, **_: object) -> ParseResult:
    language = "jsp" if PurePosixPath(path).suffix.lower() in {".jsp", ".jspx", ".jspf", ".tag", ".tagx"} else "html"
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    root = Entity(
        type="jsp_page" if language == "jsp" else "html_document", name=PurePosixPath(path).name,
        start_line=1, end_line=max(1, len(source.splitlines())), qualified_name=normalized,
        meta={"language": language, "is_file_root": True},
    )
    entities = [root]
    edges: list[ParsedEdge] = []
    chunks = [Chunk(content=source, start_line=1, end_line=max(1, len(source.splitlines())), meta={"language": language, "symbol_type": "source"})]

    def edge(kind: str, destination: str, line: int, *, target_file: str | None, extra: dict | None = None) -> None:
        static = target_file is not None
        edges.append(ParsedEdge(type=kind, src_name=normalized, dst_name=destination or "<dynamic>",
            resolution="unresolved" if static else "dynamic", src_start_line=line, src_end_line=line,
            meta={"language": language, "target_file_path": target_file, "target_entity_type": "jsp_page" if kind == "INCLUDES" else None, **(extra or {})}))

    if language == "jsp":
        for match in _DIRECTIVE.finditer(source):
            attrs = {m.group("name").lower(): m.group("value") for m in _ATTR.finditer(match.group("body"))}
            line = _line(source, match.start())
            if match.group("kind").lower() == "include":
                value = attrs.get("file", "")
                edge("INCLUDES", value, line, target_file=_target(path, value), extra={"include_kind": "directive", "file": value})
            else:
                uri, prefix = attrs.get("uri"), attrs.get("prefix")
                name = prefix or uri or "<unknown>"
                entities.append(Entity(type="jsp_taglib", name=name, start_line=line, end_line=line,
                    parent_name=root.name, parent_qualified_name=normalized, qualified_name=f"{normalized}::taglib:{name}:{line}",
                    meta={"language": "jsp", "uri": uri, "prefix": prefix}))
        for match in _SCRIPTLET.finditer(source):
            line, end = _line(source, match.start()), _line(source, match.end())
            entities.append(Entity(type="jsp_scriptlet", name=f"scriptlet-{line}", start_line=line, end_line=end,
                parent_name=root.name, parent_qualified_name=normalized, qualified_name=f"{normalized}::scriptlet:{line}", meta={"language": "jsp", "java_fragment": match.group("body").strip()}))
        for match in _EL.finditer(source):
            line = _line(source, match.start())
            entities.append(Entity(type="jsp_el_expression", name=match.group("body").strip(), start_line=line, end_line=line,
                parent_name=root.name, parent_qualified_name=normalized, qualified_name=f"{normalized}::el:{line}:{match.start()}", meta={"language": "jsp", "expression": match.group("body").strip()}))

    parser = _HTMLFacts()
    parser.feed(source)
    for tag, attrs, line in parser.facts:
        if tag == "jsp:include":
            value = attrs.get("page", "")
            edge("INCLUDES", value, line, target_file=_target(path, value), extra={"include_kind": "action", "page": value})
        elif tag == "form":
            value = attrs.get("action", "")
            entities.append(Entity(type="html_form", name=value or "<current-page>", start_line=line, end_line=line,
                parent_name=root.name, parent_qualified_name=normalized, qualified_name=f"{normalized}::form:{line}", meta={"language": language, "action": value or None, "method": attrs.get("method", "get").lower()}))
            edge("SUBMITS_TO", value or "<current-page>", line, target_file=None,
                extra={"http_method": attrs.get("method", "get").lower(), "server_path": value or None, "resolution_reason": "static_form_action" if value and "${" not in value else "dynamic_form_action"})
        else:
            attr = "href" if tag in {"a", "link"} else "src" if tag in {"script", "img", "iframe"} else None
            if attr and attrs.get(attr):
                value = attrs[attr]
                edge("LINKS_TO" if attr == "href" else "REFERENCES_RESOURCE", value, line, target_file=_target(path, value), extra={"tag": tag, "attribute": attr})
    return ParseResult(program_name=PurePosixPath(path).stem or "page", path=path, source_format="free", entities=entities, edges=edges, chunks=chunks)
