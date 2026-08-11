"""
parser/cobol/antlr_bridge.py
==============================
E-11/Phase 3: Baut aus den bereits maskierten LogicalLines (Ausgabe von
embedded.mask(), F-034) einen ANTLR-Parse-Tree für divisions.py/
data_division.py. Ersetzt lexer.py NICHT — lexer.py bleibt für procedure.py/
copybook.py/xref.py aktiv, die weiterhin auf dem flachen Token-Strom arbeiten
(unverändert, siehe parser/spikes/antlr_cobol/README.md Empfehlung).

Zwei Dinge muss die Hauptgrammatik (`_antlr/Cobol85Parser.py`) bekommen, die
sie laut Spike (Kernfrage 1-3) NICHT selbst kann:

1. **Spaltenbereinigter Text.** Die Grammatik hat keine Fixed-Format-Logik
   (Spalten 1-6/73+, Continuation über Spalte 7) — genau wie im Spike bleibt
   `source_format.py` vorgeschaltet; hier wird aus den LogicalLines reiner
   Code-Text ohne Spaltenrauschen rekonstruiert, mit Zeilennummern-Padding,
   damit Zeilennummern erhalten bleiben (CLAUDE.md „Zeilennummern sind
   heilig").
2. **Grammatik-sichere Platzhalter für COPY und EXEC-Blöcke.** Die
   Hauptgrammatik akzeptiert weder eine nicht-expandierte `COPY`-Zeile
   (Prinzip 5 verbietet Expansion) noch embedded.py's `EMBEDDED-BLOCK-*`-
   Platzhalter als Anweisung (Spike-Fund: sie erwartet für EXEC SQL/CICS ein
   Fremd-Precompiler-Tag-Format, nicht literale Syntax). Beide werden hier
   durch grammatikgültige No-Ops ersetzt — `CONTINUE.` in der PROCEDURE
   DIVISION (die einzige operandenlose Anweisung, die praktisch überall als
   Satz gültig ist), ein Filler-Datenfeld (`01 ANTLR-COPY-PLACEHOLDER PIC
   X.`) sonst. Der Platzhalter behält exakt den Zeilenbereich des Originals,
   damit umschließende Division/Section/Paragraph-Spannen (ctx.start/
   ctx.stop im Parse-Tree) nicht verkürzt werden. divisions.py/
   data_division.py filtern `ANTLR-COPY-PLACEHOLDER` explizit aus den
   Ergebnissen heraus — copybook.py findet die echte COPY-Anweisung
   weiterhin unverändert im normalen (nicht grammatik-maskierten)
   Token-Strom von lexer.py.

Bekannte Lücke (siehe Spike-README): COPY innerhalb ENVIRONMENT DIVISION
(FILE-CONTROL) bekommt denselben Filler-Platzhalter wie DATA DIVISION, ist
dort aber nicht zwingend grammatikalisch gültig — in den Fixtures nicht
getestet, kein Showstopper (ANTLRs Fehlerkorrektur behandelt das wie jeden
anderen unbekannten Rest).
"""

from __future__ import annotations

import re

from antlr4 import CommonTokenStream, InputStream
from antlr4.atn.PredictionMode import PredictionMode
from antlr4.error.ErrorListener import ErrorListener

from ._antlr.Cobol85Lexer import Cobol85Lexer
from ._antlr.Cobol85Parser import Cobol85Parser
from .model import LogicalLine, Segment

_DIVISION_RE = re.compile(r"^(IDENTIFICATION|ENVIRONMENT|DATA|PROCEDURE)\s+DIVISION\b", re.IGNORECASE)
_DATA_SECTION_RE = re.compile(
    r"^(WORKING-STORAGE|FILE|LINKAGE|LOCAL-STORAGE|SCREEN|REPORT|COMMUNICATION)\s+SECTION\b", re.IGNORECASE
)
_COPY_START_RE = re.compile(r"^COPY\b", re.IGNORECASE)
_EMBEDDED_BLOCK_RE = re.compile(r"^EMBEDDED-BLOCK-", re.IGNORECASE)

COPY_PLACEHOLDER_NAME = "ANTLR-COPY-PLACEHOLDER"


