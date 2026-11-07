"""CICS-BMS-Masken (Basic Mapping Support): Mapset, Masken und benannte Felder.

BMS ist Assembler-Makrosyntax: Name ab Spalte 1, dann das Makro (``DFHMSD`` Mapset, ``DFHMDI`` Maske, ``DFHMDF``
Feld) und die Operanden bis zum ersten Leerzeichen außerhalb eines Literals. Ein Zeichen in Spalte 72 setzt die
Anweisung in Spalte 16 der Folgezeile fort, auch mitten in einem Literal. Unbenannte Felder sind feste Bildschirmtexte;
ihr Text wird dem benannten Feld rechts daneben in derselben Zeile als ``label`` mitgegeben.

COBOL-Programme verweisen mit ``EXEC CICS SEND/RECEIVE MAP(...) MAPSET(...)`` auf eine Maske (``USES_MAP``, aufgelöst
in ``tasks/cics_resolver.py``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from code_parser import CodeParser
from core.model import Chunk, Entity, ParseResult

_CONTINUATION_COLUMN = 71
_CONTINUATION_START = 15
_MACROS = {"DFHMSD", "DFHMDI", "DFHMDF"}
_NUMBER = re.compile(r"^\d+$")


@dataclass
class _Statement:
    label: str
    macro: str
    operands: dict[str, object]
    start_line: int
    end_line: int


@dataclass
class _Map:
    statement: _Statement
    end_line: int
    fields: list[_Statement] = field(default_factory=list)


def parse_bms_file(source: str, path: str, **_: object) -> ParseResult:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    lines = source.splitlines()
    statements = list(_statements(lines))
    mapset = next((s for s in statements if s.macro == "DFHMSD" and s.label), None)
    mapset_name = mapset.label if mapset else PurePosixPath(normalized).stem.upper()
    file_end = max(1, len(lines))
    mapset_end = next(
        (
            s.end_line
            for s in statements
            if s.macro == "DFHMSD" and str(s.operands.get("TYPE", "")).upper() == "FINAL"
        ),
        file_end,
    )
    maps = _maps(statements, mapset_end)

    mapset_qname = f"{normalized}::{mapset_name}"
    entities = [
        Entity(
            type="bms_mapset",
            name=mapset_name,
            start_line=mapset.start_line if mapset else 1,
            end_line=mapset_end,
            qualified_name=mapset_qname,
            meta={
                "language": "bms",
                "is_file_root": True,
                **_pick(mapset.operands if mapset else {}, "MODE", "LANG", "CTRL", "STORAGE"),
            },
        )
    ]
    for screen in maps:
        map_qname = f"{mapset_qname}.{screen.statement.label}"
        entities.append(
            Entity(
                type="bms_map",
                name=screen.statement.label,
                start_line=screen.statement.start_line,
                end_line=screen.end_line,
                parent_name=mapset_name,
                parent_qualified_name=mapset_qname,
                qualified_name=map_qname,
                meta={
                    "language": "bms",
                    "mapset": mapset_name,
                    "texts": [
                        {"pos": f.operands.get("POS"), "text": f.operands["INITIAL"]}
                        for f in screen.fields
                        if not f.label and "INITIAL" in f.operands
                    ],
                    **_pick(screen.statement.operands, "SIZE", "LINE", "COLUMN", "CTRL"),
                },
            )
        )
        seen: set[str] = set()
        for statement in screen.fields:
            if not statement.label or statement.label in seen:
                continue
            seen.add(statement.label)
            label = _label_of(statement, screen.fields)
            entities.append(
                Entity(
                    type="bms_field",
                    name=statement.label,
                    start_line=statement.start_line,
                    end_line=statement.end_line,
                    parent_name=screen.statement.label,
                    parent_qualified_name=map_qname,
                    qualified_name=f"{map_qname}.{statement.label}",
                    meta={
                        "language": "bms",
                        "mapset": mapset_name,
                        "map": screen.statement.label,
                        **({"label": label} if label else {}),
                        **_pick(
                            statement.operands,
                            "POS",
                            "LENGTH",
                            "ATTRB",
                            "INITIAL",
                            "COLOR",
                            "HILIGHT",
                            "PICIN",
                            "PICOUT",
                            "OCCURS",
                            "JUSTIFY",
                        ),
                    },
                )
            )

    chunks = [
        Chunk(
            content=item["content"],
            start_line=item["start_line"],
            end_line=item["end_line"],
            meta={"language": "bms", "symbol_type": "source"},
        )
        for item in CodeParser("bms").chunk_file(
            source, boundary_lines=frozenset(m.statement.start_line for m in maps)
        )
    ]
    return ParseResult(
        program_name=mapset_name,
        path=path,
        source_format="fixed",
        entities=entities,
        edges=[],
        chunks=chunks,
        errors=[] if mapset else ["Kein DFHMSD-Mapset gefunden."],
    )


def _maps(statements: list[_Statement], mapset_end: int) -> list[_Map]:
    maps: list[_Map] = []
    for statement in statements:
        if statement.macro == "DFHMDI" and statement.label:
            if maps:
                maps[-1].end_line = statement.start_line - 1
            maps.append(_Map(statement, mapset_end))
        elif statement.macro == "DFHMDF" and maps:
            maps[-1].fields.append(statement)
        elif statement.macro == "DFHMSD" and maps and statement.start_line > maps[-1].end_line:
            break
    for screen in maps:
        last = max((f.end_line for f in screen.fields), default=screen.statement.end_line)
        screen.end_line = min(screen.end_line, last)
    return maps


def _label_of(statement: _Statement, fields: list[_Statement]) -> str | None:
    """Fester Text direkt links neben dem Feld in derselben Bildschirmzeile; liegt dazwischen ein anderes
    benanntes Feld, hat das Feld keine Beschriftung."""
    pos = statement.operands.get("POS")
    if not isinstance(pos, list) or len(pos) != 2:
        return None
    neighbor: _Statement | None = None
    for other in fields:
        other_pos = other.operands.get("POS")
        if not isinstance(other_pos, list) or len(other_pos) != 2:
            continue
        if other_pos[0] == pos[0] and other_pos[1] < pos[1]:
            if neighbor is None or other_pos[1] > neighbor.operands["POS"][1]:
                neighbor = other
    if neighbor is None or neighbor.label:
        return None
    text = str(neighbor.operands.get("INITIAL", "")).strip()
    return text or None


def _pick(operands: dict[str, object], *keys: str) -> dict[str, object]:
    return {key.lower(): operands[key] for key in keys if key in operands}


def _statements(lines: list[str]):
    index = 0
    while index < len(lines):
        line = lines[index].expandtabs()
        if not line.strip() or line.startswith("*") or line.startswith(".*"):
            index += 1
            continue
        start = index
        parts = [line]
        while _continues(lines[index].expandtabs()) and index + 1 < len(lines):
            index += 1
            parts.append(lines[index].expandtabs())
        statement = _statement(parts, start + 1, index + 1)
        if statement is not None:
            yield statement
        index += 1


def _continues(line: str) -> bool:
    return len(line) > _CONTINUATION_COLUMN and not line[_CONTINUATION_COLUMN].isspace()


def _statement(parts: list[str], start_line: int, end_line: int) -> _Statement | None:
    head = parts[0][:_CONTINUATION_COLUMN]
    label = ""
    if not head[:1].isspace():
        label, _, head = head.partition(" ")
    words = head.split(None, 1)
    if not words or words[0].upper() not in _MACROS:
        return None
    macro = words[0].upper()
    operand_text = _operand_text([words[1] if len(words) > 1 else "", *parts[1:]])
    return _Statement(label.upper(), macro, _operands(operand_text), start_line, end_line)


def _operand_text(parts: list[str]) -> str:
    """Operanden bis zum ersten Leerzeichen außerhalb eines Literals; Fortsetzungen ab Spalte 16."""
    text = ""
    in_quote = False
    for index, part in enumerate(parts):
        segment = part[:_CONTINUATION_COLUMN]
        if index > 0:
            segment = segment[_CONTINUATION_START:] if in_quote else segment.lstrip()
        elif not in_quote:
            segment = segment.lstrip()
        for char in segment:
            if char == "'":
                in_quote = not in_quote
            elif not in_quote and char.isspace():
                break
            text += char
    return text


def _operands(text: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in _split(text, ","):
        key, sep, value = item.partition("=")
        if not sep:
            continue
        result[key.strip().upper()] = _value(value.strip())
    return result


def _split(text: str, separator: str) -> list[str]:
    items, current, depth, in_quote = [], "", 0, False
    for char in text:
        if char == "'":
            in_quote = not in_quote
        elif not in_quote and char == "(":
            depth += 1
        elif not in_quote and char == ")":
            depth -= 1
        elif not in_quote and depth == 0 and char == separator:
            items.append(current)
            current = ""
            continue
        current += char
    if current:
        items.append(current)
    return items


def _value(raw: str) -> object:
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    if raw.startswith("(") and raw.endswith(")"):
        return [_value(part.strip()) for part in _split(raw[1:-1], ",")]
    if _NUMBER.match(raw):
        return int(raw)
    return raw.upper()
