"""
parser/cobol/copybook.py
===========================
F-022: `COPY name [OF|IN lib] [REPLACING operand BY operand …]` als
`ParsedEdge` (type="COPY").

Scannt den GESAMTEN Token-Strom, nicht auf eine Division beschränkt - COPY
ist ein Bibliotheksstatement, das laut COBOL-Grammatik überall auftauchen
darf (am häufigsten in der DATA DIVISION, aber z.B. auch in FILE-CONTROL
der ENVIRONMENT DIVISION oder in der PROCEDURE DIVISION). Läuft unabhängig
von divisions.py/data_division.py/procedure.py.

Plan §6.1 Regel 1 ist hier zentral: der Copybook-Inhalt wird NIE in den
Programmtext expandiert (sonst verschieben sich alle Zeilennummern). Es wird
nur die COPY-Kante gespeichert; das Copybook selbst wird später als eigene
Entity mit eigenen Zeilennummern separat geparst.

Auflösung nach docs/ENTSCHEIDUNGEN.md E-1/E-2: COPY ist global (scope=None),
gegen einen `CopybookIndex` (Name -> Liste von Pfaden, gebaut aus allen
*.cpy/*.copy-Dateien im Repo, Plan §6.4 Pass 0 - hier nur als Parameter
entgegengenommen, der Scan selbst ist Sache von parse.py). Genau ein Pfad
-> resolved. Mehrere Pfade sind nur über einen passenden OF/IN-Bibliotheks-
namen eindeutig aufzulösen (Verzeichnisname des Pfads), sonst unresolved -
kein Raten, dieselbe Regel wie bei REPLACING in E-2.

REPLACING-Paare landen roh in `meta["replacing"]` als Liste von
`{"from": ..., "to": ...}` - das Anwenden auf geerbte Feldnamen ist Sache der
XREF-Nachauflösung, sobald der quellenweite Feldindex existiert (E-2).
"""

from __future__ import annotations

import os
import re

from .lexer import Token
from .model import CobolProgram, ParsedEdge