class _SilentErrorListener(ErrorListener):
    """Syntaxfehler werden bewusst verschluckt, nicht auf stderr ausgegeben
    oder in ParseResult.errors aufgenommen — dieselbe "kein Abbruch"-Haltung
    wie divisions.py/data_division.py sie schon vor der Migration hatten
    (unbekannte Tokens werden übersprungen, nie als Fehler gemeldet). ANTLRs
    eigene Fehlerkorrektur (Resync) sorgt dafür, dass der Rest des Baums
    trotzdem nutzbar bleibt."""

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):  # noqa: N802
        pass


def mask_for_grammar(lines: list[LogicalLine]) -> list[LogicalLine]:
    """Ersetzt COPY-Anweisungen und embedded.mask()-Platzhalter durch
    grammatikgültige No-Ops, ohne Zeilennummern zu verschieben.

    Ein Filler-Datenfeld (`01 ANTLR-COPY-PLACEHOLDER PIC X.`) ist nur
    innerhalb einer bereits eröffneten DATA-DIVISION-Section grammatikgültig
    — `dataDivisionSection*` erwartet zwingend eine FILE/WORKING-STORAGE/
    LINKAGE-SECTION-Kopfzeile, ein Item direkt unter `DATA DIVISION.` ohne
    Section lässt die Hauptgrammatik am gesamten Rest der Division scheitern
    (beobachtet: PROCEDURE DIVISION verschwand danach komplett aus dem
    Baum). Für COPY außerhalb einer bekannten sicheren Position (DATA
    DIVISION ohne offene Section, ENVIRONMENT DIVISION FILE-CONTROL, o.ä.)
    wird die Zeile deshalb komplett geleert statt mit einem Platzhalter
    versehen — kostet im schlimmsten Fall ein zu knapp berechnetes Section-/
    Division-Zeilenende in diesem seltenen Randfall, verhindert aber den
    kaskadierenden Totalausfall."""
    result: list[LogicalLine] = []
    current_division: str | None = None
    in_data_section = False
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        if line.is_comment:
            result.append(line)
            i += 1
            continue

        stripped = line.text.strip()
        m = _DIVISION_RE.match(stripped)
        if m:
            current_division = m.group(1).upper()
            in_data_section = False
        elif current_division == "DATA" and _DATA_SECTION_RE.match(stripped):
            in_data_section = True

        if _EMBEDDED_BLOCK_RE.match(stripped):
            result.append(_placeholder(line, line, "CONTINUE"))
            i += 1
            continue

        if _COPY_START_RE.match(stripped):
            j = i
            while not _ends_with_period(lines[j]) and j + 1 < n:
                j += 1
            if current_division == "PROCEDURE":
                placeholder_text = "CONTINUE"
            elif current_division == "DATA" and in_data_section:
                placeholder_text = f"01 {COPY_PLACEHOLDER_NAME} PIC X"
            else:
                placeholder_text = None
            result.append(_placeholder(line, lines[j], placeholder_text) if placeholder_text else _blank(line, lines[j]))
            i = j + 1
            continue

        result.append(line)
        i += 1

    return result


def _ends_with_period(line: LogicalLine) -> bool:
    # embedded.mask() lief bereits — ein "." in einer verbliebenen LogicalLine
    # ist hier immer echtes Satzende oder eine Dezimalstelle, nie SQL-Syntax
    # (siehe lexer.py-Modul-Docstring). Eine Dezimalstelle kommt in einer
    # COPY-Anweisung praktisch nie vor; die einfache Prüfung reicht.
    from . import lexer as lexer_mod

    return any(t.kind == "PERIOD" for t in lexer_mod.tokenize([line]))


def _placeholder(first: LogicalLine, last: LogicalLine, text: str) -> LogicalLine:
    start = first.phys_start_line
    end = last.phys_end_line
    return LogicalLine(start, end, [Segment(start, 0, f"{text}.")], first.source_format)


def _blank(first: LogicalLine, last: LogicalLine) -> LogicalLine:
    return LogicalLine(first.phys_start_line, last.phys_end_line, [], first.source_format, is_comment=True)


