"""
parser/cobol/embedded.py
=========================
F-034: EXEC <dialect> … END-EXEC als atomarer Block erkennen und maskieren.

Läuft vor dem Lexer — sonst zerlegt ein Punkt im eingebetteten SQL/CICS-Text
die Paragraphen (Plan §6.2). Ersetzt jeden erkannten Block durch eine einzige
Platzhalter-LogicalLine ohne Satzzeichen, damit divisions.py/procedure.py
(spätere AP-2-Schritte) nicht darüber stolpern. Der Originaltext bleibt im
zurückgegebenen EmbeddedBlock erhalten — sql.py (AP-2, F-027) wertet ihn aus.

Kein Abbruch bei fehlendem END-EXEC (CLAUDE.md „Zeilennummern sind heilig",
Plan §6.1 Regel 2): der Rest der Datei wird als Teil des Blocks behandelt,
statt eine Exception zu werfen.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import LogicalLine, Segment

_END_EXEC = "END-EXEC"


@dataclass
class EmbeddedBlock:
    dialect: str
    start_line: int
    end_line: int
    content: str


def mask(lines: list[LogicalLine]) -> tuple[list[LogicalLine], list[EmbeddedBlock]]:
    result: list[LogicalLine] = []
    blocks: list[EmbeddedBlock] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        if line.is_comment:
            result.append(line)
            i += 1
            continue

        words = line.text.split()
        if len(words) >= 2 and words[0].upper() == "EXEC":
            dialect = words[1].upper()
            block_lines = [line]
            j = i
            found_end = _contains_end_exec(line.text)
            while not found_end and j + 1 < n:
                j += 1
                nxt = lines[j]
                block_lines.append(nxt)
                if not nxt.is_comment and _contains_end_exec(nxt.text):
                    found_end = True

            code_lines = [bl for bl in block_lines if not bl.is_comment]
            content = "\n".join(bl.text for bl in code_lines)
            start_line = line.phys_start_line
            end_line = block_lines[-1].phys_end_line
            blocks.append(EmbeddedBlock(dialect, start_line, end_line, content))

            # Bindestrich statt Unterstrich: der Lexer kennt WORD-Zeichen nur
            # als Buchstaben/Ziffern/Bindestrich, ein '_' würde den Platzhalter
            # in mehrere Tokens zerlegen (u.a. wieder 'EXEC' als eigenes Wort).
            placeholder = LogicalLine(
                start_line,
                end_line,
                [Segment(start_line, 0, f"EMBEDDED-BLOCK-{dialect}")],
                line.source_format,
            )
            trailing = _text_after_end_exec(code_lines[-1].text) if code_lines else ""
            if trailing:
                placeholder.segments.append(Segment(end_line, 0, trailing))
            result.append(placeholder)
            i = j + 1
            continue

        result.append(line)
        i += 1

    return result, blocks


def _contains_end_exec(text: str) -> bool:
    return any(word.upper().rstrip(".") == _END_EXEC for word in text.split())


def _text_after_end_exec(text: str) -> str:
    upper = text.upper()
    idx = upper.rfind(_END_EXEC)
    if idx == -1:
        return ""
    return text[idx + len(_END_EXEC):].strip()
