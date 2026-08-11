"""
parser/cobol/data_division.py
================================
F-025 (Phase 3, E-11): Level-Nummern (01-49/66/77/88), PIC, REDEFINES,
OCCURS [DEPENDING ON], VALUE sowie FD/SD → FileDescriptor aus der DATA
DIVISION — aus dem ANTLR-Parse-Tree statt aus einem Token-Scan.

Läuft nach divisions.scan() — braucht dessen CobolProgram nicht mehr direkt
(die Grammatik liefert Sections/FDs strukturiert), wohl aber denselben
Parse-Tree noch einmal (antlr_bridge.build_tree() ist günstig genug, um ihn
zweimal zu bauen — ein gemeinsamer Cache über beide Aufrufe wäre eine
spätere Optimierung, keine Korrektheitsfrage).

Gruppenhierarchie (parent) bleibt ein Stack von (Level, Name) — das
COBOL85-Grammatik selbst bildet die Ebenen-basierte Gruppenhierarchie NICHT
strukturell im Baum ab (`dataDescriptionEntry*` ist eine flache Liste,
`fileDescriptionEntry` verschachtelt lediglich "alle Items dieser FD", nicht
Gruppe-in-Gruppe) — derselbe Algorithmus wie vor Phase 3: ein neues Item mit
Level L schließt alle Stack-Einträge mit Level >= L, sein Elternteil ist
danach der Stack-Top (oder die aktuelle FD/SD, wenn der Stack leer ist).
Level 88 (Condition-Name) und 66 (RENAMES) werden nie auf den Stack gelegt,
Level 77 setzt sich selbst als Top-Level (parent=None).

Ein per COPY-Statement maskiertes Filler-Item (`antlr_bridge.
COPY_PLACEHOLDER_NAME`) wird aus dem Ergebnis gefiltert — es diente nur dazu,
den Zeilenbereich der umschließenden Section im Parse-Tree korrekt zu halten
(siehe antlr_bridge.py), ist aber kein echtes Datenfeld.

Kein Abbruch (Plan §6.1 Regel 2): fehlt die DATA DIVISION, gibt es leere
Ergebnislisten plus einen Fehlereintrag, nie eine Exception.
"""

from __future__ import annotations

from . import antlr_bridge
from ._antlr.Cobol85Parser import Cobol85Parser
from ._antlr.Cobol85Visitor import Cobol85Visitor
from .antlr_bridge import COPY_PLACEHOLDER_NAME
from .model import CobolProgram, DataItem, FileDescriptor, LogicalLine

_CONDITION_LEVEL = 88
_RENAMES_LEVEL = 66
_STANDALONE_LEVEL = 77


def parse(program: CobolProgram, masked_lines: list[LogicalLine]) -> tuple[list[DataItem], list[FileDescriptor], list[str]]:
    errors: list[str] = []

    data_division = next((d for d in program.divisions if d.name == "DATA"), None)
    if data_division is None:
        errors.append("Keine DATA DIVISION gefunden - Datenfelder nicht durchsucht.")
        return [], [], errors

    # parse_copybook() (parse.py) übergibt ein synthetisches CobolProgram ohne
    # IDENTIFICATION DIVISION - COBOL85s Grammatik verlangt sie zwingend
    # (siehe antlr_bridge.build_tree()-Docstring).
    is_copybook = not any(d.name == "IDENTIFICATION" for d in program.divisions)
    header = (
        "IDENTIFICATION DIVISION. PROGRAM-ID. ANTLR-COPYBOOK-WRAPPER. DATA DIVISION. WORKING-STORAGE SECTION."
        if is_copybook
        else None
    )
    tree = antlr_bridge.build_tree(masked_lines, header=header)
    visitor = _DataDivisionVisitor()
    visitor.visit(tree)

    items = [i for i in visitor.items if i.name.upper() != COPY_PLACEHOLDER_NAME]
    return items, visitor.file_descriptors, errors


