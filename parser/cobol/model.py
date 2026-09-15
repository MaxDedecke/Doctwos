"""
parser/cobol/model.py
======================
COBOL-eigene Datenstrukturen der COBOL-Parser-Pipeline (Plan §6.2).

Divisions/Data-Division/Procedure/SQL ergänzen ihre eigenen Strukturen, sobald
sie gebaut werden — kein Vorbau auf Vorrat. Mit divisions.py/procedure.py kamen
`CobolProgram`, `Division`, `Section`, `Paragraph` dazu, mit data_division.py
`DataItem` und `FileDescriptor`, mit sql.py `SqlBlock`.

Die sprachneutralen Typen (`ParseResult`, `Entity`, `ParsedEdge`, `Chunk`,
`ParseDiagnostic` sowie die Alias-Typen `SourceFormat`/`EntityType`/
`EdgeType`/`Resolution`/`DiagnosticSeverity`/`DiagnosticPhase`) sind seit
O-078 nach `parser/core/model.py` verschoben (dort an ihnen selbst
hängt nichts COBOL-Spezifisches — ein künftiger zweiter Struktur-Parser,
siehe O-077, sollte nicht `from cobol.model import ParseResult` schreiben
müssen). Re-Export hier, damit bestehender Code unverändert weiterläuft.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.model import (  # noqa: F401 — Re-Export, siehe Docstring oben (O-078)
    Chunk,
    DiagnosticPhase,
    DiagnosticSeverity,
    EdgeType,
    Entity,
    EntityType,
    ParseDiagnostic,
    ParsedEdge,
    ParseResult,
    Resolution,
    SourceFormat,
)


@dataclass(frozen=True)
class Segment:
    """Ein zusammenhängendes Stück Code-Text auf genau einer physischen Zeile.

    col_start ist der 0-basierte Spaltenindex, an dem `text` in der
    Originalzeile beginnt — nötig, um Area A (Spalten 8-11) von Area B
    (12-72) zu unterscheiden (F-021).
    """

    phys_line: int
    col_start: int
    text: str


@dataclass
class LogicalLine:
    """Eine logische Quellzeile: eine oder mehrere physische Zeilen, per
    Continuation (Spalte 7 = '-') zu einer Einheit zusammengefasst.

    Zeilennummern sind heilig (CLAUDE.md) — jede LogicalLine trägt deshalb
    ihre physische Start-/Endzeile, nie nur eine Position im Fließtext.
    """

    phys_start_line: int
    phys_end_line: int
    segments: list[Segment] = field(default_factory=list)
    source_format: SourceFormat = "fixed"
    is_comment: bool = False
    is_debug: bool = False
    directive: str | None = None
    condition: str | None = None

    @property
    def text(self) -> str:
        """Verketteter Code-Text aller Segmente, ohne Positionsinformation."""
        return "".join(seg.text for seg in self.segments)


@dataclass
class Division:
    """IDENTIFICATION | ENVIRONMENT | DATA | PROCEDURE DIVISION (F-020).

    end_line ist die letzte Zeile mit einem Token in dieser Division, nicht
    einfach "nächster Header minus 1" — so bleiben trailing Kommentar-/Leer-
    zeilen vor der nächsten Division außerhalb des Bereichs.
    """

    name: str
    start_line: int
    end_line: int


@dataclass
class Section:
    """Section-Header (`NAME SECTION.`), sowohl in DATA DIVISION
    (WORKING-STORAGE/FILE/LINKAGE SECTION) als auch in PROCEDURE DIVISION
    (benutzerdefinierte Abschnittsnamen).
    """

    name: str
    division: str
    start_line: int
    end_line: int


@dataclass
class Paragraph:
    """Paragraph in der PROCEDURE DIVISION mit exaktem Zeilenbereich (F-023).

    section ist der Name der umschließenden Section, oder None, wenn der
    Paragraph direkt unter PROCEDURE DIVISION steht (kein Section-Header
    davor) — der häufige Fall in kleinen Programmen (siehe 01_minimal.cbl).
    """

    name: str
    section: str | None
    start_line: int
    end_line: int


@dataclass
class EntryPoint:
    """`ENTRY`-Anweisung (O-138): alternativer Eintrittspunkt in ein
    Unterprogramm, typischerweise für Aufrufer außerhalb von COBOL
    (Assembler/PL/I) oder CICS gedacht. name ist der Klartextname aus dem
    Literal (ohne Anführungszeichen). paragraph ist der Name des
    umschließenden Paragraphen, in dem die Anweisung steht, oder None, wenn
    sie direkt unter PROCEDURE DIVISION ohne Paragraph steht."""

    name: str
    paragraph: str | None
    start_line: int
    end_line: int


@dataclass
class CobolProgram:
    """Ein per PROGRAM-ID identifiziertes COBOL-Programm (F-020).

    name ist "" statt None, wenn PROGRAM-ID fehlt oder nicht erkannt wurde —
    kein Abbruch (Plan §6.1 Regel 2), der Fehler landet stattdessen in der
    errors-Liste von divisions.scan().

    O-138: eine Datei kann mehrere COBOL-Programme enthalten — mehrere
    aufeinanderfolgende PROGRAM-IDs (eigenständige Compilation Units) oder
    echt verschachtelte Unterprogramme (`programUnit*` in der Grammatik).
    divisions.scan() liefert dafür eine Liste von CobolProgram-Objekten,
    jedes mit AUSSCHLIESSLICH seinen eigenen (nicht den seiner Kinder oder
    Geschwister) Divisions/Sections/Paragraphen — Paragraph-/Feldnamen
    bleiben dadurch programmlokal (Abnahme O-138). parent_name trägt bei
    einem echt verschachtelten Unterprogramm den Namen des umschließenden
    Programms (sonst None) — nötig, damit zwei gleichnamige Unterprogramme
    unter verschiedenen Elternprogrammen nicht denselben qualified_name
    erhalten (siehe parse.py::_build_entities)."""

    name: str
    start_line: int
    end_line: int
    divisions: list[Division] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    paragraphs: list[Paragraph] = field(default_factory=list)
    entry_points: list[EntryPoint] = field(default_factory=list)
    parent_name: str | None = None


def program_own_range(program: CobolProgram) -> tuple[int, int]:
    """O-138: der Zeilenbereich, der AUSSCHLIESSLICH zu diesem Programm
    gehört — nie zu einem verschachtelten Unterprogramm oder einem
    nachfolgenden Geschwisterprogramm derselben Datei. `programUnit*`
    (verschachtelte Programme) steht in der Grammatik immer NACH der
    eigenen `procedureDivision` (`identificationDivision environmentDivision?
    dataDivision? procedureDivision? programUnit* endProgramStatement?`) —
    die Vereinigung der eigenen Divisions ist deshalb schon exakt diese
    Grenze, ganz ohne Kindprogramme explizit auszuschließen. copybook.py/
    sql.py nutzen das, um COPY-/EXEC-SQL-Vorkommen nicht mehrfach zu
    zählen, wenn parse.py je CobolProgram einer Datei einmal scannt.
    Fällt auf `program.start_line`/`end_line` zurück, wenn gar keine
    Division erkannt wurde (F-029-Fallback, z.B. 99_garbage.cbl)."""
    if not program.divisions:
        return program.start_line, program.end_line
    return program.divisions[0].start_line, program.divisions[-1].end_line


@dataclass
class FileDescriptor:
    """FD/SD-Kopf in der FILE SECTION (F-025).

    Umfasst nur den Kopf selbst (bis zu dessen abschließendem Punkt) — die
    zugehörige Satzbeschreibung ist ein normaler `DataItem` mit Level 01 und
    `parent=name` dieser FD/SD, kein Sonderfall in der Gruppenhierarchie.
    """

    name: str
    start_line: int
    end_line: int


@dataclass
class DataItem:
    """Datenfeld aus der DATA DIVISION (F-025): Level-Nummer 01-49/66/77/88,
    PIC, REDEFINES, OCCURS [DEPENDING ON], VALUE.

    parent ist der Name des umschließenden Gruppenfelds (COBOL-Gruppenhierarchie
    über Level-Nummern: ein Item ist Kind des nächsten vorangehenden Items mit
    kleinerer Level-Nummer) oder, für ein 01-Level-Satz in der FILE SECTION,
    der Name der umschließenden FD/SD. None für Top-Level-Items in WORKING-
    STORAGE/LINKAGE SECTION sowie für Level 66 (RENAMES) und 77 — beide sind
    laut COBOL-Grammatik eigenständig und nehmen nie an der Gruppenhierarchie
    teil.

    picture ist der rekonstruierte PIC-String (z.B. "X(10)V99"), nicht die
    einzelnen Tokens — der Lexer zerlegt ihn in mehrere WORD/NUMBER/SYMBOL-
    Tokens, `data_division.py` fügt sie anhand ihrer Spaltenposition wieder
    lückenlos zusammen.
    """

    name: str
    level: int
    start_line: int
    end_line: int
    parent: str | None = None
    picture: str | None = None
    redefines: str | None = None
    occurs: int | None = None
    occurs_depending_on: str | None = None
    value: str | None = None


@dataclass
class SqlBlock:
    """Ein `EXEC SQL … END-EXEC`-Block (F-027), Entity-Typ `sql_block`
    (docs/ENTSCHEIDUNGEN.md E-4).

    name ist synthetisch (`SQL-BLOCK@<start_line>`) — anders als Paragraphen
    oder Cursor hat ein anonymer SQL-Block kein COBOL-eigenes Bezeichnerwort;
    die Zeilennummer ist die einzige stabile Identität (CLAUDE.md „Zeilen-
    nummern sind heilig") und macht ihn trotzdem als Kantenendpunkt für die
    USES-Kante SQL-Block→Datenfeld eindeutig adressierbar (E-4).

    tables/host_variables sind roh aus dem SQL-Text extrahiert (kein
    Katalogabgleich — leichtgewichtiger Klassifikator laut Plan §6.2), in
    Fundreihenfolge dedupliziert. cursor_name ist nur bei DECLARE CURSOR /
    OPEN / FETCH / CLOSE gesetzt.
    """

    name: str
    statement_type: str
    start_line: int
    end_line: int
    tables: list[str] = field(default_factory=list)
    host_variables: list[str] = field(default_factory=list)
    cursor_name: str | None = None
