"""
parser/cobol/divisions.py
===========================
F-020: Programmstruktur aus dem Token-Strom erkennen — IDENTIFICATION/
ENVIRONMENT/DATA/PROCEDURE DIVISION, PROGRAM-ID, Sections (in DATA wie in
PROCEDURE DIVISION) und Paragraphen mit exakten Zeilenbereichen (F-023).

Läuft nach lexer.tokenize() (auf bereits embedded.mask()-maskierten Zeilen).
Ein einziger linearer Durchlauf, weil Division-/Section-/Paragraphenköpfe
strukturell identisch sind: ein Name in Area A, der als einziger Inhalt einer
eigenen Anweisung steht ("eigene Anweisung" = per Definition COBOL-Grammatik,
nicht per Spaltenposition — Free-Format hat keine Area A). Deshalb wird hier
nicht über Area A/B unterschieden (das wäre für Free-Format unbrauchbar),
sondern über "Satzanfang": ein Header darf nur direkt nach einem Punkt (oder
am Dateianfang) stehen, genau wie im echten COBOL-Grammatik.

Kein Abbruch (Plan §6.1 Regel 2): fehlt PROGRAM-ID oder jede Division, gibt
es einen möglichst vollständigen CobolProgram plus Einträge in der
zurückgegebenen Fehlerliste — nie eine Exception.
"""

from __future__ import annotations

from .lexer import Token
from .model import CobolProgram, Division, Paragraph, Section

_DIVISION_NAMES = {"IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE"}


def scan(tokens: list[Token]) -> tuple[CobolProgram, list[str]]:
    errors: list[str] = []

    if not tokens:
        errors.append("Keine Tokens gefunden - leere oder nicht lesbare Datei.")
        return CobolProgram(name="", start_line=0, end_line=0), errors

    start_line = tokens[0].phys_line
    n = len(tokens)

    divisions: list[Division] = []
    sections: list[Section] = []
    paragraphs: list[Paragraph] = []

    program_name = ""
    current_division_name: str | None = None

    open_division: list | None = None  # [name, start_line]
    open_section: list | None = None  # [name, division, start_line]
    open_paragraph: list | None = None  # [name, section, start_line]

    def close_paragraph(last_line: int) -> None:
        nonlocal open_paragraph
        if open_paragraph is not None:
            name, section, p_start = open_paragraph
            paragraphs.append(Paragraph(name, section, p_start, last_line))
            open_paragraph = None

    def close_section(last_line: int) -> None:
        nonlocal open_section
        close_paragraph(last_line)
        if open_section is not None:
            name, division, s_start = open_section
            sections.append(Section(name, division, s_start, last_line))
            open_section = None

    def close_division(last_line: int) -> None:
        nonlocal open_division
        close_section(last_line)
        if open_division is not None:
            name, d_start = open_division
            divisions.append(Division(name, d_start, last_line))
            open_division = None

    at_sentence_start = True
    i = 0
    while i < n:
        tok = tokens[i]

        if not at_sentence_start:
            at_sentence_start = tok.kind == "PERIOD"
            i += 1
            continue

        prev_line = tokens[i - 1].phys_line if i > 0 else tok.phys_line

        if (
            tok.kind == "WORD"
            and tok.value.upper() in _DIVISION_NAMES
            and _word_at(tokens, i + 1, "DIVISION")
        ):
            close_division(prev_line)
            current_division_name = tok.value.upper()
            open_division = [current_division_name, tok.phys_line]
            period_idx = _find_period(tokens, i + 2)
            i = period_idx + 1 if period_idx is not None else n
            at_sentence_start = True
            continue

        if tok.kind == "WORD" and tok.value.upper() == "PROGRAM-ID" and _is_period(tokens, i + 1):
            name_idx = i + 2
            if name_idx < n and tokens[name_idx].kind in ("WORD", "LITERAL"):
                program_name = _clean_name(tokens[name_idx].value)
            period_idx = _find_period(tokens, i + 2)
            i = period_idx + 1 if period_idx is not None else n
            at_sentence_start = True
            continue

        if tok.kind == "WORD" and not _is_embedded_placeholder(tok.value) and _word_at(tokens, i + 1, "SECTION"):
            close_section(prev_line)
            open_section = [tok.value, current_division_name, tok.phys_line]
            period_idx = _find_period(tokens, i + 2)
            i = period_idx + 1 if period_idx is not None else n
            at_sentence_start = True
            continue

        if (
            current_division_name == "PROCEDURE"
            and tok.kind == "WORD"
            and not _is_embedded_placeholder(tok.value)
            and _is_period(tokens, i + 1)
        ):
            close_paragraph(prev_line)
            section_name = open_section[0] if open_section else None
            open_paragraph = [tok.value, section_name, tok.phys_line]
            i += 2
            at_sentence_start = True
            continue

        at_sentence_start = tok.kind == "PERIOD"
        i += 1

    last_line = tokens[-1].phys_line
    close_division(last_line)

    if not divisions:
        errors.append("Keine Division erkannt (weder IDENTIFICATION/ENVIRONMENT/DATA/PROCEDURE DIVISION gefunden).")
    if not program_name:
        errors.append("PROGRAM-ID nicht gefunden.")

    program = CobolProgram(
        name=program_name,
        start_line=start_line,
        end_line=last_line,
        divisions=divisions,
        sections=sections,
        paragraphs=paragraphs,
    )
    return program, errors


def _word_at(tokens: list[Token], idx: int, word: str) -> bool:
    return idx < len(tokens) and tokens[idx].kind == "WORD" and tokens[idx].value.upper() == word


def _is_period(tokens: list[Token], idx: int) -> bool:
    return idx < len(tokens) and tokens[idx].kind == "PERIOD"


def _find_period(tokens: list[Token], start_idx: int) -> int | None:
    for j in range(start_idx, len(tokens)):
        if tokens[j].kind == "PERIOD":
            return j
    return None


def _is_embedded_placeholder(value: str) -> bool:
    """Ein `EMBEDDED-BLOCK-<DIALEKT>`-Platzhalter (embedded.mask()) besteht oft
    aus genau WORD+PERIOD (der Punkt nach END-EXEC) — strukturell nicht von
    einem Paragraphen-/Section-Kopf zu unterscheiden. Ohne diese Ausnahme
    würde z.B. ein EXEC-Block direkt unter einem Paragraphen-Header dessen
    Bereich sofort wieder schliessen (siehe 08_exec_cics.cbl)."""
    return value.upper().startswith("EMBEDDED-BLOCK-")


def _clean_name(value: str) -> str:
    if value[:1] in ("'", '"') and value[-1:] == value[:1]:
        return value[1:-1]
    return value