class _DataDivisionVisitor(Cobol85Visitor):
    def __init__(self) -> None:
        self.items: list[DataItem] = []
        self.file_descriptors: list[FileDescriptor] = []

    def visitFileSection(self, ctx: Cobol85Parser.FileSectionContext):  # noqa: N802
        for fd_ctx in ctx.fileDescriptionEntry():
            self._visit_file_descriptor(fd_ctx)
        return None

    def _visit_file_descriptor(self, ctx: Cobol85Parser.FileDescriptionEntryContext) -> None:
        name = _clean_name(ctx.fileName().getText())
        entries = ctx.dataDescriptionEntry()
        header_end = _line(entries[0].start) - 1 if entries else _line(ctx.stop)
        header_end = max(header_end, _line(ctx.start))
        self.file_descriptors.append(FileDescriptor(name=name, start_line=_line(ctx.start), end_line=header_end))

        stack: list[tuple[int, str]] = []
        for entry in entries:
            self._visit_entry(entry, stack, current_fd=name)

    def visitWorkingStorageSection(self, ctx: Cobol85Parser.WorkingStorageSectionContext):  # noqa: N802
        stack: list[tuple[int, str]] = []
        for entry in ctx.dataDescriptionEntry():
            self._visit_entry(entry, stack, current_fd=None)
        return None

    def visitLinkageSection(self, ctx: Cobol85Parser.LinkageSectionContext):  # noqa: N802
        stack: list[tuple[int, str]] = []
        for entry in ctx.dataDescriptionEntry():
            self._visit_entry(entry, stack, current_fd=None)
        return None

    def _visit_entry(self, entry: Cobol85Parser.DataDescriptionEntryContext, stack: list[tuple[int, str]], current_fd: str | None) -> None:
        fmt1 = entry.dataDescriptionEntryFormat1()
        if fmt1 is not None:
            self._visit_format1(fmt1, stack, current_fd)
            return

        fmt2 = entry.dataDescriptionEntryFormat2()
        if fmt2 is not None:
            name = _clean_name(fmt2.dataName().getText())
            self.items.append(
                DataItem(name=name, level=_RENAMES_LEVEL, start_line=_line(fmt2.start), end_line=_line(fmt2.stop), parent=None)
            )
            return

        fmt3 = entry.dataDescriptionEntryFormat3()
        if fmt3 is not None:
            name = _clean_name(fmt3.conditionName().getText())
            parent = stack[-1][1] if stack else current_fd
            value = _value_text(fmt3.dataValueClause())
            self.items.append(
                DataItem(
                    name=name, level=_CONDITION_LEVEL, start_line=_line(fmt3.start), end_line=_line(fmt3.stop),
                    parent=parent, value=value,
                )
            )
            return
        # dataDescriptionEntryExecSql: kein echtes Datenfeld, wird nie erreicht
        # (EXEC-Blöcke sind vor antlr_bridge.build_tree() bereits maskiert),
        # bleibt hier nur als expliziter No-Op statt stillschweigend zu fehlen.

    def _visit_format1(self, ctx: Cobol85Parser.DataDescriptionEntryFormat1Context, stack: list[tuple[int, str]], current_fd: str | None) -> None:
        level = _level_number(ctx)
        if level is None:
            return

        if ctx.FILLER() is not None:
            name = "FILLER"
        elif ctx.dataName() is not None:
            name = _clean_name(ctx.dataName().getText())
        else:
            return  # implizites, unbenanntes Item ohne FILLER - kein Testfall deckt das ab

        if level == _STANDALONE_LEVEL:
            parent = None
        else:
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1] if stack else current_fd
            stack.append((level, name))

        redefines_ctx = _first(ctx.dataRedefinesClause())
        occurs_ctx = _first(ctx.dataOccursClause())
        picture_ctx = _first(ctx.dataPictureClause())
        value_ctx = _first(ctx.dataValueClause())

        self.items.append(
            DataItem(
                name=name,
                level=level,
                start_line=_line(ctx.start),
                end_line=_line(ctx.stop),
                parent=parent,
                picture=picture_ctx.pictureString().getText() if picture_ctx is not None else None,
                redefines=_clean_name(redefines_ctx.dataName().getText()) if redefines_ctx is not None else None,
                occurs=_occurs_count(occurs_ctx),
                occurs_depending_on=_occurs_depending_on(occurs_ctx),
                value=_value_text_from_clause(value_ctx),
            )
        )

    # Explizit NICHT default-rekursiv absteigen (kein visitChildren-Aufruf in
    # den obigen Overrides) - eine FD/Section wird komplett über ihre eigene
    # dataDescriptionEntry()-Liste abgearbeitet, kein zweiter Durchlauf nötig.
    def visitProcedureDivision(self, ctx):  # noqa: N802
        return None  # Datenfelder liegen nie in der PROCEDURE DIVISION - abschneiden spart Zeit.


def _first(ctx_list):
    return ctx_list[0] if ctx_list else None


def _occurs_count(ctx) -> int | None:
    if ctx is None:
        return None
    lit = ctx.integerLiteral()
    if lit is None:
        return None
    try:
        return int(lit.getText())
    except ValueError:
        return None


def _occurs_depending_on(ctx) -> str | None:
    if ctx is None:
        return None
    qdn = ctx.qualifiedDataName()
    return _clean_name(qdn.getText()) if qdn is not None else None


def _value_text_from_clause(ctx) -> str | None:
    if ctx is None:
        return None
    intervals = ctx.dataValueInterval()
    if not intervals:
        return None
    return _clean_name(intervals[0].dataValueIntervalFrom().getText())


def _value_text(ctx) -> str | None:
    return _value_text_from_clause(ctx)


def _level_number(ctx: Cobol85Parser.DataDescriptionEntryFormat1Context) -> int | None:
    if ctx.LEVEL_NUMBER_77() is not None:
        return _STANDALONE_LEVEL
    lit = ctx.INTEGERLITERAL()
    if lit is None:
        return None
    try:
        level = int(lit.getText())
    except ValueError:
        return None
    return level if 1 <= level <= 49 else None


def _line(token) -> int:
    return token.line if token is not None else 0


def _clean_name(value: str) -> str:
    if value[:1] in ("'", '"') and value[-1:] == value[:1]:
        return value[1:-1]
    return value
