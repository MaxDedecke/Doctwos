"""
parser/cobol/divisions.py
===========================
F-020 (Phase 3, E-11): Programmstruktur — IDENTIFICATION/ENVIRONMENT/DATA/
PROCEDURE DIVISION, PROGRAM-ID, Sections (in DATA wie in PROCEDURE DIVISION)
und Paragraphen mit exakten Zeilenbereichen (F-023) — aus dem ANTLR-Parse-Tree
(`antlr_bridge.build_tree()`) statt aus einem handgeschriebenen Token-Scan.

Ersetzt die bis Phase 3 (docs/ENTSCHEIDUNGEN.md E-11) handgeschriebene
lineare Token-Abtastung: die Grammatik unterscheidet Division-/Section-/
Paragraphen-Köpfe strukturell bereits selbst (eigene Regeln
`identificationDivision`/`dataDivision`/`procedureDivision`/
`procedureSectionHeader`/`paragraph`), ein alleinstehendes `GOBACK.`/`EXIT.`
sieht im Parse-Tree nie wie ein Paragraphenkopf aus — die frühere
`_RESERVED_BARE_VERBS`-Ausnahmeliste entfällt ersatzlos.

Kein Abbruch (Plan §6.1 Regel 2): fehlt PROGRAM-ID oder jede Division, gibt
es einen möglichst vollständigen CobolProgram plus Einträge in der
zurückgegebenen Fehlerliste — nie eine Exception. ANTLR-Syntaxfehler selbst
werden nie in diese Fehlerliste übernommen (dieselbe Haltung wie zuvor, als
unbekannte Tokens stillschweigend übersprungen wurden) — seit O-119 aber
strukturiert über einen eigenen Rückgabewert (`antlr_bridge._FlaggingErrorListener`)
statt komplett verschluckt.

O-138: `compilationUnit` ist grammatikalisch `programUnit+`, und `programUnit`
selbst enthält rekursiv `programUnit*` (echt verschachtelte Unterprogramme).
`scan()` liefert deshalb eine LISTE von CobolProgram statt eines einzelnen —
jedes mit ausschließlich seinen EIGENEN Divisions/Sections/Paragraphen, nie
denen eines Geschwister- oder Kindprogramms (siehe `_StructureVisitor`unten).
Für den weit überwiegenden Normalfall (genau ein Programm pro Datei) bleiben
Zeilengrenzen und Fehlerverhalten exakt wie vor O-138 (siehe `_single_program()`
unten) — kein Golden-File-Unterschied für bestehende Fixtures.
"""

from __future__ import annotations

from . import antlr_bridge
from . import lexer as lexer_mod
from ._antlr.Cobol85Parser import Cobol85Parser
from ._antlr.Cobol85Visitor import Cobol85Visitor
from .model import CobolProgram, Division, LogicalLine, ParseDiagnostic, Paragraph, Section

_DIVISION_RULE_NAMES = {
    "identificationDivision": "IDENTIFICATION",
    "environmentDivision": "ENVIRONMENT",
    "dataDivision": "DATA",
    "procedureDivision": "PROCEDURE",
}


def scan(
    masked_lines: list[LogicalLine],
) -> tuple[list[CobolProgram], list[str], list[ParseDiagnostic]]:
    errors: list[str] = []

    tokens = lexer_mod.tokenize(masked_lines)
    if not tokens:
        errors.append("Keine Tokens gefunden - leere oder nicht lesbare Datei.")
        return [CobolProgram(name="", start_line=0, end_line=0)], errors, []

    start_line = tokens[0].phys_line
    last_line = tokens[-1].phys_line

    tree, source_text, diagnostics = antlr_bridge.build_tree(masked_lines)
    visitor = _StructureVisitor(source_text)
    visitor.visit(tree)
    programs = visitor.programs or [CobolProgram(name="", start_line=start_line, end_line=last_line)]

    if not any(p.divisions for p in programs):
        errors.append(
            "Keine Division erkannt (weder IDENTIFICATION/ENVIRONMENT/DATA/PROCEDURE DIVISION gefunden)."
        )
    if any(not p.name for p in programs):
        errors.append("PROGRAM-ID nicht gefunden.")

    if len(programs) == 1:
        # Einzelprogramm-Normalfall (weit überwiegende Mehrheit aller Dateien,
        # alle bestehenden Golden Files): Zeilengrenzen kommen unverändert vom
        # gesamten Tokenstrom, nicht vom (potenziell engeren) AST-Knoten des
        # einzelnen programUnit - identisch zum Verhalten vor O-138, auch für
        # PROGRAM-ID-lose oder division-lose Dateien (F-029-Fallback).
        programs[0].start_line = start_line
        programs[0].end_line = last_line

    return programs, errors, diagnostics


class _ProgramFrame:
    """Sammelstelle für EIN `programUnit` während des Besuchs — getrennt vom
    fertigen `CobolProgram`, weil sich `name` erst über `visitProgramIdParagraph`
    ergibt, nachdem der Frame schon existieren muss (Divisions werden vorher
    besucht)."""

    def __init__(self, parent_name: str | None) -> None:
        self.name = ""
        self.parent_name = parent_name
        self.divisions: list[Division] = []
        self.sections: list[Section] = []
        self.paragraphs: list[Paragraph] = []


