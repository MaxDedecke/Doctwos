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
werden nie in diese Liste übernommen (antlr_bridge._SilentErrorListener) —
dieselbe Haltung wie zuvor, als unbekannte Tokens stillschweigend übersprungen
wurden.
"""

from __future__ import annotations

from . import antlr_bridge
from . import lexer as lexer_mod
from ._antlr.Cobol85Parser import Cobol85Parser
from ._antlr.Cobol85Visitor import Cobol85Visitor
from .model import CobolProgram, Division, LogicalLine, Paragraph, Section

_DIVISION_RULE_NAMES = {
    "identificationDivision": "IDENTIFICATION",
    "environmentDivision": "ENVIRONMENT",
    "dataDivision": "DATA",
    "procedureDivision": "PROCEDURE",
}


def scan(masked_lines: list[LogicalLine]) -> tuple[CobolProgram, list[str]]:
    errors: list[str] = []

    tokens = lexer_mod.tokenize(masked_lines)
    if not tokens:
        errors.append("Keine Tokens gefunden - leere oder nicht lesbare Datei.")
        return CobolProgram(name="", start_line=0, end_line=0), errors

    start_line = tokens[0].phys_line
    last_line = tokens[-1].phys_line

    tree, source_text = antlr_bridge.build_tree(masked_lines)
    visitor = _StructureVisitor(source_text)
    visitor.visit(tree)

    if not visitor.divisions:
        errors.append("Keine Division erkannt (weder IDENTIFICATION/ENVIRONMENT/DATA/PROCEDURE DIVISION gefunden).")
    if not visitor.program_name:
        errors.append("PROGRAM-ID nicht gefunden.")

    program = CobolProgram(
        name=visitor.program_name,
        start_line=start_line,
        end_line=last_line,
        divisions=visitor.divisions,
        sections=visitor.sections,
        paragraphs=visitor.paragraphs,
    )
    return program, errors


class _StructureVisitor(Cobol85Visitor):
    """Ein Durchlauf über `programUnit` (nur das erste — mehrere PROGRAM-IDs
    pro Datei werden wie vor Phase 3 nicht unterstützt, das gesamte File gilt
    als ein CobolProgram, siehe divisions.py-Historie/Tests). PROGRAM-ID aus
    späteren `programUnit`-Wiederholungen (verschachtelte Unterprogramme)
    überschreibt den Namen — dieselbe "letzter gewinnt"-Regel wie zuvor."""

    def __init__(self, source_text: str) -> None:
        self.program_name = ""
        self.divisions: list[Division] = []
        self.sections: list[Section] = []
        self.paragraphs: list[Paragraph] = []
        self._current_division: str | None = None
        self._source_text = source_text

    def visitProgramUnit(self, ctx: Cobol85Parser.ProgramUnitContext):  # noqa: N802
        for name, rule_key in _DIVISION_RULE_NAMES.items():
            child = getattr(ctx, name)()
            if child is None or child.exception is not None:
                continue
            self._current_division = rule_key
            self.divisions.append(Division(rule_key, _line(child.start), _line(child.stop)))
        self.visitChildren(ctx)
        return None

    def visitProgramIdParagraph(self, ctx: Cobol85Parser.ProgramIdParagraphContext):  # noqa: N802
        name_ctx = ctx.programName()
        if name_ctx is not None:
            self.program_name = _clean_name(antlr_bridge.original_span(self._source_text, name_ctx))
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
        self.sections.append(Section(name, "PROCEDURE", _line(ctx.start), _line(ctx.stop)))
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
            name = _clean_name(antlr_bridge.original_span(self._source_text, name_ctx)) if name_ctx is not None else ""
            if not name:
                continue
            self.paragraphs.append(Paragraph(name, section_name, _line(p.start), _line(p.stop)))

    def _record_named_section(self, ctx, name: str, start_tok, stop_tok, division: str) -> None:
        self.sections.append(Section(name, division, _line(start_tok), _line(stop_tok)))


def _line(token) -> int:
    return token.line if token is not None else 0


def _clean_name(value: str) -> str:
    if value[:1] in ("'", '"') and value[-1:] == value[:1]:
        return value[1:-1]
    return value
