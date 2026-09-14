"""
parser/cobol/antlr_bridge.py
==============================
E-11/Phase 3: Baut aus den bereits maskierten LogicalLines (Ausgabe von
embedded.mask(), F-034) einen ANTLR-Parse-Tree für divisions.py/
data_division.py. Ersetzt lexer.py NICHT — lexer.py bleibt für procedure.py/
copybook.py/xref.py aktiv, die weiterhin auf dem flachen Token-Strom arbeiten
(unverändert, siehe docs/ENTSCHEIDUNGEN.md E-11).

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
3. **Freitext-Paragraphen der IDENTIFICATION DIVISION.** `AUTHOR.`,
   `INSTALLATION.`, `DATE-WRITTEN.`, `DATE-COMPILED.`, `SECURITY.` und
   `REMARKS.` erwarten laut Grammatik ein `COMMENTENTRYLINE`-Token, das nur
   entsteht, wenn der Text mit einem `*>CE`-Tag vorpräpariert wurde (Cobol85.g4)
   — ein Preprocessing-Schritt, den dieser Grammatik-Port nicht implementiert.
   Ohne ihn bricht der Parser direkt hinter dem Paragraph-Kopf ab und die
   Fehlerkorrektur reißt den Rest der Datei (inkl. DATA/PROCEDURE DIVISION) mit
   — betraf praktisch jede Datei mit einer `AUTHOR.`-Zeile, bis auf keine
   Golden-Fixture zutreffend (F-033-Lücke, s. `12_identification_paragraphs.cbl`).
   Der Freitext wird daher komplett verworfen; nur der Paragraph-Kopf bleibt
   stehen (`commentEntry` ist in der Grammatik optional).

Bekannte Lücke (siehe Spike-README): COPY innerhalb ENVIRONMENT DIVISION
(FILE-CONTROL) bekommt denselben Filler-Platzhalter wie DATA DIVISION, ist
dort aber nicht zwingend grammatikalisch gültig — in den Fixtures nicht
getestet, kein Showstopper (ANTLRs Fehlerkorrektur behandelt das wie jeden
anderen unbekannten Rest).
"""

from __future__ import annotations

import dataclasses
import re

from antlr4 import CommonTokenStream, InputStream
from antlr4.atn.PredictionMode import PredictionMode
from antlr4.error.ErrorListener import ErrorListener

from ._antlr.Cobol85Lexer import Cobol85Lexer
from ._antlr.Cobol85Parser import Cobol85Parser
from .model import DiagnosticPhase, LogicalLine, ParseDiagnostic, Segment

# O-119: Anzahl DISTINKTER Diagnose-Einträge, die eine einzelne build_tree()-
# Rückgabe höchstens tragen darf ("Zahl/Textmenge begrenzen" aus der
# Abnahme) — ein pathologisch kaputtes Encoding kann sonst hunderte
# Token-Recognition-Fehler produzieren. Häufig IDENTISCHE Diagnosen (gleicher
# Code/Phase/Text, andere Zeile) zählen dabei schon vorher als EIN Eintrag
# (siehe `_bundle_repeats()`) — dieser Deckel greift erst bei tatsächlich
# unterschiedlichen Diagnosen.
_MAX_DIAGNOSTICS = 50

_DIVISION_RE = re.compile(
    r"^(IDENTIFICATION|ENVIRONMENT|DATA|PROCEDURE)\s+DIVISION\b", re.IGNORECASE
)
_DATA_SECTION_RE = re.compile(
    r"^(WORKING-STORAGE|FILE|LINKAGE|LOCAL-STORAGE|SCREEN|REPORT|COMMUNICATION)\s+SECTION\b",
    re.IGNORECASE,
)
_COPY_START_RE = re.compile(r"^COPY\b", re.IGNORECASE)
_EMBEDDED_BLOCK_RE = re.compile(r"^EMBEDDED-BLOCK-", re.IGNORECASE)
# IDENTIFICATION-DIVISION-Paragraphen, deren Inhalt frei formulierter Text ist
# (z.B. "AUTHOR. GEMINI-CLI."). Die Grammatik akzeptiert diesen Text nur als
# eigenes COMMENTENTRYLINE-Lexer-Token, das per Konvention ein "*>CE"-Tag vor
# dem Text voraussetzt (siehe Cobol85.g4) — ein Preprocessing-Schritt, den
# dieser Grammatik-Port nie implementiert hat. Ohne ihn bricht ANTLRs Parser
# direkt nach dem Divisions-Header ab und die Fehlerkorrektur reißt den
# gesamten Rest der Datei (inkl. DATA/PROCEDURE DIVISION) mit sich — beobachtet
# an praktisch jeder Datei dieses Testprojekts, die eine AUTHOR-Zeile hat.
_IDENT_TEXT_PARAGRAPH_RE = re.compile(
    r"^(AUTHOR|INSTALLATION|DATE-WRITTEN|DATE-COMPILED|SECURITY|REMARKS)\b", re.IGNORECASE
)