class _StructureVisitor(Cobol85Visitor):
    """Ein Durchlauf über ALLE `programUnit`-Knoten (O-138: mehrere
    aufeinanderfolgende PROGRAM-IDs UND echt verschachtelte Unterprogramme).

    Jedes `programUnit` bekommt einen eigenen `_ProgramFrame` auf einem
    Stack: Divisions/Sections/Paragraphen landen immer im jeweils obersten
    Frame, nie in einer geteilten globalen Liste — genau das war der O-138-
    Fehler (gleichnamige Paragraphen/Felder verschiedener Programme wurden
    ununterscheidbar vermischt). Ein verschachteltes `programUnit` pusht
    einen neuen Frame VOR seinem eigenen `visitChildren()`-Aufruf und poppt
    ihn danach wieder — zu jedem Zeitpunkt gehört der Stack-Top exakt zu dem
    `programUnit`, dessen Divisions/Paragraphen gerade besucht werden, weil
    die Grammatik `identificationDivision environmentDivision? dataDivision?
    procedureDivision? programUnit* endProgramStatement?` verschachtelte
    Unterprogramme immer ERST NACH der eigenen PROCEDURE DIVISION erlaubt."""

    def __init__(self, source_text: str) -> None:
        self.programs: list[CobolProgram] = []
        self._stack: list[_ProgramFrame] = []
        self._source_text = source_text

    def visitProgramUnit(self, ctx: Cobol85Parser.ProgramUnitContext):  # noqa: N802
        # Der VOLLE Vorfahrenpfad (nicht nur der unmittelbare Elternname) -
        # sonst kollidieren zwei gleichnamige, zwei Ebenen tief verschachtelte
        # Unterprogramme unter verschiedenen Großeltern (parse.py::_qualify
        # baut daraus "A.B.C" statt nur "B.C").
        parent_name = ".".join(f.name for f in self._stack) if self._stack else None
        frame = _ProgramFrame(parent_name)
        self._stack.append(frame)

        for name, rule_key in _DIVISION_RULE_NAMES.items():
            child = getattr(ctx, name)()
            if child is None or child.exception is not None:
                continue
            frame.divisions.append(Division(rule_key, _line(child.start), _line(child.stop)))

        self.visitChildren(ctx)

        finished = self._stack.pop()
        self.programs.append(
            CobolProgram(
                name=finished.name,
                start_line=_line(ctx.start),
                end_line=_line(ctx.stop),
                divisions=finished.divisions,
                sections=finished.sections,
                paragraphs=finished.paragraphs,
                parent_name=finished.parent_name,
            )
        )
        return None

    def visitProgramIdParagraph(self, ctx: Cobol85Parser.ProgramIdParagraphContext):  # noqa: N802
        name_ctx = ctx.programName()
        if name_ctx is not None and self._stack:
            self._stack[-1].name = _clean_name(antlr_bridge.original_span(self._source_text, name_ctx))
        return None

    def visitFileSection(self, ctx: Cobol85Parser.FileSectionContext):  # noqa: N802
        self._record_named_section(ctx, "FILE", ctx.start, ctx.stop, "DATA")
        return self.visitChildren(ctx)

    def visitWorkingStorageSection(self, ctx: Cobol85Parser.WorkingStorageSectionContext):  # noqa: N802
        self._record_named_section(ctx, "WORKING-STORAGE", ctx.start, ctx.stop, "DATA")
        return self.visitChildren(ctx)

    def visitLinkageSection(self, ctx: Cobol85Parser.LinkageSectionContext):  # noqa: N802
        self._record_named_section(ctx, "LINKAGE", ctx.start, ctx.stop, "DATA")
        return self.visitChildren(ctx)

    def visitProcedureSectionHeader(self, ctx: Cobol85Parser.ProcedureSectionHeaderContext):  # noqa: N802
        # procedureSection wraps header + its paragraphs; the header's own
        # ctx only spans "NAME SECTION [n]" — the real end_line comes from
        # the enclosing procedureSection, handled in visitProcedureSection().
        return None

    def visitProcedureSection(self, ctx: Cobol85Parser.ProcedureSectionContext):  # noqa: N802
        header = ctx.procedureSectionHeader()
        name = _clean_name(antlr_bridge.original_span(self._source_text, header.sectionName()))
        self._stack[-1].sections.append(Section(name, "PROCEDURE", _line(ctx.start), _line(ctx.stop)))
        self._collect_paragraphs(ctx.paragraphs(), name)
        return None

    def visitProcedureDivisionBody(self, ctx: Cobol85Parser.ProcedureDivisionBodyContext):  # noqa: N802
        # Paragraphen direkt unter PROCEDURE DIVISION, vor der ersten Section
        # (oder wenn es gar keine Section gibt) - section=None.
        self._collect_paragraphs(ctx.paragraphs(), None)
        for section_ctx in ctx.procedureSection():
            self.visit(section_ctx)
        return None

    def _collect_paragraphs(self, paragraphs_ctx, section_name: str | None) -> None:
        if paragraphs_ctx is None:
            return
        for p in paragraphs_ctx.paragraph():
            name_ctx = p.paragraphName()
            name = (
                _clean_name(antlr_bridge.original_span(self._source_text, name_ctx))
                if name_ctx is not None
                else ""
            )
            if not name:
                continue
            self._stack[-1].paragraphs.append(
                Paragraph(name, section_name, _line(p.start), _line(p.stop))
            )

    def _record_named_section(self, ctx, name: str, start_tok, stop_tok, division: str) -> None:
        self._stack[-1].sections.append(Section(name, division, _line(start_tok), _line(stop_tok)))


def _line(token) -> int:
    return token.line if token is not None else 0


def _clean_name(value: str) -> str:
    if value[:1] in ("'", '"') and value[-1:] == value[:1]:
        return value[1:-1]
    return value
