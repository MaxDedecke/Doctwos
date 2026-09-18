"""Static XSLT analysis for templates and transformation dependencies.

This module deliberately does not transform XML, read referenced files, or
resolve XPath at runtime.  It extracts facts present in one stylesheet and
leaves cross-file/resource resolution to the normal graph pass.
"""

from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import PurePosixPath
from urllib.parse import urlparse

from core.model import Chunk, Entity, ParseDiagnostic, ParseResult, ParsedEdge
from code_parser import CodeParser


XSLT_NAMESPACES = {
    "http://www.w3.org/1999/XSL/Transform",
    "http://www.w3.org/1999/XSL/TransformAlias",
}
_DOCTYPE_RE = re.compile(r"<!DOCTYPE\b", re.IGNORECASE)
_XSL_PREFIX_RE = re.compile(r"xmlns(?::([A-Za-z_][\w.-]*))?\s*=\s*(['\"])(.*?)\2")
_DOCUMENT_CALL_RE = re.compile(r"\bdocument\s*\(\s*(['\"])(.*?)\1\s*\)")
_DOCUMENT_ANY_CALL_RE = re.compile(r"\bdocument\s*\(\s*([^)]*)\)")
_TAG_RE = re.compile(r"<\s*(?![!?/])([A-Za-z_][\w:.-]*)(?=[\s/>])")
_KNOWN_XSL_NAMES = {
    "apply-templates",
    "attribute-set",
    "call-template",
    "decimal-format",
    "document",
    "include",
    "import",
    "key",
    "namespace-alias",
    "output",
    "param",
    "preserve-space",
    "source-document",
    "strip-space",
    "template",
    "variable",
}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _namespace(tag: str) -> str | None:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else None


def _is_xsl(element: ET.Element, name: str | None = None) -> bool:
    if name is not None and _local_name(element.tag) != name:
        return False
    namespace = _namespace(element.tag)
    # Accept an unqualified instruction for useful diagnostics on legacy
    # stylesheets, but always retain the original namespace in metadata.
    return namespace in XSLT_NAMESPACES or (
        namespace is None and _local_name(element.tag) in _KNOWN_XSL_NAMES
    )


def _normalize_path(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).as_posix()


def _relative_resource(path: str, href: str) -> tuple[str | None, bool]:
    """Return a repository-relative resource path and whether it is external."""
    href = href.strip()
    parsed = urlparse(href)
    if not href or parsed.scheme or parsed.netloc or href.startswith("//"):
        return None, bool(href)
    # Attribute value templates and XPath expressions are intentionally not
    # evaluated.  The boolean keeps the caller on the dynamic/unresolved path.
    if any(token in href for token in ("{", "}", "$", "(")):
        return None, bool(href)
    base = PurePosixPath(_normalize_path(path)).parent.as_posix()
    target = posixpath.normpath(posixpath.join(base, href.split("#", 1)[0]))
    return target.lstrip("./") or ".", False


def _source_ranges(source: str, root: ET.Element) -> dict[int, tuple[int, int]]:
    """Best-effort physical ranges for parsed elements.

    ElementTree intentionally does not expose source locations.  The lexical
    walk below is only used for navigation metadata; parsing remains the source
    of truth.  Valid XML keeps start/end tags balanced, which makes this stable
    for namespaced XSLT as well.
    """
    elements = iter(root.iter())
    ranges: dict[int, tuple[int, int]] = {}
    stack: list[tuple[str, ET.Element, int]] = []
    next_element = next(elements, None)
    token_re = re.compile(r"<\s*(/?)\s*([A-Za-z_][\w:.-]*)(?=[\s/>])[^>]*>", re.S)
    for match in token_re.finditer(source):
        raw = match.group(0)
        if raw.startswith("<?") or raw.startswith("<!"):
            continue
        closing = bool(match.group(1))
        name = match.group(2)
        line = source.count("\n", 0, match.start()) + 1
        if closing:
            for index in range(len(stack) - 1, -1, -1):
                if stack[index][0] == name:
                    _, element, start_line = stack.pop(index)
                    ranges[id(element)] = (start_line, line)
                    break
            continue
        element = next_element
        next_element = next(elements, None)
        if element is None:
            continue
        if raw.rstrip().endswith("/>"):
            ranges[id(element)] = (line, line)
        else:
            stack.append((name, element, line))
    end_line = max(1, len(source.splitlines()))
    while stack:
        _, element, start_line = stack.pop()
        ranges[id(element)] = (start_line, end_line)
    return ranges


