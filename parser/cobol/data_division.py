"""
parser/cobol/data_division.py
================================
F-025: Level-Nummern (01-49/66/77/88), PIC, REDEFINES, OCCURS [DEPENDING ON],
VALUE sowie FD/SD → FileDescriptor aus der DATA DIVISION.

Läuft nach divisions.scan() — braucht dessen CobolProgram (für den Zeilenbereich
der DATA DIVISION sowie die darin liegenden Sections, um FD/SD-Zugehörigkeit
und Gruppenhierarchie beim Section-Wechsel zurückzusetzen) sowie denselben
Token-Strom noch einmal (nur der DATA-DIVISION-Ausschnitt wird durchsucht).

Gruppenhierarchie (parent) über einen einzigen Stack von (Level, Name):
ein neues Item mit Level L schließt alle Stack-Einträge mit Level >= L (das
sind seine Geschwister/entfernteren Vorfahren), sein Elternteil ist danach
der Stack-Top (oder die aktuelle FD/SD, wenn der Stack leer ist). Level 88
(Condition-Name) und 66 (RENAMES) werden nie auf den Stack gelegt — 88 hängt
sich an den zuletzt gesehenen Stack-Top (sein bedingtes Feld), 66 bleibt
laut COBOL-Grammatik ohnehin ohne Kinder. Level 77 setzt sich selbst als
Top-Level (parent=None), weil L=77 beim nächsten Item automatisch den
gesamten Stack schließt (jede reguläre Level-Nummer ist kleiner als 77).

Kein Abbruch (Plan §6.1 Regel 2): fehlt die DATA DIVISION, gibt es leere
Ergebnislisten plus einen Fehlereintrag, nie eine Exception.
"""

from __future__ import annotations

from .lexer import Token
from .model import CobolProgram, DataItem, FileDescriptor, Section

_CONDITION_LEVEL = 88
_RENAMES_LEVEL = 66
_STANDALONE_LEVEL = 77


def parse(program: CobolProgram, tokens: list[Token]) -> tuple[list[DataItem], list[FileDescriptor], list[str]]:
    errors: list[str] = []

    data_division = next((d for d in program.divisions if d.name == "DATA"), None)
    if data_division is None:
        errors.append("Keine DATA DIVISION gefunden - Datenfelder nicht durchsucht.")
        return [], [], errors

    dd_tokens = [t for t in tokens if data_division.start_line <= t.phys_line <= data_division.end_line]
    n = len(dd_tokens)
    data_sections = [s for s in program.sections if s.division == "DATA"]

    items: list[DataItem] = []
    file_descriptors: list[FileDescriptor] = []

    stack: list[tuple[int, str]] = []
    current_fd: str | None = None
    prev_section: Section | None = None

    at_sentence_start = True
    i = 0
    while i < n:
        tok = dd_tokens[i]

        if not at_sentence_start:
            at_sentence_start = tok.kind == "PERIOD"
            i += 1
            continue

        section = _section_at_line(data_sections, tok.phys_line)
        if section != prev_section:
            stack = []
            current_fd = None
            prev_section = section

        if tok.kind == "WORD" and tok.value.upper() in ("FD", "SD") and _word_at(dd_tokens, i + 1):
            name = dd_tokens[i + 1].value
            period_idx = _find_period(dd_tokens, i + 2)
            file_descriptors.append(
                FileDescriptor(
                    name=name,
                    start_line=tok.phys_line,
                    end_line=dd_tokens[period_idx].phys_line if period_idx is not None else tok.phys_line,
                )
            )
            current_fd = name
            stack = []
            i = period_idx + 1 if period_idx is not None else n
            at_sentence_start = True
            continue

        level = _level_number(tok)
        if level is not None and _word_at(dd_tokens, i + 1):
            name = dd_tokens[i + 1].value
            end_idx, clauses = _scan_clauses(dd_tokens, i + 2)

            if level == _CONDITION_LEVEL:
                parent = stack[-1][1] if stack else current_fd
            elif level in (_RENAMES_LEVEL, _STANDALONE_LEVEL):
                parent = None
            else:
                while stack and stack[-1][0] >= level:
                    stack.pop()
                parent = stack[-1][1] if stack else current_fd
                stack.append((level, name))

            end_line = dd_tokens[end_idx].phys_line if end_idx < n else dd_tokens[-1].phys_line
            items.append(
                DataItem(
                    name=name,
                    level=level,
                    start_line=tok.phys_line,
                    end_line=end_line,
                    parent=parent,
                    **clauses,
                )
            )
            i = end_idx + 1 if end_idx < n else n
            at_sentence_start = True
            continue

        at_sentence_start = tok.kind == "PERIOD"
        i += 1

    return items, file_descriptors, errors