class CopybookIndex(dict[str, list[str]]):
    """Namensindex plus die bereits in Pass 0 gelesenen Felddefinitionen.

    Ein normales ``dict`` bleibt als Eingabe erlaubt (Parser-API/Tests). Der
    Connector benutzt diese Unterklasse, damit parse_program() die Felder des
    eindeutig ausgewählten Copybooks erben kann, ohne dessen Text in das
    Programm zu expandieren.
    """

    def __init__(
        self,
        *args,
        fields_by_path: dict[str, list[dict]] | None = None,
        copy_edges_by_path: dict[str, list[ParsedEdge]] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.fields_by_path = fields_by_path or {}
        # Wird vom quellenweiten Pass 0 gefuellt. Die Kanten erlauben, Felder
        # aus verschachtelten Copybooks zu uebernehmen, ohne Copybook-Text in
        # den aufrufenden Quelltext einzublenden.
        self.copy_edges_by_path = copy_edges_by_path or {}

_OPERAND_KINDS = ("PSEUDO_TEXT", "LITERAL", "WORD")


def scan(
    program: CobolProgram, tokens: list[Token], index: CopybookIndex | None = None
) -> tuple[list[ParsedEdge], list[str]]:
    errors: list[str] = []
    edges: list[ParsedEdge] = []
    index = index or {}

    n = len(tokens)
    i = 0
    while i < n:
        tok = tokens[i]

        if tok.kind == "WORD" and tok.value.upper() == "COPY" and _word_or_literal_at(tokens, i + 1):
            name = _clean_name(tokens[i + 1].value)
            j = i + 2

            library = None
            if j < n and tokens[j].kind == "WORD" and tokens[j].value.upper() in ("OF", "IN"):
                if j + 1 < n and tokens[j + 1].kind in ("WORD", "LITERAL"):
                    library = _clean_name(tokens[j + 1].value)
                    j += 2

            replacing: list[dict] = []
            if j < n and tokens[j].kind == "WORD" and tokens[j].value.upper() == "REPLACING":
                j += 1
                while True:
                    pair, j = _replacing_pair(tokens, j)
                    if pair is None:
                        break
                    replacing.append(pair)

            end_idx = _find_period(tokens, j)
            end_line = tokens[end_idx].phys_line if end_idx is not None else tok.phys_line

            meta: dict = {}
            if library is not None:
                meta["library"] = library
            if replacing:
                meta["replacing"] = replacing

            edges.append(
                ParsedEdge(
                    type="COPY",
                    src_name=_src_name(program, tok.phys_line),
                    dst_name=name,
                    resolution=_resolve(name, library, index),
                    src_start_line=tok.phys_line,
                    src_end_line=end_line,
                    scope=None,
                    meta=meta,
                )
            )
            i = end_idx + 1 if end_idx is not None else n
            continue

        i += 1

    return edges, errors


# Dieselben Endungen wie connectors/git.py::_build_copybook_index verwendet,
# um den Index zu bauen (Name ohne Endung -> Pfade). Manche Bestände
# schreiben `COPY "NAME.cpy".` mit Endung im Literal statt der reinen
# Bibliotheksform `COPY NAME.` - ohne Normalisierung findet index.get() dann
# nie einen Treffer und COPY-Kanten (und darüber E-2s Feldvererbung, siehe
# auch tasks/edge_resolver.py::resolve_global_edges, das denselben Namen
# noch einmal DB-seitig gegen die Copybook-Entity abgleicht) bleiben für den
# gesamten Bestand unresolved.
_COPYBOOK_EXTENSIONS = (".cpy", ".copy")


def strip_copybook_extension(name: str) -> str:
    stem, ext = os.path.splitext(name)
    return stem if ext.lower() in _COPYBOOK_EXTENSIONS else name


def _resolve(name: str, library: str | None, index: CopybookIndex) -> str:
    return "resolved" if resolve_path(name, library, index) is not None else "unresolved"


def resolve_path(name: str, library: str | None, index: CopybookIndex) -> str | None:
    """Liefert nur bei eindeutiger COPY-Auflösung den konkreten Pfad."""
    paths = index.get(strip_copybook_extension(name).upper(), [])
    if not paths:
        return None
    if len(paths) == 1:
        return paths[0]
    if library is not None:
        matches = [p for p in paths if os.path.basename(os.path.dirname(p)).upper() == library.upper()]
        if len(matches) == 1:
            return matches[0]
    return None


def inherited_fields(copy_edges: list[ParsedEdge], index: CopybookIndex | None) -> list[dict]:
    """Projiziert Felder eindeutig aufgeloester COPY-Anweisungen in den
    aktuellen Namensraum.

    ``fields_by_path`` darf dabei bereits transitive Felder eines Copybooks
    enthalten. Das ist wichtig fuer ``COPY A`` wenn A seinerseits ``COPY B``
    enthaelt. ``path`` und ``qualified_name`` bleiben stets die des wirklich
    definierenden Copybooks, damit die spaetere DB-Aufloesung eindeutig bleibt.
    """
    if index is None or not hasattr(index, "fields_by_path"):
        return []

    inherited: list[dict] = []
    for edge in copy_edges:
        path = resolve_path(edge.dst_name, (edge.meta or {}).get("library"), index)
        if path is None:
            continue
        replacing = (edge.meta or {}).get("replacing", [])
        for field in index.fields_by_path.get(path, []):
            name = field.get("effective_name", field["name"])
            parent = field.get("effective_parent", field.get("parent") or "")
            inherited.append(
                {
                    **field,
                    "effective_name": apply_replacing(name, replacing),
                    "effective_parent": apply_replacing(parent, replacing) or None,
                }
            )
    return inherited


def apply_replacing(value: str, replacing: list[dict]) -> str:
    """Apply every COPY REPLACING pair case-insensitively."""
    result = value
    for pair in replacing:
        old = pair.get("from", "")
        if not old:
            continue
        new = pair.get("to", "")
        result = re.sub(re.escape(old), lambda _: new, result, flags=re.IGNORECASE)
    return result


def _replacing_pair(tokens: list[Token], j: int) -> tuple[dict | None, int]:
    """Ein `operand-1 BY operand-2`-Paar, oder (None, j unverändert), falls
    an Position j kein vollständiges Paar mehr beginnt - damit der Aufrufer
    (die REPLACING-Schleife) genau dort abbricht, wo `_find_period` danach
    weitersuchen muss."""

    start = j
    n = len(tokens)
    if j >= n or tokens[j].kind not in _OPERAND_KINDS:
        return None, start
    operand1 = _clean_operand(tokens[j].value)
    j += 1
    if j >= n or not (tokens[j].kind == "WORD" and tokens[j].value.upper() == "BY"):
        return None, start
    j += 1
    if j >= n or tokens[j].kind not in _OPERAND_KINDS:
        return None, start
    operand2 = _clean_operand(tokens[j].value)
    j += 1
    return {"from": operand1, "to": operand2}, j


def _src_name(program: CobolProgram, line: int) -> str:
    for p in program.paragraphs:
        if p.start_line <= line <= p.end_line:
            return p.name
    return program.name


def _word_or_literal_at(tokens: list[Token], idx: int) -> bool:
    return idx < len(tokens) and tokens[idx].kind in ("WORD", "LITERAL")


def _find_period(tokens: list[Token], start_idx: int) -> int | None:
    for j in range(start_idx, len(tokens)):
        if tokens[j].kind == "PERIOD":
            return j
    return None


def _clean_operand(value: str) -> str:
    if value.startswith("==") and value.endswith("=="):
        return value[2:-2].strip()
    return _clean_name(value)


def _clean_name(value: str) -> str:
    if value[:1] in ("'", '"') and value[-1:] == value[:1]:
        return value[1:-1]
    return value
