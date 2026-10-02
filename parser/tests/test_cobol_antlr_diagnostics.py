"""
O-119: strukturierte Lexer-/Parser-Diagnosen aus dem ANTLR-Bridge statt
verschluckter oder auf stderr gedruckter Syntaxfehler.
"""

import os

from cobol import antlr_bridge, divisions, embedded, source_format
from cobol.model import ParseDiagnostic
from cobol.parse import parse_program

FIXTURES = os.path.join(os.path.dirname(__file__), "cobol_corpus", "fixtures")


def _scan(text: str, fmt: str = "fixed"):
    lines = source_format.split_logical_lines(text, fmt)
    masked, _ = embedded.mask(lines)
    programs, errors, diagnostics = divisions.scan(masked)
    return programs[0], errors, diagnostics


def test_parser_syntax_error_is_reported_without_aborting_the_import():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. BADSTMT.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           FROBNICATE WIDGET.\n"
        "           STOP RUN.\n"
    )
    program, errors, diagnostics = _scan(text)

    # Kein Abbruch (Plan §6.1 Regel 2): die Struktur bleibt trotzdem nutzbar.
    assert program.name == "BADSTMT"
    assert errors == []

    assert len(diagnostics) == 1
    diag = diagnostics[0]
    assert diag.code == "COBOL85_PARSER_ERROR"
    assert diag.phase == "parser"
    assert diag.severity == "error"
    assert diag.line == 5  # physische Originalzeile, nicht der Grammatik-Text
    assert diag.count == 1
    assert "WIDGET" in diag.message


def test_lexer_token_recognition_error_is_reported_not_printed_to_stderr(capsys):
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. BADCHAR.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           DISPLAY # HELLO.\n"
        "           STOP RUN.\n"
    )
    program, errors, diagnostics = _scan(text)

    assert errors == []
    assert len(diagnostics) == 1
    diag = diagnostics[0]
    assert diag.code == "COBOL85_LEXER_ERROR"
    assert diag.phase == "lexer"
    assert diag.line == 5

    # Vor O-119 lief das über ANTLRs Default-ConsoleErrorListener auf stderr
    # (siehe scripts/regenerate_cobol_golden.py-Ausgabe vor diesem Fix) -
    # ohne eigenen Listener auf dem Lexer bliebe dieser Fehler unterdrückt-
    # aber-doppelt-sichtbar statt nur strukturiert zurückgegeben.
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""


def test_repeated_identical_diagnostics_are_bundled_with_a_count():
    with open(os.path.join(FIXTURES, "99_garbage.cbl")) as f:
        text = f.read()
    result = parse_program(text, "cobol_corpus/fixtures/99_garbage.cbl")

    hash_diag = next(d for d in result.diagnostics if "'#'" in d.message)
    assert hash_diag.count == 3
    assert "insgesamt 3x" in hash_diag.message

    # Fünf verschiedene Sonderzeichen + ein Parser-Fehler - keine Diagnose
    # taucht doppelt auf, obwohl divisions.py UND data_division.py je einmal
    # antlr_bridge.build_tree() auf derselben Datei aufrufen. Dazu kommt seit
    # O-121 immer die eine SOURCE_FORMAT_HEURISTIC-Notiz ohne Profil.
    antlr_diagnostics = [d for d in result.diagnostics if d.phase != "profile"]
    assert len(antlr_diagnostics) == 6
    assert len(result.diagnostics) == 7


def test_sll_only_error_resolved_by_ll_retry_is_not_double_counted():
    # Dieselbe Diagnose ("mismatched input 'WIDGET'") entstünde bei
    # doppelter Zählung (SLL-Versuch UND LL-Retry) mit count=2 statt 1 -
    # build_tree() verwirft die Diagnosen des verworfenen SLL-Versuchs
    # (O-119-Abnahme).
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. BADSTMT.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           FROBNICATE WIDGET.\n"
        "           STOP RUN.\n"
    )
    result = parse_program(text, "test/badstmt.cbl")
    parser_diagnostics = [d for d in result.diagnostics if d.phase == "parser"]
    assert len(parser_diagnostics) == 1
    assert parser_diagnostics[0].count == 1


def test_clean_program_without_profile_only_has_the_heuristic_note():
    with open(os.path.join(FIXTURES, "01_minimal.cbl")) as f:
        text = f.read()
    result = parse_program(text, "cobol_corpus/fixtures/01_minimal.cbl")

    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.code == "SOURCE_FORMAT_HEURISTIC"
    assert diag.phase == "profile"
    assert diag.severity == "info"


def _diag(message: str, line: int = 1, code: str = "COBOL85_LEXER_ERROR") -> ParseDiagnostic:
    return ParseDiagnostic(
        code=code, severity="error", phase="lexer", message=message, line=line, column=0
    )


def test_consolidate_diagnostics_dedupes_across_the_two_build_tree_calls():
    # divisions.py und data_division.py rufen build_tree() für dieselbe
    # Datei zweimal auf (siehe deren Docstrings) - bei einem Syntaxfehler
    # liefern beide Aufrufe denselben Diagnose-Eintrag.
    same = [_diag("mismatched input 'X'")]
    merged = antlr_bridge.consolidate_diagnostics(same, same)
    assert len(merged) == 1


def test_consolidate_diagnostics_caps_total_count():
    many_distinct = [_diag(f"error number {i}", line=i) for i in range(80)]
    merged = antlr_bridge.consolidate_diagnostics(many_distinct)

    assert len(merged) == antlr_bridge._MAX_DIAGNOSTICS
    last = merged[-1]
    assert last.code == "DIAGNOSTICS_TRUNCATED"
    assert last.severity == "warning"
    assert "31 weitere" in last.message


SEPARATOR_COMMAS = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. COMMAS.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-A                 PIC X(8).
       01  WS-B                 PIC X(8).
       01  WS-OUT               PIC X(40).
       PROCEDURE DIVISION.
       MAIN-PARA.
           STRING WS-A, WS-B, 'A,B' DELIMITED BY SIZE
                  INTO WS-OUT
           END-STRING.
           CALL "CEEDAYS" USING
                  WS-A,
                  WS-B;
                  WS-OUT
           END-CALL.
           STOP RUN.
"""


def test_separator_commas_and_semicolons_do_not_cause_syntax_errors():
    # O-374: `STRING A, B ...` und `CALL ... USING A, B,` (CardDemo CBACT04C,
    # CSUTLDTC, COACCT01, CODATE01). Kommas/Semikolon mit folgendem Leerraum sind
    # in COBOL Trenner; das Komma im Literal 'A,B' bleibt erhalten.
    program, errors, diagnostics = _scan(SEPARATOR_COMMAS)
    assert [d.message for d in diagnostics if d.severity == "error"] == []
    assert [p.name for p in program.paragraphs] == ["MAIN-PARA"]


def test_separator_blanking_keeps_literals_and_offsets():
    text = "STRING A, B 'X, Y' \"P; Q\",\n  C;\n"
    blanked = antlr_bridge._blank_separators(text)
    assert len(blanked) == len(text)
    assert blanked == "STRING A  B 'X, Y' \"P; Q\" \n  C \n"
