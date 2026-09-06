"""
parser/core/model.py
=====================
Sprachneutrale Datenstrukturen der Parser-Pipeline (Plan §6.2/§6.3).

O-078: Vorher standen `ParseResult`/`Entity`/`ParsedEdge`/`Chunk` in
`parser/cobol/model.py`, obwohl an ihnen selbst nichts COBOL-Spezifisches
hängt — `cobol_persist.py::persist_parse_result` könnte sie unverändert für
jede Sprache verarbeiten. Das erzwang für einen künftigen zweiten Struktur-
Parser (siehe O-077, `cobol/registry.py::STRUCTURE_PARSERS`) die falsche
Kopplung `from cobol.model import ParseResult`. Diese vier Typen (plus die
Literal-Aliase, die sie referenzieren) leben jetzt hier; `cobol/model.py`
importiert sie unverändert weiter, damit bestehender Code (`from cobol.model
import ...` sowie das paketinterne `from .model import ...`) unangetastet
bleibt. Reine Verschiebung — keine Verhaltensänderung.

COBOL-eigene Strukturen (`CobolProgram`, `Division`, `Section`, `Paragraph`,
`DataItem`, `FileDescriptor`, `SqlBlock`, `Segment`, `LogicalLine`) bleiben
bewusst in `cobol/model.py` — sie sind an COBOLs Grammatik gebunden, nicht
sprachneutral.

`EntityType`/`EdgeType`/`Resolution` spiegeln bewusst die String-Werte aus
`backend/models/database.py` (`CodeEntity.type`, `CodeEdge.type`/`.resolution`) —
der Parser produziert hier schon die Werte, die `parse.py` später 1:1 in die
DB schreibt, keine Übersetzungstabelle nötig.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SourceFormat = Literal["fixed", "free"]

EntityType = Literal[
    "program",
    "copybook",
    "section",
    "paragraph",
    "data_item",
    "file_fd",
    "sql_table",
    "sql_block",
]

EdgeType = Literal["CALL", "PERFORM", "GOTO", "COPY", "DEFINES", "USES", "READS", "WRITES"]
# "GOTO" ist noch nicht in backend/models/database.py::CodeEdge.type (Kommentar
# listet nur "CALL | PERFORM | COPY | DEFINES | USES | READS | WRITES") — nachziehen,
# sobald parse.py/die DB-Schicht ans Ergebnis von procedure.py angebunden wird.

Resolution = Literal["resolved", "unresolved", "dynamic"]


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

    Zwei Sonderfälle aus parse.py chunken die gesamte Datei statt einzelner
    Paragraphen (kein `"section"`/`"paragraph"`): F-029-Fallback (kein
    PROCEDURE-DIVISION-Paragraph gefunden) → `"program"` + `"fallback": True`;
    Copybooks (keine PROCEDURE DIVISION, parse_copybook()) → `"copybook"`.
    """

    content: str
    start_line: int
    end_line: int
    meta: dict


@dataclass
class Entity:
    """Eine geparste Entity, wie sie später 1:1 in `code_entities` landet
    (F-030) — bis auf die DB-Zuweisungen selbst (`id`/`project_id`/
    `source_id`/`parent_id`/`content_hash`), die erst beim Persistieren in
    AP-4 entstehen (docs/ENTSCHEIDUNGEN.md E-6). `parent_name` trägt
    stattdessen den Namen der Eltern-Entity **derselben Datei** — AP-4 löst
    daraus beim Schreiben die echte `parent_id` auf.

    `qualified_name` wird schon hier gebaut (z.B. "XAAOA.MAIN-SECTION.
    INIT-PARA") — alle dafür nötigen Vorfahren sind beim Parsen einer
    einzelnen Datei bereits vollständig bekannt, kein Grund, das auf
    AP-4/die DB-Schicht zu verschieben.
    """

    type: EntityType
    name: str
    start_line: int
    end_line: int
    parent_name: str | None = None
    qualified_name: str | None = None
    meta: dict = field(default_factory=dict)


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


@dataclass
class ParseResult:
    """Ergebnis eines Struktur-Parsers (siehe `cobol/registry.py::
    STRUCTURE_PARSERS`, O-077) für **eine** Datei (Plan §6.3), komplett
    in-memory — kein DB-Zugriff (docs/ENTSCHEIDUNGEN.md E-6). Das ist die
    Struktur, gegen die die Golden Files aus F-033 vergleichen.
    """

    program_name: str
    path: str
    source_format: SourceFormat
    entities: list[Entity] = field(default_factory=list)
    edges: list[ParsedEdge] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
