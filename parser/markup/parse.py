"""Small, safe XML structure parser.

The XML parser is intentionally limited to the document root.  Its purpose is
not to model every XML vocabulary, but to give XSLT resource edges a concrete
target without loading external entities, DTDs, URLs, or executing anything.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath

from code_parser import CodeParser
from core.model import Chunk, Entity, ParseDiagnostic, ParseResult


_DOCTYPE_RE = re.compile(r"<!DOCTYPE\b", re.IGNORECASE)


def _line_for_parse_error(exc: ET.ParseError) -> tuple[int, int]:
    position = getattr(exc, "position", None)
    return position if position else (1, 0)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_xml_document(source: str, path: str, **_: object) -> ParseResult:
    """Parse an XML file without resolving external resources.

    XML vocabularies such as XSD and WSDL remain deliberately represented as a
    single document entity.  Dedicated vocabulary parsers can be added later
    without changing the registry contract.
    """

    normalized_path = PurePosixPath(path.replace("\\", "/")).as_posix()
    chunks = [
        Chunk(
            content=chunk["content"],
            start_line=chunk["start_line"],
            end_line=chunk["end_line"],
            meta={"language": "xml", "symbol_type": "source", **chunk.get("meta", {})},
        )
        for chunk in CodeParser("xml").chunk_file(source)
    ]

    if _DOCTYPE_RE.search(source):
        return ParseResult(
            program_name=PurePosixPath(path).stem or "xml",
            path=path,
            source_format="free",
            chunks=chunks,
            diagnostics=[
                ParseDiagnostic(
                    code="XML_EXTERNAL_DECLARATION_BLOCKED",
                    severity="error",
                    phase="parser",
                    message="DOCTYPE/DTD-Deklarationen werden aus Sicherheitsgründen nicht verarbeitet.",
                    line=source.count("\n", 0, _DOCTYPE_RE.search(source).start()) + 1,
                    column=0,
                )
            ],
        )

    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        line, column = _line_for_parse_error(exc)
        return ParseResult(
            program_name=PurePosixPath(path).stem or "xml",
            path=path,
            source_format="free",
            chunks=chunks,
            diagnostics=[
                ParseDiagnostic(
                    code="XML_PARSE_ERROR",
                    severity="error",
                    phase="parser",
                    message=f"XML ist nicht gültig: {exc}",
                    line=line,
                    column=column,
                )
            ],
        )

    root_match = re.search(r"<\s*(?![!?/])([A-Za-z_][\w:.-]*)(?=[\s/>])", source)
    root_offset = root_match.start() if root_match else 0
    root_line = source.count("\n", 0, root_offset) + 1
    name = _local_name(root.tag)
    entity = Entity(
        type="xml_document",
        name=name,
        start_line=root_line,
        end_line=max(1, len(source.splitlines())),
        qualified_name=normalized_path,
        meta={
            "language": "xml",
            "is_file_root": True,
            "root_element": name,
            "namespace": root.tag.split("}", 1)[0][1:] if root.tag.startswith("{") else None,
        },
    )
    return ParseResult(
        program_name=PurePosixPath(path).stem or name,
        path=path,
        source_format="free",
        entities=[entity],
        chunks=chunks,
    )