def _reconstruct_text(lines: list[LogicalLine]) -> str:
    """Eine LogicalLine mit Continuation (Spalte 7 = '-') spannt mehrere
    physische Zeilen (phys_start_line < phys_end_line), aber `.text` ist EIN
    zusammenhängender String. Ohne Blankzeilen-Padding für die "verschluckten"
    Folgezeilen verschieben sich alle Zeilennummern nach der ersten
    Continuation-Zeile der Datei — genau das darf laut CLAUDE.md
    ("Zeilennummern sind heilig") nie passieren."""
    out_lines: list[str] = []
    next_lineno = 1
    for ll in lines:
        while next_lineno < ll.phys_start_line:
            out_lines.append("")
            next_lineno += 1
        out_lines.append("" if ll.is_comment else ll.text)
        next_lineno += 1
        while next_lineno <= ll.phys_end_line:
            out_lines.append("")
            next_lineno += 1
    return "\n".join(out_lines)


def _prepend_header(text: str, header: str) -> str:
    lines = text.split("\n")
    for idx, line in enumerate(lines):
        if line.strip():
            lines[idx] = f"{header} {line}"
            return "\n".join(lines)
    return header


_WARMUP_TEXT = """\
IDENTIFICATION DIVISION.
PROGRAM-ID. ANTLR-WARMUP.
DATA DIVISION.
WORKING-STORAGE SECTION.
01 WS-COUNT PIC 9(3) VALUE 0.
01 WS-TABLE.
05 WS-ENTRY PIC X(10) OCCURS 1 TO 50 TIMES DEPENDING ON WS-COUNT.
PROCEDURE DIVISION.
MAIN-PARA.
DISPLAY 'WARMUP'.
STOP RUN.
"""


def warmup() -> None:
    """Zahlt ANTLRs einmaligen Full-Context-Fallback beim Worker-Start statt
    bei der ersten echten Datei (Spike-README, Abschnitt "Performance" —
    Pflicht-Auflage aus der Go-Empfehlung für Phase 3). ANTLRs adaptive
    LL(*)-Prediction eskaliert bei mehrdeutigen Konstrukten (beobachtet:
    `OCCURS ... DEPENDING ON`) einmalig von SLL auf vollen Kontext und cached
    die Entscheidung danach prozessweit auf ATN-Ebene (~0.2-1.3s Kosten,
    genau einmal pro Worker-Prozess — siehe worker.py::_warmup_antlr_cobol_parser,
    an `celery.signals.worker_process_init` gehängt)."""
    lexer = Cobol85Lexer(InputStream(_WARMUP_TEXT))
    tokens = CommonTokenStream(lexer)
    parser = Cobol85Parser(tokens)
    parser._interp.predictionMode = PredictionMode.SLL
    parser.removeErrorListeners()
    parser.addErrorListener(_SilentErrorListener())
    parser.startRule()


def build_tree(masked_lines: list[LogicalLine], header: str | None = None) -> Cobol85Parser.StartRuleContext:
    """Baut den ANTLR-Parse-Tree aus den (embedded.mask()-maskierten)
    LogicalLines. `masked_lines` wird hier NICHT verändert — mask_for_grammar()
    arbeitet auf einer eigenen Kopie, der Aufrufer behält seine für
    lexer.tokenize() unveränderte Version.

    `header` (nur für Copybooks, siehe data_division.py): COBOL85s
    `startRule` verlangt zwingend eine IDENTIFICATION DIVISION — ein
    Copybook hat laut Grammatik keine (reine Datenbeschreibung, Prinzip 5).
    Der Header wird der ERSTEN nicht-leeren Zeile vorangestellt statt als
    eigene Zeile eingefügt, damit sich keine Zeilennummer verschiebt
    (CLAUDE.md „Zeilennummern sind heilig")."""
    grammar_lines = mask_for_grammar(masked_lines)
    text = _reconstruct_text(grammar_lines)
    if header:
        text = _prepend_header(text, header)

    lexer = Cobol85Lexer(InputStream(text))
    tokens = CommonTokenStream(lexer)
    parser = Cobol85Parser(tokens)
    # SLL statt ANTLRs Default (Full-LL): ~15-40x schneller auf dieser
    # Grammatik, ohne das Fehlerverhalten zu ändern (Spike-README,
    # Abschnitt "Performance" — Pflicht-Auflage aus der Go-Empfehlung).
    parser._interp.predictionMode = PredictionMode.SLL
    parser.removeErrorListeners()
    parser.addErrorListener(_SilentErrorListener())
    return parser.startRule()
