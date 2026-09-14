"""
parser/tests/cobol_corpus/matrix.py
=====================================
O-118: Kompatibilitätsmatrix je Compilerfamilie/-version und Merkmal.

Ein grüner Golden-File-Vergleich (test_cobol_golden.py) sagt nur, dass sich
das AKTUELLE Verhalten nicht unbeabsichtigt geändert hat - nicht, ob dieses
Verhalten für einen bestimmten Herstellercompiler korrekt ist (F-033 prüft
Byte-Stabilität, keine Korrektheit). Diese Matrix hängt jedem Fixture-Fall
zusätzlich einen Status an, der genau diese Lücke sichtbar macht.

Status-Werte (aus der O-118-Abnahme übernommen, plus ein vierter für schon
bekannte, noch offene Bugs):

- "unterstützt": Verhalten gegen eine dokumentierte Compilerregel geprüft
  und korrekt.
- "teilweise": Verhalten stimmt für den gezeigten Fall, deckt das Merkmal
  aber nicht vollständig ab.
- "nicht geprüft": synthetisches Fixture ohne Abgleich gegen einen echten
  Herstellercompiler. GnuCOBOL ist laut MAINFRAME_KOMPATIBILITAET.md KEIN
  Ersatz für eine Herstellerverifikation - "nicht geprüft" bleibt daher der
  Status, auch wenn das Fixture gegen GnuCOBOL liefe.
- "bekannter Fehler": das Golden File pinnt nur das AKTUELLE (falsche)
  Verhalten zur Regressionssicherung. test_cobol_compat_matrix.py hält
  zusätzlich das KORREKTE Verhalten als xfail(strict=True) fest, damit ein
  künftiger Fix sofort auffällt - Matrix-Status und xfail-Marker müssen
  dann in derselben Änderung aktualisiert werden.

Diese Matrix ist kein CI-Gate für die eigentliche Kundenabnahme (O-154) -
sie macht nur sichtbar, was von diesem synthetischen Korpus schon wofür
geprüft ist und was nicht. Optionale Referenzläufe gegen echte
Herstellercompiler sind bewusst nicht Teil dieser Datei (kein Compiler im
Repo/CI verfügbar) - sie kämen als eigener, getrennter Testlauf hinzu,
sobald ein solcher Referenzlauf tatsächlich existiert.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Status = Literal["unterstützt", "teilweise", "nicht geprüft", "bekannter Fehler"]


@dataclass(frozen=True)
class CompatCase:
    fixture: str  # Dateiname unter cobol_corpus/fixtures/, ohne ".cbl"
    feature: str  # kurzer Klartextname des geprüften Merkmals
    status: Status
    compiler_family: str = "generisch (eigene ANTLR-COBOL85-Grammatik, keine Herstellerabnahme)"
    ticket: str | None = None
    note: str = ""


MATRIX: list[CompatCase] = [
    CompatCase("01_minimal", "IDENTIFICATION/PROCEDURE DIVISION, minimal", "nicht geprüft"),
    CompatCase("02_fixed_edge", "Fixed-Format Spaltengrenzen", "nicht geprüft"),
    CompatCase("03_free_format", "Free-Format Grundfall", "nicht geprüft"),
    CompatCase("04_copy_replacing", "COPY ... REPLACING", "nicht geprüft"),
    CompatCase("05_copy_missing", "COPY auf fehlendes Copybook", "nicht geprüft"),
    CompatCase("06_data_qualified", "qualifizierte Datenfeldnamen", "nicht geprüft"),
    CompatCase("07_exec_sql", "EXEC SQL-Block", "nicht geprüft"),
    CompatCase("08_exec_cics", "EXEC CICS-Block (nur Maskierung, keine Ressourcenanalyse)", "nicht geprüft"),
    CompatCase("09_dynamic_call", "dynamischer CALL", "nicht geprüft"),
    CompatCase("10_perform_thru", "PERFORM ... THRU", "nicht geprüft"),
    CompatCase("11_bare_verb_statements", "Anweisungen ohne Punkt", "nicht geprüft"),
    CompatCase("12_identification_paragraphs", "IDENTIFICATION-Unterabsätze", "nicht geprüft"),
    CompatCase("13_umlauts", "Nicht-ASCII-Bezeichner im Quelltext", "nicht geprüft"),
    CompatCase(
        "14_free_format_directive",
        "SOURCE FORMAT FREE, Direktive in Spalte 1",
        "teilweise",
        note=(
            "Direktive wird bei Spalte-1-Position korrekt als Free-Signal "
            "gewertet - Gegenfall zu O-123, das dieselbe Direktive eingerückt "
            "zeigt (16_...). Nur dieser eine Fall geprüft, keine weiteren "
            "Einrückungstiefen oder Formatwechsel innerhalb einer Datei."
        ),
    ),
    CompatCase("15_table_subscript", "Tabellen-Index/Subscript", "nicht geprüft"),
    CompatCase(
        "16_source_format_free_directive_indented",
        "SOURCE FORMAT FREE, Direktive eingerückt",
        "teilweise",
        note=(
            "Direktive vor dem ersten Quelltext wird auch eingerückt als "
            "explizites Startformat erkannt. Die umfassenderen Fälle "
            "Variable/Extended und Wechsel innerhalb einer Datei werden "
            "in test_cobol_source_format.py abgedeckt; keine "
            "Hersteller-Compilerabnahme im CI."
        ),
    ),
    CompatCase(
        "17_conditional_compilation_true_branch",
        ">>IF/>>ELSE bedingte Kompilierung mit bekanntem Ausdruck",
        "teilweise",
        note=(
            "Numerische Gleichheit und profilierte DEFINEs werden ohne "
            "Quellcodeausführung ausgewertet; unbekannte Bedingungen bleiben "
            "als bedingte Kanten erhalten. Weitere EVALUATE-/Dialektformen "
            "sind noch nicht gegen Herstellercompiler geprüft."
        ),
    ),
    CompatCase(
        "18_multiple_programs",
        "mehrere Programme pro Datei (O-138)",
        "teilweise",
        note=(
            "Zwei eigenständige Compilation Units mit identischen Paragraphen-"
            "namen (MAIN-PARA/INIT-PARA) bleiben getrennt aufgelöst; das zweite "
            "Programm trägt zusätzlich eine ENTRY-Anweisung. Echt verschachtelte "
            "Unterprogramme (programUnit* INNERHALB eines anderen, nicht nur "
            "aufeinanderfolgend) sind nur in test_cobol_divisions.py abgedeckt, "
            "nicht hier - kein Herstellercompiler-Abgleich."
        ),
    ),
    CompatCase("99_garbage", "Datei ohne PROCEDURE DIVISION (Fallback-Chunking)", "nicht geprüft"),
]

MATRIX_BY_FIXTURE: dict[str, CompatCase] = {case.fixture: case for case in MATRIX}
