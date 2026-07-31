"""
parser/cobol/model.py
======================
Gemeinsame Datenstrukturen der COBOL-Parser-Pipeline (Plan §6.2).

Divisions/Data-Division/Procedure/SQL ergänzen ihre eigenen Strukturen, sobald
sie gebaut werden — kein Vorbau auf Vorrat. Mit divisions.py/procedure.py kamen
`CobolProgram`, `Division`, `Section`, `Paragraph` und `ParsedEdge` dazu, mit
data_division.py `DataItem` und `FileDescriptor`, mit sql.py `SqlBlock`, mit
chunking.py jetzt `Chunk`. ParseResult folgt mit parse.py.

`EntityType`/`EdgeType`/`Resolution` spiegeln bewusst die String-Werte aus
`backend/models/database.py` (`CodeEntity.type`, `CodeEdge.type`/`.resolution`) —
der Parser produziert hier schon die Werte, die parse.py später 1:1 in die DB
schreibt, keine Übersetzungstabelle nötig.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SourceFormat = Literal["fixed", "free"]

EntityType = Literal[
    "program", "copybook", "section", "paragraph",
    "data_item", "file_fd", "sql_table", "sql_block",
]

EdgeType = Literal["CALL", "PERFORM", "GOTO", "COPY", "DEFINES", "USES", "READS", "WRITES"]
# "GOTO" ist noch nicht in backend/models/database.py::CodeEdge.type (Kommentar
# listet nur "CALL | PERFORM | COPY | DEFINES | USES | READS | WRITES") — nachziehen,
# sobald parse.py/die DB-Schicht ans Ergebnis von procedure.py angebunden wird.

Resolution = Literal["resolved", "unresolved", "dynamic"]


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
class CobolProgram:
    """Ein per PROGRAM-ID identifiziertes COBOL-Programm (F-020).

    name ist "" statt None, wenn PROGRAM-ID fehlt oder nicht erkannt wurde —
    kein Abbruch (Plan §6.1 Regel 2), der Fehler landet stattdessen in der
    errors-Liste von divisions.scan().
    """

    name: str
    start_line: int
    end_line: int
    divisions: list[Division] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    paragraphs: list[Paragraph] = field(default_factory=list)


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


@dataclass
class Chunk:
    """Ein Embedding-Chunk (F-041) — `content` plus `meta`, das 1:1 in
    `DocumentChunk.metadata_json` landet (parser/models/database.py).

    meta enthält immer `"program"`/`"format"`. Für den Normalfall (ein Chunk
    = ein Paragraph) zusätzlich `"section"`/`"paragraph"` (je `str`). Zwei
    Ausnahmen ändern die Form:

    - Split eines zu großen Paragraphen (> chunk_size): `"paragraph"` bleibt
      derselbe Name, dazu `"part"`/`"parts"` (1-basiert).
    - Merge mehrerer zu kleiner Nachbarparagraphen derselben Section
      (< min_chunk_size): `"paragraph"` (singular) entfällt zugunsten von
      `"paragraphs"` (`list[str]`) — ein Chunk deckt dann mehr als einen
      Paragraphen ab, das Singular-Feld wäre irreführend.
    """

    content: str
    start_line: int
    end_line: int
    meta: dict


@dataclass
class ParsedEdge:
    """Eine Kante, wie sie später 1:1 in `code_edges` landet (F-032).

    scope ist der Programmname für lokal aufzulösende Kantenarten (PERFORM,
    GO TO, USES, DEFINES) und None für global aufzulösende (CALL, COPY) —
    siehe docs/ENTSCHEIDUNGEN.md E-1. src_start_line/src_end_line sind die
    Zeile(n) der Anweisung selbst (z.B. der CALL-Zeile), nicht des ganzen
    umschließenden Paragraphen — das ist, worauf F-067ff. später verlinkt.
    """

    type: EdgeType
    src_name: str
    dst_name: str
    resolution: Resolution
    src_start_line: int
    src_end_line: int
    scope: str | None = None
    meta: dict = field(default_factory=dict)