def _line_at(source: str, offset: int) -> int:
    return source.count("\n", 0, max(0, offset)) + 1


def _split_range(lines: list[str], start: int, end: int, limit: int = 1200) -> list[tuple[str, int, int]]:
    pieces: list[tuple[str, int, int]] = []
    start = max(1, start)
    end = min(len(lines), max(start, end))
    cursor = start - 1
    while cursor < end:
        first = cursor
        size = 0
        while cursor < end:
            candidate = len(lines[cursor]) + (1 if cursor > first else 0)
            if cursor > first and size + candidate > limit:
                break
            size += candidate
            cursor += 1
        pieces.append(("\n".join(lines[first:cursor]), first + 1, cursor))
    return pieces


def _fallback_chunks(source: str) -> list[Chunk]:
    return [
        Chunk(
            content=chunk["content"],
            start_line=chunk["start_line"],
            end_line=chunk["end_line"],
            meta={
                "language": "xslt",
                "symbol_type": "source",
                "fallback": True,
                **(chunk.get("meta") or {}),
            },
        )
        for chunk in CodeParser("xslt").chunk_file(source)
    ]


def _parse_failure(source: str, path: str, code: str, message: str, line: int = 1) -> ParseResult:
    return ParseResult(
        program_name=PurePosixPath(path).stem or "stylesheet",
        path=path,
        source_format="free",
        chunks=_fallback_chunks(source),
        diagnostics=[
            ParseDiagnostic(
                code=code,
                severity="error",
                phase="parser",
                message=message,
                line=line,
                column=0,
            )
        ],
    )


def _unique_qname(base: str, used: set[str]) -> str:
    if base not in used:
        used.add(base)
        return base
    suffix = 2
    while f"{base}#{suffix}" in used:
        suffix += 1
    result = f"{base}#{suffix}"
    used.add(result)
    return result


def _template_label(element: ET.Element, ordinal: int) -> tuple[str, str | None, str | None, str | None]:
    name = element.attrib.get("name")
    match = element.attrib.get("match")
    mode = element.attrib.get("mode")
    label = name or match or f"anonymous-{ordinal}"
    return label, name, match, mode if mode is not None else None


def _containing_template(
    element: ET.Element, parent_by_id: dict[int, ET.Element], template_entities: dict[int, Entity]
) -> Entity | None:
    current = parent_by_id.get(id(element))
    while current is not None:
        found = template_entities.get(id(current))
        if found is not None:
            return found
        current = parent_by_id.get(id(current))
    return None


def _xpath_edge(
    *,
    source: Entity,
    edge_type: str,
    dst_name: str,
    line: int,
    xpath: str | None,
    meta: dict,
    resolution: str = "unresolved",
    ) -> ParsedEdge:
    return ParsedEdge(
        type=edge_type,
        src_name=source.qualified_name or source.name,
        dst_name=dst_name,
        resolution=resolution,
        src_start_line=line,
        src_end_line=line,
        meta={"language": "xslt", "xpath": xpath, **meta},
    )


def _is_static_qname(value: str) -> bool:
    return bool(value) and not any(token in value for token in ("{", "}", "$", "(", ")"))


