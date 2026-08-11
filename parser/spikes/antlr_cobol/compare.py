#!/usr/bin/env python3
"""
parser/spikes/antlr_cobol/compare.py
=====================================
Spike-Werkzeug für Phase 1 (E-11, siehe docs/ENTSCHEIDUNGEN.md). Parst alle
Fixtures aus parser/tests/cobol_corpus/fixtures/*.cbl mit dem generierten
ANTLR-Parser (nackter Parse-Tree, kein Visitor) und protokolliert rein lesend:

- Parse-Erfolg/-Fehler je Fixture (Preprocessor-Grammatik und Hauptgrammatik
  getrennt, da COBOL85 zwei Stufen vorsieht)
- Anzahl Syntaxfehler
- Ob Token Line/Column tragen (Kernfrage 4)
- Ob COPY textuell expandiert wird (Kernfrage 2) — Sondertest unten
- Grobe Parse-Zeit

Explizit KEIN Abgleich gegen die Golden-JSONs (parser/tests/cobol_corpus/golden/)
— das wäre die falsche Messlatte, siehe Plan-Abschnitt "Golden Files sind
Verhaltensspezifikation, keine Bitgleichheits-Referenz".

Ausführen mit dem Spike-venv (nicht dem Projekt-venv!):
    parser/spikes/antlr_cobol/.venv-spike/bin/python parser/spikes/antlr_cobol/compare.py
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = SPIKE_DIR / "generated"
FIXTURES_DIR = SPIKE_DIR.parent.parent / "tests" / "cobol_corpus" / "fixtures"

sys.path.insert(0, str(GENERATED_DIR))
# parser/cobol/ selbst wird NICHT verändert, nur read-only als Vergleichsmaßstab
# importiert (Kernfrage 1: deckt die Grammatik das Preprocessing ab, oder
# bleibt source_format.py nötig?).
sys.path.insert(0, str(SPIKE_DIR.parent.parent.parent))

from antlr4 import CommonTokenStream, FileStream, InputStream  # noqa: E402
from antlr4.atn.PredictionMode import PredictionMode  # noqa: E402
from antlr4.error.ErrorListener import ErrorListener  # noqa: E402

from Cobol85Lexer import Cobol85Lexer  # noqa: E402
from Cobol85Parser import Cobol85Parser  # noqa: E402
from Cobol85PreprocessorLexer import Cobol85PreprocessorLexer  # noqa: E402
from Cobol85PreprocessorParser import Cobol85PreprocessorParser  # noqa: E402

from parser.cobol.parse import parse_program  # noqa: E402
from parser.cobol.source_format import detect_format, split_logical_lines  # noqa: E402


def _apply_sll(parser: Cobol85Parser) -> None:
    """ANTLRs Default-Prediction (Full-LL) ist auf dieser Grammatik ~15-40x
    langsamer als nötig (siehe `perf_check`, Kernfrage „Performance" in Phase
    2). SLL ist Standard-ANTLR-Praxis für Grammatiken ohne echten Bedarf an
    Full-LL-Ambiguitätsauflösung und ändert das Fehlerverhalten auf den
    Fixtures nachweislich nicht (siehe README, Performance-Abschnitt)."""
    parser._interp.predictionMode = PredictionMode.SLL


class CollectingErrorListener(ErrorListener):
    """Sammelt Syntaxfehler statt sie auf stderr zu drucken (Default-Verhalten
    von ANTLR) — wir wollen sie kontrolliert protokollieren, nicht verstecken."""

    def __init__(self) -> None:
        super().__init__()
        self.errors: list[str] = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):  # noqa: N802
        self.errors.append(f"line {line}:{column} {msg}")


@dataclass
class FixtureResult:
    name: str
    preprocessor_ok: bool
    preprocessor_errors: list[str]
    main_ok: bool
    main_errors: list[str]
    has_line_column: bool
    top_level_rule_hits: list[str] = field(default_factory=list)
    parse_seconds: float = 0.0


def _rule_names_touched(tree, parser, depth: int = 2) -> list[str]:
    """Sammelt die Regelnamen der obersten `depth` Ebenen des Parse-Trees —
    genug, um grob zu sehen, welche Grammatik-Pfade getroffen wurden, ohne den
    ganzen Baum zu dumpen."""
    names: list[str] = []

    def walk(node, level):
        if level > depth or not hasattr(node, "getRuleIndex"):
            return
        try:
            names.append(parser.ruleNames[node.getRuleIndex()])
        except Exception:
            return
        for i in range(getattr(node, "getChildCount", lambda: 0)()):
            child = node.getChild(i)
            walk(child, level + 1)

    walk(tree, 0)
    return names


def parse_fixture(path: Path) -> FixtureResult:
    start = time.monotonic()

    # Stufe 1: Preprocessor-Grammatik (COPY/REPLACE als Syntax, keine Expansion)
    pre_input = FileStream(str(path), encoding="utf-8")
    pre_lexer = Cobol85PreprocessorLexer(pre_input)
    pre_tokens = CommonTokenStream(pre_lexer)
    pre_parser = Cobol85PreprocessorParser(pre_tokens)
    pre_errors = CollectingErrorListener()
    pre_parser.removeErrorListeners()
    pre_parser.addErrorListener(pre_errors)
    pre_tree = pre_parser.startRule()
    preprocessor_ok = len(pre_errors.errors) == 0

    # Stufe 2: Hauptgrammatik direkt auf der Originaldatei (kein Preprocessor-
    # Output dazwischengeschaltet — Phase 1 prüft nur, ob die Hauptgrammatik
    # für sich genommen die Fixtures strukturell erkennt).
    main_input = FileStream(str(path), encoding="utf-8")
    main_lexer = Cobol85Lexer(main_input)
    main_tokens = CommonTokenStream(main_lexer)
    main_parser = Cobol85Parser(main_tokens)
    _apply_sll(main_parser)
    main_errors = CollectingErrorListener()
    main_parser.removeErrorListeners()
    main_parser.addErrorListener(main_errors)
    main_tree = main_parser.startRule()
    main_ok = len(main_errors.errors) == 0

    main_tokens.fill()
    has_line_column = any(
        getattr(t, "line", None) not in (None, 0) for t in main_tokens.tokens
    )

    elapsed = time.monotonic() - start

    return FixtureResult(
        name=path.name,
        preprocessor_ok=preprocessor_ok,
        preprocessor_errors=pre_errors.errors,
        main_ok=main_ok,
        main_errors=main_errors.errors,
        has_line_column=has_line_column,
        top_level_rule_hits=_rule_names_touched(main_tree, main_parser),
        parse_seconds=elapsed,
    )


def _reconstruct_via_source_format(path: Path) -> str:
    """Baut aus den LogicalLines von parser/cobol/source_format.py (F-021,
    read-only genutzt) reinen Code-Text ohne Spalten-/Sequenznummern-Rauschen
    — genau das Format, das die ANTLR-Hauptgrammatik offenbar erwartet
    (Kernfrage 1). Zeilennummern bleiben durch Padding grob erhalten, damit
    Fehlermeldungen noch auf die Originaldatei zeigen."""
    text = path.read_text(encoding="utf-8")
    fmt = detect_format(text)
    logical_lines = split_logical_lines(text, fmt)

    out_lines: list[str] = []
    next_lineno = 1
    for ll in logical_lines:
        while next_lineno < ll.phys_start_line:
            out_lines.append("")
            next_lineno += 1
        if not ll.is_comment:
            out_lines.append(ll.text)
        else:
            out_lines.append("")
        next_lineno = ll.phys_end_line + 1
    return "\n".join(out_lines)


def parse_reconstructed(path: Path) -> tuple[bool, list[str]]:
    text = _reconstruct_via_source_format(path)
    main_input = InputStream(text)
    main_lexer = Cobol85Lexer(main_input)
    main_tokens = CommonTokenStream(main_lexer)
    main_parser = Cobol85Parser(main_tokens)
    _apply_sll(main_parser)
    errors = CollectingErrorListener()
    main_parser.removeErrorListeners()
    main_parser.addErrorListener(errors)
    main_parser.startRule()
    return len(errors.errors) == 0, errors.errors


def perf_check() -> str:
    """Performance-Kriterium aus Phase 2: Parse-Zeit auf einer realistischen
    Beispieldatei, erzeugt über scripts/generate_synthetic_cobol_corpus.py
    (read-only importiert, erzeugt nichts auf der Festplatte). Vergleicht
    ANTLR (SLL) gegen den Altparser auf demselben, deterministisch erzeugten
    Programmtext."""
    import random
    import sys as _sys

    scripts_dir = str(SPIKE_DIR.parent.parent.parent / "scripts")
    if scripts_dir not in _sys.path:
        _sys.path.insert(0, scripts_dir)
    from generate_synthetic_cobol_corpus import generate_program  # noqa: PLC0415

    rng = random.Random(42)
    program_ids = [f"PGM{i:05d}" for i in range(30)]
    copybook_ids = [f"CPY{i:05d}" for i in range(10)]
    programs = [
        generate_program(rng, i, program_ids, copybook_ids) for i in range(len(program_ids))
    ]
    text = max(programs, key=lambda p: p.count("\n"))
    n_lines = text.count("\n")

    fmt = detect_format(text)
    logical_lines = split_logical_lines(text, fmt)
    recon = "\n".join(ll.text if not ll.is_comment else "" for ll in logical_lines)

    t0 = time.monotonic()
    lexer = Cobol85Lexer(InputStream(recon))
    tokens = CommonTokenStream(lexer)
    parser = Cobol85Parser(tokens)
    _apply_sll(parser)
    errors = CollectingErrorListener()
    parser.removeErrorListeners()
    parser.addErrorListener(errors)
    parser.startRule()
    antlr_seconds = time.monotonic() - t0

    t0 = time.monotonic()
    parse_program(text, "perf_check_synthetic.cbl")
    legacy_seconds = time.monotonic() - t0

    factor = antlr_seconds / legacy_seconds if legacy_seconds else float("inf")
    return (
        f"{n_lines} Zeilen synthetisches Programm: "
        f"ANTLR (SLL, source_format vorgeschaltet) {antlr_seconds:.3f}s "
        f"({len(errors.errors)} Syntaxfehler, erwartet wegen COPY/EXEC SQL) "
        f"vs. Altparser {legacy_seconds:.3f}s -> Faktor {factor:.1f}x"
    )


def check_copy_expansion() -> str:
    """Kernfrage 2: Expandiert die Preprocessor-Grammatik COPY textuell, oder
    bleibt COPY als eigener Baumknoten stehen? Wir parsen 04_copy_replacing.cbl
    (referenziert ein NICHT vorhandenes Copybook WSFIELDS) und prüfen, ob der
    Parse-Tree einen copyStatement-Knoten enthält, statt den Inhalt eines
    Copybooks zu erwarten. Läuft die Preprocessor-Grammatik OHNE Dateisystem-
    Zugriff auf ein Copybook-Verzeichnis durch, ist das der Beleg: sie
    expandiert nicht selbst, sondern überlässt das dem Aufrufer (hier: niemand
    — Prinzip 5 bleibt unberührt)."""
    fixture = FIXTURES_DIR / "04_copy_replacing.cbl"
    pre_input = FileStream(str(fixture), encoding="utf-8")
    pre_lexer = Cobol85PreprocessorLexer(pre_input)
    pre_tokens = CommonTokenStream(pre_lexer)
    pre_parser = Cobol85PreprocessorParser(pre_tokens)
    errors = CollectingErrorListener()
    pre_parser.removeErrorListeners()
    pre_parser.addErrorListener(errors)
    tree = pre_parser.startRule()
    tree_text = tree.toStringTree(recog=pre_parser)
    has_copy_node = "copyStatement" in tree_text
    return (
        f"COPY-Knoten im Parse-Tree vorhanden: {has_copy_node}; "
        f"kein Dateisystemzugriff nötig, kein Fehler trotz fehlendem "
        f"Copybook: {len(errors.errors) == 0} "
        f"({'KEINE Expansion — vertraeglich mit Prinzip 5' if has_copy_node else 'unerwartet'})"
    )


def main() -> None:
    fixtures = sorted(FIXTURES_DIR.glob("*.cbl"))
    if not fixtures:
        print(f"Keine Fixtures gefunden unter {FIXTURES_DIR}")
        sys.exit(1)

    results = [parse_fixture(f) for f in fixtures]

    print(f"{'Fixture':<30} {'Preproc':<8} {'Main':<8} {'Line/Col':<9} {'Sek':<6} Fehler (main, gekürzt)")
    print("-" * 100)
    ok_count = 0
    for r in results:
        status = "OK" if r.main_ok else "FEHLER"
        if r.main_ok:
            ok_count += 1
        err_preview = "; ".join(r.main_errors[:2])
        print(
            f"{r.name:<30} {('OK' if r.preprocessor_ok else 'FEHLER'):<8} "
            f"{status:<8} {str(r.has_line_column):<9} {r.parse_seconds:<6.3f} {err_preview}"
        )

    print("-" * 100)
    print(f"Strukturell OK: {ok_count}/{len(results)} (Go-Schwelle Phase 2: >=10/12)")
    print()
    print("Kernfrage 1 (reicht Cobol85Preprocessor.g4, oder bleibt")
    print("source_format.py als Vorstufe nötig?) — Fixtures nach")
    print("source_format.py-Rekonstruktion erneut gegen die Hauptgrammatik:")
    recon_ok = 0
    for f in fixtures:
        ok, errs = parse_reconstructed(f)
        if ok:
            recon_ok += 1
        preview = "; ".join(errs[:2])
        print(f"  {f.name:<30} {'OK' if ok else 'FEHLER':<8} {preview}")
    print(f"  -> {recon_ok}/{len(fixtures)} OK mit source_format.py vorgeschaltet "
          f"(vs. {ok_count}/{len(results)} ohne)")
    print()
    print("Kernfrage 2 (COPY-Expansion):", check_copy_expansion())
    print()
    print("Performance (Go/No-Go-Kriterium Phase 2):")
    print(" ", perf_check())
    print()
    print("Details je Fixture (oberste 2 Regelebenen des Parse-Trees):")
    for r in results:
        print(f"  {r.name}: {r.top_level_rule_hits[:8]}")


if __name__ == "__main__":
    main()