def _scan_clauses(tokens: list[Token], start: int) -> tuple[int, dict]:
    """Durchsucht die Klauseln eines Datenitems bis zum abschließenden Punkt.

    Gibt den Index dieses Punkts (oder len(tokens), falls keiner mehr folgt)
    zurück, plus die eingesammelten Klauselwerte als kwargs für `DataItem`.
    """

    n = len(tokens)
    j = start
    picture: str | None = None
    redefines: str | None = None
    occurs: int | None = None
    occurs_depending_on: str | None = None
    value: str | None = None

    while j < n and tokens[j].kind != "PERIOD":
        tok = tokens[j]

        if tok.kind == "WORD" and tok.value.upper() in ("PIC", "PICTURE"):
            j += 1
            j = _skip_word(tokens, j, "IS")
            pic_start = j
            if pic_start < n:
                k = pic_start
                while (
                    k + 1 < n
                    and tokens[k + 1].kind != "PERIOD"
                    and _contiguous(tokens[k], tokens[k + 1])
                ):
                    k += 1
                picture = "".join(t.value for t in tokens[pic_start : k + 1])
                j = k + 1
            continue

        if tok.kind == "WORD" and tok.value.upper() == "REDEFINES":
            j += 1
            if j < n and tokens[j].kind == "WORD":
                redefines = tokens[j].value
                j += 1
            continue

        if tok.kind == "WORD" and tok.value.upper() == "OCCURS":
            j += 1
            if j < n and tokens[j].kind == "NUMBER":
                occurs = int(float(tokens[j].value))
                j += 1
            if j < n and tokens[j].kind == "WORD" and tokens[j].value.upper() == "TO":
                j += 1
                if j < n and tokens[j].kind == "NUMBER":
                    j += 1
            j = _skip_word(tokens, j, "TIMES")
            if j < n and tokens[j].kind == "WORD" and tokens[j].value.upper() == "DEPENDING":
                j += 1
                j = _skip_word(tokens, j, "ON")
                if j < n and tokens[j].kind == "WORD":
                    occurs_depending_on = tokens[j].value
                    j += 1
            continue

        if tok.kind == "WORD" and tok.value.upper() == "VALUE":
            j += 1
            j = _skip_word(tokens, j, "IS")
            if j < n and tokens[j].kind in ("LITERAL", "WORD", "NUMBER"):
                value = _clean_name(tokens[j].value)
                j += 1
            continue

        j += 1

    return j, {
        "picture": picture,
        "redefines": redefines,
        "occurs": occurs,
        "occurs_depending_on": occurs_depending_on,
        "value": value,
    }


def _level_number(tok: Token) -> int | None:
    if tok.kind != "NUMBER":
        return None
    try:
        level = int(tok.value)
    except ValueError:
        return None
    return level if 1 <= level <= 88 else None


def _section_at_line(sections: list[Section], line: int) -> Section | None:
    for s in sections:
        if s.start_line <= line <= s.end_line:
            return s
    return None


def _word_at(tokens: list[Token], idx: int) -> bool:
    return idx < len(tokens) and tokens[idx].kind == "WORD"


def _skip_word(tokens: list[Token], idx: int, word: str) -> int:
    if idx < len(tokens) and tokens[idx].kind == "WORD" and tokens[idx].value.upper() == word:
        return idx + 1
    return idx


def _find_period(tokens: list[Token], start_idx: int) -> int | None:
    for j in range(start_idx, len(tokens)):
        if tokens[j].kind == "PERIOD":
            return j
    return None


def _contiguous(a: Token, b: Token) -> bool:
    return a.phys_line == b.phys_line and b.col == a.col + len(a.value)


def _clean_name(value: str) -> str:
    if value[:1] in ("'", '"') and value[-1:] == value[:1]:
        return value[1:-1]
    return value