COPY_PLACEHOLDER_NAME = "ANTLR-COPY-PLACEHOLDER"

# Cobol85Lexer.IDENTIFIER kennt nur [a-zA-Z0-9] (siehe grammar/Cobol85.g4) —
# deutsche Bezeichner mit Umlauten/ß (z.B. "200-BUCHUNGSPOSITIONEN-PRÜFEN")
# lösen pro Zeichen einen "token recognition error" aus; der Lexer überspringt
# das Zeichen stillschweigend, was den restlichen Tokenstrom der Zeile
# verschiebt und (beobachtet) zu doppelt erkannten Section-Namen und in Folge
# zu UniqueViolations beim Persistieren führt. lexer.py (der handgeschriebene
# Tokenizer für procedure.py/copybook.py/xref.py) hat dasselbe Problem nicht —
# er nutzt bewusst `\w` statt `[a-zA-Z0-9]` (siehe dessen WORD-Pattern).
# Ohne ANTLR-Toolchain in diesem Environment (kein Java/antlr4-Jar) ist eine
# Grammatik-Änderung nicht regenerierbar; stattdessen wird der Text nur für
# den Lexer 1:1-zeichenweise auf ASCII gefaltet (Position/Länge bleiben exakt
# gleich) — `original_span()` liefert anschließend die echte Schreibweise
# zurück, indem sie anhand der (durch die Faltung stabilen) Zeichen-Offsets
# eines Tokens in den ungefalteten Originaltext zurückgreift.
_UMLAUT_FOLD = str.maketrans(
    {
        "Ä": "A",
        "Ö": "O",
        "Ü": "U",
        "ä": "a",
        "ö": "o",
        "ü": "u",
        "ß": "s",
    }
)


def original_span(source_text: str, ctx) -> str:
    """Rekonstruiert die echte (nicht auf ASCII gefaltete) Schreibweise eines
    Parser-Tree-Knotens — für Namen, die `_UMLAUT_FOLD` verändert haben
    könnte. `ctx.start.start`/`ctx.stop.stop` sind absolute Zeichen-Offsets
    im an den Lexer übergebenen Input-Stream; da die Faltung Länge und
    Position jedes Zeichens erhält, sind dieselben Offsets im ungefalteten
    `source_text` (von `build_tree()` zurückgegeben) gültig."""
    if ctx is None:
        return ""
    return source_text[ctx.start.start : ctx.stop.stop + 1]


class _FlaggingErrorListener(ErrorListener):
    """Syntaxfehler brechen den Import nie ab (ANTLRs eigene Fehlerkorrektur/
    Resync läuft unverändert weiter, derselbe Grundsatz wie schon vor der
    Migration, als divisions.py/data_division.py unbekannte Tokens
    stillschweigend übersprangen) — landen aber seit O-119 strukturiert in
    `self.diagnostics` statt nur ein `had_error`-Flag zu setzen. Eine Instanz
    ist an genau eine Phase (Lexer ODER Parser) gebunden, damit
    `syntaxError()` `phase` nicht aus `recognizer` erraten muss. Ohne
    explizite Listener-Zuweisung würde ANTLRs Default-`ConsoleErrorListener`
    Lexer-Fehler weiterhin auf stderr drucken (beobachtet bei
    `scripts/regenerate_cobol_golden.py`, "token recognition error at: ...")."""

    def __init__(self, phase: DiagnosticPhase) -> None:
        self.phase = phase
        self.had_error = False
        self.diagnostics: list[ParseDiagnostic] = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):  # noqa: N802
        self.had_error = True
        code = "COBOL85_LEXER_ERROR" if self.phase == "lexer" else "COBOL85_PARSER_ERROR"
        self.diagnostics.append(
            ParseDiagnostic(
                code=code,
                severity="error",
                phase=self.phase,
                message=msg,
                line=line,
                column=column,
            )
        )


