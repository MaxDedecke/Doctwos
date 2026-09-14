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

DiagnosticSeverity = Literal["error", "warning", "info"]
DiagnosticPhase = Literal["lexer", "parser", "profile"]


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


@dataclass(frozen=True)
class ParseDiagnostic:
    """O-119: strukturierte Lexer-/Parser-Syntaxdiagnose, getrennt von der
    bestehenden `ParseResult.errors`-Liste (reine Klartextsätze für
    strukturelle Befunde wie "PROGRAM-ID nicht gefunden", die divisions.py/
    data_division.py selbst feststellen). Bricht nie den Import ab — ANTLRs
    eigene Fehlerkorrektur (Resync) läuft unverändert weiter; das hier macht
    nur sichtbar, was sie überspielt.

    `line`/`column` beziehen sich auf die physische Originalzeile der
    Quelldatei, nicht auf den spaltenbereinigten Grammatik-Text — dessen
    Zeilennummern sind absichtlich stabil dazu (siehe
    `antlr_bridge._reconstruct_text`, CLAUDE.md "Zeilennummern sind heilig").
    `path` fehlt bewusst — ein `ParseDiagnostic` lebt immer in genau einer
    `ParseResult`, deren `path` schon gilt.

    Stammt eine Diagnose aus dem ersten SLL-Parse-Versuch, der anschließend
    mit LL(*) erfolgreich wiederholt wurde, taucht sie hier NICHT auf
    (O-119-Abnahme) — nur Diagnosen des tatsächlich verwendeten Durchlaufs
    zählen. Mehrfach identisch auftretende Diagnosen werden vor der Rückgabe
    gebündelt (`count` > 1) statt einzeln aufgelistet.

    `phase="profile"` (O-121) markiert Diagnosen, die nicht aus ANTLR
    stammen, sondern aus der Buildprofil-Auflösung (`cobol/profile.py`) —
    z.B. ein per Heuristik statt per Profil bestimmtes Quellformat oder eine
    unbekannte `compiler_family`. `severity="info"` ist für solche Fälle
    gedacht, die weder Fehler noch echte Warnung sind (z.B. eine bewusste
    Profil-Übersteuerung über mehrere Ebenen).

    `profile` selbst bleibt weiterhin `None` — Profile haben noch keine
    persistierte Identität (kein Name/keine ID, siehe `cobol/profile.py`),
    das kommt erst mit der DB-/Einrichtungsseite (O-151).
    """

    code: str
    severity: DiagnosticSeverity
    phase: DiagnosticPhase
    message: str
    line: int
    column: int
    count: int = 1
    profile: str | None = None


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
    diagnostics: list[ParseDiagnostic] = field(default_factory=list)


# O-120: bislang leitete GitConnector den einzigen sichtbaren Qualitätsstatus
# ("ok"/"fallback_text") ausschließlich aus `errors` ab -- die mit O-119
# eingeführten strukturierten `diagnostics` (z.B. ein zurückgestuftes
# COBOL85-Fallback-Token oder eine unbekannte `compiler_family`, siehe
# O-121s `PROFILE_UNKNOWN_COMPILER_FAMILY`) blieben dabei unberücksichtigt --
# eine Datei mit ernsten Diagnosen aber leerem `errors` erschien als "ok",
# genau die in MAINFRAME_KOMPATIBILITAET.md dokumentierte Lücke. Diese vier
# Werte sind bewusst der komplette Wortschatz aus dem O-120-Katalogeintrag
# ("vollständig/teilweise/Textfallback/übersprungen") -- "skipped" wird nie
# von `classify_completeness()` vergeben (eine Datei, die klassifiziert wird,
# wurde per Definition geparst), sondern direkt vom aufrufenden Connector
# gesetzt, wenn eine Datei gar nicht erst an den Parser ging (Binärformat,
# Größenlimit, kein UTF-8 -- siehe `connectors/git.py::fetch_documents`).
AnalysisStatus = Literal["complete", "partial", "text_fallback", "skipped"]


def classify_completeness(result: ParseResult) -> tuple[AnalysisStatus, list[str]]:
    """Bewertet ein `ParseResult` danach, wie vollständig die Struktur der
    Datei tatsächlich erfasst wurde -- nicht nur, ob der Parser abgestürzt
    ist. Reine Funktion, kein DB-Zugriff (wie `ParseResult` selbst, E-6).

    - "text_fallback": kein einziger PROCEDURE-DIVISION-Paragraph gefunden
      (F-029) -- `_fallback_chunks()` markiert das eigens mit
      `meta["fallback"] = True`, statt dass wir hier erneut prüfen müssten,
      ob `entities`/`edges` leer sind (eine Datei ohne PROCEDURE DIVISION
      kann trotzdem IDENTIFICATION-/DATA-DIVISION-Entities haben).
    - "partial": es wurde Struktur erkannt, aber `errors` und/oder
      `diagnostics` mit severity "error"/"warning" stehen dagegen -- ein
      fachlich unvollständiger oder unsicherer Graph, der nicht als
      uneingeschränkt verlässlich gelten darf (O-120-Abnahme). severity
      "info" (z.B. O-121s `SOURCE_FORMAT_HEURISTIC`, die ohne Buildprofil
      für praktisch jede Datei anfällt) zählt bewusst NICHT als Makel --
      sonst würde die reine Abwesenheit eines noch nicht existierenden
      Profil-Einrichtungswegs (O-151) jede Datei zu "partial" degradieren.
    - "complete": weder noch.
    """
    reasons = list(result.errors)
    reasons += [d.message for d in result.diagnostics if d.severity in ("error", "warning")]

    if any(chunk.meta.get("fallback") for chunk in result.chunks):
        return "text_fallback", reasons or [
            "Keine PROCEDURE DIVISION gefunden, Datei wurde als Volltext statt als Struktur analysiert."
        ]
    if reasons:
        return "partial", reasons
    return "complete", []