def parse_xslt_file(source: str, path: str, **_: object) -> ParseResult:
    """Extract XSLT 1/2/3 stylesheet facts without executing a transform."""
    normalized_path = _normalize_path(path)
    if _DOCTYPE_RE.search(source):
        match = _DOCTYPE_RE.search(source)
        return _parse_failure(
            source,
            path,
            "XSLT_EXTERNAL_DECLARATION_BLOCKED",
            "DOCTYPE/DTD-Deklarationen werden aus Sicherheitsgründen nicht verarbeitet.",
            _line_at(source, match.start() if match else 0),
        )
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        position = getattr(exc, "position", (1, 0))
        return _parse_failure(source, path, "XSLT_PARSE_ERROR", f"XSLT ist nicht gültig: {exc}", position[0])

    if _local_name(root.tag) not in {"stylesheet", "transform"} or (
        _namespace(root.tag) not in XSLT_NAMESPACES and _namespace(root.tag) is not None
    ):
        return _parse_failure(
            source,
            path,
            "XSLT_ROOT_NOT_RECOGNIZED",
            "Dokumentwurzel ist kein XSLT-Stylesheet (stylesheet/transform).",
        )

    ranges = _source_ranges(source, root)
    root_start, root_end = ranges.get(id(root), (1, max(1, len(source.splitlines()))))
    root_opening = _TAG_RE.search(source)
    root_end_offset = source.find(">", root_opening.start()) + 1 if root_opening else 0
    ns_map = {
        prefix or "": uri
        for prefix, _, uri in _XSL_PREFIX_RE.findall(source[:root_end_offset])
    }
    root_qname = normalized_path
    root_entity = Entity(
        type="xslt_stylesheet",
        name=PurePosixPath(path).name or normalized_path,
        start_line=root_start,
        end_line=root_end,
        qualified_name=root_qname,
        meta={
            "language": "xslt",
            "is_file_root": True,
            "version": root.attrib.get("version"),
            "namespace": _namespace(root.tag),
            "namespaces": ns_map,
            "import_precedence": 0,
        },
    )
    entities: list[Entity] = [root_entity]
    edges: list[ParsedEdge] = []
    used_qnames = {root_qname}
    parent_by_id: dict[int, ET.Element] = {}
    for parent in root.iter():
        for child in list(parent):
            parent_by_id[id(child)] = parent

    template_entities: dict[int, Entity] = {}
    templates_by_name: dict[str, list[Entity]] = defaultdict(list)
    templates_by_mode: dict[str, list[Entity]] = defaultdict(list)
    template_ordinal = 0

    for element in root.iter():
        local = _local_name(element.tag)
        if not _is_xsl(element):
            continue
        start_line, end_line = ranges.get(id(element), (root_start, root_end))
        container = _containing_template(element, parent_by_id, template_entities)
        if local == "template":
            template_ordinal += 1
            label, template_name, match, mode = _template_label(element, template_ordinal)
            qname = _unique_qname(f"{root_qname}::template:{label}", used_qnames)
            entity = Entity(
                type="xslt_template",
                name=label,
                start_line=start_line,
                end_line=end_line,
                parent_name=root_entity.name,
                qualified_name=qname,
                parent_qualified_name=root_qname,
                meta={
                    "language": "xslt",
                    "template_name": template_name,
                    "match": match,
                    "mode": mode or "#default",
                    "priority": element.attrib.get("priority"),
                    "import_precedence": 0,
                    "xpath": match,
                    "source_file_path": normalized_path,
                },
            )
            entities.append(entity)
            template_entities[id(element)] = entity
            if template_name:
                templates_by_name[template_name].append(entity)
            if match:
                templates_by_mode[mode or "#default"].append(entity)
            continue

        if local in {"param", "variable"}:
            name = element.attrib.get("name") or f"anonymous-{start_line}"
            kind = "xslt_parameter" if local == "param" else "xslt_variable"
            parent = container or root_entity
            qname = _unique_qname(f"{parent.qualified_name}::{local}:{name}", used_qnames)
            entities.append(
                Entity(
                    type=kind,
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    parent_name=parent.name,
                    qualified_name=qname,
                    parent_qualified_name=parent.qualified_name,
                    meta={
                        "language": "xslt",
                        "select": element.attrib.get("select"),
                        "xpath": element.attrib.get("select"),
                    },
                )
            )
            continue

        if container is None and local in {
            "output",
            "key",
            "strip-space",
            "preserve-space",
            "attribute-set",
            "decimal-format",
            "namespace-alias",
        }:
            label = element.attrib.get("name") or element.attrib.get("match") or local
            qname = _unique_qname(f"{root_qname}::section:{local}:{label}", used_qnames)
            entities.append(
                Entity(
                    type="xslt_section",
                    name=label,
                    start_line=start_line,
                    end_line=end_line,
                    parent_name=root_entity.name,
                    qualified_name=qname,
                    parent_qualified_name=root_qname,
                    meta={
                        "language": "xslt",
                        "section": local,
                        "attributes": dict(element.attrib),
                        "xpath": element.attrib.get("match") or element.attrib.get("use"),
                    },
                )
            )

    # Top-level module relationships.  Relative paths are normalized but not
    # read; URLs remain explicitly dynamic.
    imports = [element for element in list(root) if _is_xsl(element, "import")]
    for index, element in enumerate(imports):
        href = element.attrib.get("href", "")
        target, external = _relative_resource(path, href)
        line = ranges.get(id(element), (root_start, root_start))[0]
        meta = {
            "href": href,
            "target_file_path": target,
            "target_entity_type": "xslt_stylesheet",
            "import_precedence": len(imports) - index,
            "external": external,
            "source_file_path": normalized_path,
        }
        edges.append(
            _xpath_edge(
                source=root_entity,
                edge_type="IMPORTS",
                dst_name=target or href or "<dynamic>",
                line=line,
                xpath=None,
                meta=meta,
                resolution="dynamic" if external or not href else "unresolved",
            )
        )

    for element in [item for item in list(root) if _is_xsl(item, "include")]:
        href = element.attrib.get("href", "")
        target, external = _relative_resource(path, href)
        line = ranges.get(id(element), (root_start, root_start))[0]
        edges.append(
            _xpath_edge(
                source=root_entity,
                edge_type="INCLUDES",
                dst_name=target or href or "<dynamic>",
                line=line,
                xpath=None,
                meta={
                    "href": href,
                    "target_file_path": target,
                    "target_entity_type": "xslt_stylesheet",
                    "external": external,
                    "source_file_path": normalized_path,
                },
                resolution="dynamic" if external or not href else "unresolved",
            )
        )

    # Instruction-level relationships and XPath evidence.
    for element in root.iter():
        local = _local_name(element.tag)
        if not _is_xsl(element):
            continue
        source_entity = _containing_template(element, parent_by_id, template_entities) or root_entity
        start_line = ranges.get(id(element), (root_start, root_start))[0]
        if local == "call-template":
            name = element.attrib.get("name", "").strip()
            static_name = _is_static_qname(name)
            candidates = templates_by_name.get(name, []) if static_name else []
            target_qname = candidates[0].qualified_name if len(candidates) == 1 else None
            meta = {
                "template_name": name or None,
                "target_qualified_name": target_qname,
                "source_file_path": normalized_path,
                "resolution_reason": "named_template" if target_qname else (
                    "ambiguous_template" if len(candidates) > 1 else "dynamic_template_name"
                ),
            }
            edges.append(
                _xpath_edge(
                    source=source_entity,
                    edge_type="CALLS_TEMPLATE",
                    dst_name=name or "<dynamic>",
                    line=start_line,
                    xpath=None,
                    meta=meta,
                    resolution="resolved" if target_qname else (
                        "dynamic" if not static_name else "unresolved"
                    ),
                )
            )
        elif local == "apply-templates":
            select = element.attrib.get("select")
            mode = element.attrib.get("mode") or "#default"
            static_selection = not select or _is_static_qname(select.strip()) or \
                (select and not any(token in select for token in ("$", "{", "}", "(", ")")))
            static_mode = _is_static_qname(mode) or mode in {"#default", "#all", "#current"}
            candidates = templates_by_mode.get(mode, []) if static_mode and mode not in {"#all", "#current"} else []
            normalized_select = (select or "").strip()
            exact = [
                candidate
                for candidate in candidates
                if candidate.meta.get("match")
                and (
                    candidate.meta["match"] == normalized_select
                    or candidate.meta["match"] == normalized_select.lstrip("./")
                    or candidate.meta["match"] == normalized_select.rsplit("/", 1)[-1]
                    )
                ]
            target_qname = (
                exact[0].qualified_name if len(exact) == 1
                else candidates[0].qualified_name if not normalized_select and len(candidates) == 1
                else None
            )
            candidates_qnames = [candidate.qualified_name for candidate in candidates]
            reason = (
                "exact_match" if len(exact) == 1 else
                "single_mode_match" if target_qname else
                "ambiguous_match" if len(exact) > 1 or len(candidates) > 1 else
                "dynamic_selection"
            )
            edges.append(
                _xpath_edge(
                    source=source_entity,
                    edge_type="APPLIES_TEMPLATES",
                    dst_name=target_qname or f"mode:{mode}",
                    line=start_line,
                    xpath=select,
                    meta={
                        "select": select,
                        "mode": mode,
                        "candidate_qualified_names": candidates_qnames,
                        "target_qualified_name": target_qname,
                        "source_file_path": normalized_path,
                        "resolution_reason": reason,
                    },
                    resolution=(
                        "resolved" if target_qname
                        else "dynamic" if not static_selection or not static_mode
                        else "unresolved"
                    ),
                )
            )
        elif local in {"source-document", "document"} and element.attrib.get("href"):
            href = element.attrib["href"]
            target, external = _relative_resource(path, href)
            edges.append(
                _xpath_edge(
                    source=source_entity,
                    edge_type="READS_XML",
                    dst_name=target or href,
                    line=start_line,
                    xpath=element.attrib.get("select"),
                    meta={
                        "href": href,
                        "target_file_path": target,
                        "target_entity_type": "xml_document",
                        "external": external,
                        "source_file_path": normalized_path,
                    },
                    resolution="dynamic" if external else "unresolved",
                )
            )

    literal_document_spans: set[tuple[int, int]] = set()
    for match in _DOCUMENT_CALL_RE.finditer(source):
        href = match.group(2).strip()
        literal_document_spans.add(match.span())
        target, external = _relative_resource(path, href)
        line = _line_at(source, match.start())
        source_entity = next(
            (
                entity
                for entity in template_entities.values()
                if entity.start_line <= line <= entity.end_line
            ),
            root_entity,
        )
        edges.append(
            _xpath_edge(
                source=source_entity,
                edge_type="READS_XML",
                dst_name=target or href,
                line=line,
                xpath=match.group(0),
                meta={
                    "href": href,
                    "target_file_path": target,
                    "target_entity_type": "xml_document",
                    "external": external,
                    "source_file_path": normalized_path,
                    "resolution_reason": "document_function",
                },
                resolution="dynamic" if external else "unresolved",
            )
        )

    # Preserve dynamic document($uri)/document(concat(...)) calls as explicit
    # dynamic relationships.  They must remain visible without being turned
    # into a guessed repository path.
    for match in _DOCUMENT_ANY_CALL_RE.finditer(source):
        if any(match.start() >= start and match.end() <= end for start, end in literal_document_spans):
            continue
        argument = match.group(1).strip()
        line = _line_at(source, match.start())
        source_entity = next(
            (
                entity
                for entity in template_entities.values()
                if entity.start_line <= line <= entity.end_line
            ),
            root_entity,
        )
        edges.append(
            _xpath_edge(
                source=source_entity,
                edge_type="READS_XML",
                dst_name="<dynamic>",
                line=line,
                xpath=match.group(0),
                meta={
                    "document_expression": argument,
                    "target_file_path": None,
                    "target_entity_type": "xml_document",
                    "external": False,
                    "source_file_path": normalized_path,
                    "resolution_reason": "dynamic_document_expression",
                },
                resolution="dynamic",
            )
        )
    template_ranges = [
        (entity.start_line, entity.end_line, entity)
        for entity in template_entities.values()
    ]
    lines = source.splitlines()
    covered: set[int] = set()
    chunks: list[Chunk] = []
    for start, end, entity in sorted(template_ranges):
        covered.update(range(start, min(end, len(lines)) + 1))
        for content, piece_start, piece_end in _split_range(lines, start, end):
            chunks.append(
                Chunk(
                    content=content,
                    start_line=piece_start,
                    end_line=piece_end,
                    meta={
                        "language": "xslt",
                        "symbol_type": "xslt_template",
                        "symbol_name": entity.name,
                        "symbol_qualified_name": entity.qualified_name,
                        "template_name": entity.meta.get("template_name"),
                        "match": entity.meta.get("match"),
                        "mode": entity.meta.get("mode"),
                        "xpath": entity.meta.get("xpath"),
                    },
                )
            )
    line = 1
    while line <= len(lines):
        if line in covered:
            line += 1
            continue
        start = line
        while line <= len(lines) and line not in covered:
            line += 1
        for content, piece_start, piece_end in _split_range(lines, start, line - 1):
            if content.strip():
                chunks.append(
                    Chunk(
                        content=content,
                        start_line=piece_start,
                        end_line=piece_end,
                        meta={"language": "xslt", "symbol_type": "context"},
                    )
                )
    if not chunks:
        chunks = _fallback_chunks(source)

    diagnostics: list[ParseDiagnostic] = []
    version = root.attrib.get("version")
    if version and version not in {"1.0", "2.0", "3.0"}:
        diagnostics.append(
            ParseDiagnostic(
                code="XSLT_VERSION_UNSUPPORTED",
                severity="warning",
                phase="parser",
                message=f"XSLT-Version {version} ist nicht im geprüften Umfang; Fakten werden konservativ erfasst.",
                line=root_start,
                column=0,
            )
        )

    return ParseResult(
        program_name=PurePosixPath(path).stem or "stylesheet",
        path=path,
        source_format="free",
        entities=entities,
        edges=edges,
        chunks=sorted(chunks, key=lambda chunk: (chunk.start_line, chunk.end_line)),
        diagnostics=diagnostics,
    )