def _parse(
    ascii_text: str, prediction_mode
) -> tuple[Cobol85Parser.StartRuleContext, bool, list[ParseDiagnostic]]:
    """Ein Parse-Durchlauf in einem festen Prediction-Mode. Gibt zusätzlich
    zurück, ob dabei ein Syntaxfehler auftrat (Signal für `build_tree()`s
    Zwei-Phasen-Logik) sowie die dabei aufgetretenen Diagnosen (O-119) —
    ohne selbst zu entscheiden, ob diese Diagnosen am Ende zählen (das
    entscheidet `build_tree()`: nur der tatsächlich verwendete Durchlauf
    zählt, ein per LL(*) erfolgreich wiederholter SLL-Fehler nicht)."""
    lexer = Cobol85Lexer(InputStream(ascii_text))
    lexer.removeErrorListeners()
    lexer_listener = _FlaggingErrorListener("lexer")
    lexer.addErrorListener(lexer_listener)

    tokens = CommonTokenStream(lexer)
    parser = Cobol85Parser(tokens)
    parser._interp.predictionMode = prediction_mode
    parser.removeErrorListeners()
    parser_listener = _FlaggingErrorListener("parser")
    parser.addErrorListener(parser_listener)

    tree = parser.startRule()
    had_error = lexer_listener.had_error or parser_listener.had_error
    diagnostics = lexer_listener.diagnostics + parser_listener.diagnostics
    return tree, had_error, diagnostics


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
    current_data_section: str | None = None
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
            current_data_section = None
        else:
            m2 = _DATA_SECTION_RE.match(stripped) if current_division == "DATA" else None
            if m2:
                in_data_section = True
                current_data_section = m2.group(1).upper()

        if _EMBEDDED_BLOCK_RE.match(stripped):
            result.append(_placeholder(line, line, "CONTINUE"))
            i += 1
            continue

        if current_division == "IDENTIFICATION" and _IDENT_TEXT_PARAGRAPH_RE.match(stripped):
            keyword = _IDENT_TEXT_PARAGRAPH_RE.match(stripped).group(1).upper()
            j = i
            while not _ends_with_period(lines[j]) and j + 1 < n:
                j += 1
            # Der freie Text wird komplett verworfen (nicht ins Modell übernommen) —
            # nur der Paragraph-Kopf selbst ("AUTHOR.") bleibt stehen, was die
            # Grammatik ohne commentEntry-Token akzeptiert (siehe authorParagraph()
            # & Co. in Cobol85Parser.py: commentEntry ist optional).
            result.append(_placeholder(line, lines[j], keyword))
            i = j + 1
            continue

        if _COPY_START_RE.match(stripped):
            j = i
            while not _ends_with_period(lines[j]) and j + 1 < n:
                j += 1
            if current_division == "PROCEDURE":
                placeholder_text = "CONTINUE"
            elif current_division == "DATA" and current_data_section == "FILE":
                # FILE SECTION akzeptiert nur fileDescriptionEntry (FD ...), kein
                # bare-01-Datenfeld — ein COPY hier steht praktisch immer für einen
                # kompletten FD-Block aus dem Copybook (Record-Layout einer Datei).
                placeholder_text = f"FD {COPY_PLACEHOLDER_NAME}"
            elif current_division == "DATA" and in_data_section:
                placeholder_text = f"01 {COPY_PLACEHOLDER_NAME} PIC X"
            else:
                placeholder_text = None
            result.append(
                _placeholder(line, lines[j], placeholder_text)
                if placeholder_text
                else _blank(line, lines[j])
            )
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
    return LogicalLine(
        first.phys_start_line, last.phys_end_line, [], first.source_format, is_comment=True
    )


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
DISPLAY WS-ENTRY (WS-COUNT).
DISPLAY 'WARMUP'.
STOP RUN.
"""


def warmup() -> None:
    """Zahlt ANTLRs einmalige JIT-/ATN-Kosten für beide Prediction-Modes
    beim Worker-Start statt bei der ersten echten Datei (Spike-README,
    Abschnitt "Performance" — Pflicht-Auflage aus der Go-Empfehlung für
    Phase 3; ~0.2-1.3s, genau einmal pro Worker-Prozess — siehe worker.py::
    _warmup_antlr_cobol_parser, an `celery.signals.worker_process_init`
    gehängt). `_WARMUP_TEXT` deckt beide bekannten SLL-Problemfälle ab: das
    `OCCURS ... DEPENDING ON` in der DATA DIVISION (SLL entscheidet das
    richtig, aber teuer) und die Tabellen-Subscript-Referenz `WS-ENTRY
    (WS-COUNT)` in der PROCEDURE DIVISION (SLL entscheidet das FALSCH, siehe
    build_tree()) — damit ist der LL(*)-Fallback-Pfad beim ersten echten
    Treffer schon warm, nicht erst dort."""
    ascii_text = _WARMUP_TEXT.translate(_UMLAUT_FOLD)
    _parse(ascii_text, PredictionMode.SLL)
    _parse(ascii_text, PredictionMode.LL)


def build_tree(
    masked_lines: list[LogicalLine], header: str | None = None
) -> tuple[Cobol85Parser.StartRuleContext, str, list[ParseDiagnostic]]:
    """Baut den ANTLR-Parse-Tree aus den (embedded.mask()-maskierten)
    LogicalLines. `masked_lines` wird hier NICHT verändert — mask_for_grammar()
    arbeitet auf einer eigenen Kopie, der Aufrufer behält seine für
    lexer.tokenize() unveränderte Version.

    `header` (nur für Copybooks, siehe data_division.py): COBOL85s
    `startRule` verlangt zwingend eine IDENTIFICATION DIVISION — ein
    Copybook hat laut Grammatik keine (reine Datenbeschreibung, Prinzip 5).
    Der Header wird der ERSTEN nicht-leeren Zeile vorangestellt statt als
    eigene Zeile eingefügt, damit sich keine Zeilennummer verschiebt
    (CLAUDE.md „Zeilennummern sind heilig").

    Rückgabe ist `(tree, source_text, diagnostics)` statt nur `tree` —
    Aufrufer, die Namen per `ctx.getText()` aus dem Baum lesen, bekommen
    damit potenziell ASCII-gefaltete Umlaute zurück (siehe `_UMLAUT_FOLD`);
    `original_span()` braucht `source_text`, um die echte Schreibweise zu
    rekonstruieren. `diagnostics` (O-119) sind schon gebündelt/gedeckelt
    (siehe `_bundle_repeats()`), aber NICHT gegen einen zweiten build_tree()-
    Aufruf auf demselben Text dedupliziert — divisions.py und
    data_division.py bauen den Baum für dieselbe Datei zweimal (siehe deren
    Docstrings); das übernimmt `consolidate_diagnostics()` beim
    Zusammenführen in parse.py.

    Zwei-Phasen-Parsing (Standardmuster der ANTLR4-Referenz für "SLL für
    Tempo, LL(*) als Fallback"): SLL statt ANTLRs Default (Full-LL) ist auf
    dieser Grammatik ~15-40x schneller (Spike-README, Abschnitt
    "Performance" — Pflicht-Auflage aus der Go-Empfehlung), entscheidet aber
    manche mehrdeutigen Konstrukte ohne vollen Kontext falsch — beobachtet
    bei `identifier: qualifiedDataName | tableCall | ...` (Cobol85.g4):
    beide Alternativen beginnen gleich, unterscheiden sich nur durch eine
    optionale Subscript-Klammer `(index)` danach. Mit SLL erzwungen eskaliert
    ANTLR das NICHT automatisch (anders als bei anderen mehrdeutigen Stellen,
    siehe warmup()) — jede Tabellen-Subscript-Referenz in der PROCEDURE
    DIVISION (z.B. `MOVE X TO TABELLE (IDX)`) ließ den Parser ab dort
    kaskadierend falsche `procedureSection`-Knoten erzeugen (doppelte
    Section-Entities, UniqueViolation beim Persistieren). Erster Versuch
    bleibt SLL (schneller Normalfall, keine Kosten für unbetroffene
    Dateien); nur bei einem Fehler wird komplett neu mit LL(*) geparst."""
    grammar_lines = mask_for_grammar(masked_lines)
    text = _reconstruct_text(grammar_lines)
    if header:
        text = _prepend_header(text, header)

    ascii_text = text.translate(_UMLAUT_FOLD)
    tree, had_error, diagnostics = _parse(ascii_text, PredictionMode.SLL)
    if had_error:
        # Nur der LL(*)-Durchlauf zählt jetzt — ein SLL-Fehler, den LL(*)
        # anschließend sauber auflöst, darf laut O-119-Abnahme nicht als
        # endgültige Diagnose gemeldet werden.
        tree, _, diagnostics = _parse(ascii_text, PredictionMode.LL)
    return tree, text, _bundle_repeats(diagnostics)


def _bundle_repeats(diagnostics: list[ParseDiagnostic]) -> list[ParseDiagnostic]:
    """O-119-Abnahme "Wiederholungen bündeln": mehrere Diagnosen mit
    gleichem `(code, phase, message)` — typischerweise dieselbe Art
    Token-Recognition-Fehler an vielen Stellen einer kaputt kodierten Datei —
    werden zu einer einzigen zusammengefasst (`count`, erste Zeile/Spalte
    bleibt erhalten, weitere Fundstellen hängen lesbar an `message`).
    Erhält die Fundreihenfolge (erstes Auftreten entscheidet die Position)."""
    order: list[tuple[str, DiagnosticPhase, str]] = []
    groups: dict[tuple[str, DiagnosticPhase, str], list[ParseDiagnostic]] = {}
    for diag in diagnostics:
        key = (diag.code, diag.phase, diag.message)
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(diag)

    bundled: list[ParseDiagnostic] = []
    for key in order:
        occurrences = groups[key]
        first = occurrences[0]
        if len(occurrences) == 1:
            bundled.append(first)
            continue
        all_lines = sorted({d.line for d in occurrences})
        shown = ", ".join(str(n) for n in all_lines[:5])
        if len(all_lines) > 5:
            shown += ", ..."
        message = f"{first.message} (insgesamt {len(occurrences)}x, Zeilen: {shown})"
        bundled.append(dataclasses.replace(first, message=message, count=len(occurrences)))
    return bundled


def consolidate_diagnostics(*diagnostic_lists: list[ParseDiagnostic]) -> list[ParseDiagnostic]:
    """Führt Diagnosen mehrerer build_tree()-Aufrufe für DIESELBE Datei
    zusammen. parse.py::parse_program() ruft dies für divisions.py UND
    data_division.py auf (siehe deren Docstrings) — beide bauen aus
    demselben Text denselben Baum, liefern bei einem Syntaxfehler also
    identische Diagnosen ein zweites Mal; die werden hier dedupliziert statt
    doppelt in ParseResult.diagnostics zu landen.

    Deckelt zusätzlich die GESAMTZAHL unterschiedlicher Diagnosen
    (O-119-Abnahme "Zahl ... begrenzen") — unabhängig vom inhaltlichen
    Bündeln gleicher Wiederholungen in `_bundle_repeats()`, das schon vorher
    pro build_tree()-Aufruf lief."""
    seen: set[tuple] = set()
    merged: list[ParseDiagnostic] = []
    for diagnostics in diagnostic_lists:
        for diag in diagnostics:
            key = (diag.code, diag.phase, diag.message, diag.line, diag.column, diag.count)
            if key in seen:
                continue
            seen.add(key)
            merged.append(diag)

    if len(merged) <= _MAX_DIAGNOSTICS:
        return merged

    truncated = merged[: _MAX_DIAGNOSTICS - 1]
    omitted = len(merged) - len(truncated)
    truncated.append(
        ParseDiagnostic(
            code="DIAGNOSTICS_TRUNCATED",
            severity="warning",
            phase="parser",  # Meta-Diagnose ohne echte Phase, "parser" als Deckel-Konvention
            message=f"{omitted} weitere Diagnosen unterdrückt (Deckel {_MAX_DIAGNOSTICS}).",
            line=0,
            column=0,
        )
    )
    return truncated
