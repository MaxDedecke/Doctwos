"""
parser/cobol/parse.py
========================
F-020…034/F-041: Orchestrierung der gesamten Pipeline zu einem `ParseResult`
für **eine** Datei, komplett in-memory — kein DB-Zugriff (Plan §6.3,
docs/ENTSCHEIDUNGEN.md E-6). Reihenfolge:

    source_format.detect_format/split_logical_lines
      -> embedded.mask
      -> lexer.tokenize
      -> divisions.scan
      -> data_division.parse
      -> procedure.scan
      -> copybook.scan
      -> sql.scan
      -> xref.scan
      -> chunking.chunk

`chunking.chunk()` gehört formal zu AP-4 (E-6), wird hier aber schon
aufgerufen, weil `ParseResult.chunks` laut §6.3 Teil des Rückgabewerts ist
und die Funktion selbst keine DB-Anbindung braucht — dieselbe Begründung wie
beim Vorziehen von `chunking.py` selbst.

F-029 „kein Abbruch": eine Datei ohne einen einzigen PROCEDURE-DIVISION-
Paragraphen (z.B. kaputt oder unvollständig, siehe `99_garbage.cbl`) liefert
bei `chunking.chunk()` eine leere Liste — die Funktion chunkt ausschließlich
Paragraphen. Damit die Datei trotzdem durchsuchbar bleibt (Plan §6.1 Regel 2,
"generisches Text-Chunking"), springt dann `_fallback_chunks()` ein: dieselbe
zeilenweise Packstrategie wie `chunking._split_paragraph()`, nur über die
gesamte Datei statt über einen Paragraphen.
"""

from __future__ import annotations

import os

from . import copybook as copybook_mod
from . import data_division as data_division_mod
from . import divisions as divisions_mod
from . import embedded as embedded_mod
from . import lexer as lexer_mod
from . import procedure as procedure_mod
from . import source_format as source_format_mod
from . import sql as sql_mod
from . import xref as xref_mod
from .chunking import DEFAULT_CHUNK_SIZE
from .chunking import chunk as chunk_paragraphs
from .copybook import CopybookIndex
from .model import (
    Chunk,
    CobolProgram,
    DataItem,
    Division,
    Entity,
    FileDescriptor,
    ParseResult,
    SourceFormat,
    SqlBlock,
)


def parse_program(text: str, path: str, copybook_index: CopybookIndex | None = None) -> ParseResult:
    errors: list[str] = []

    source_format = source_format_mod.detect_format(text)
    logical_lines = source_format_mod.split_logical_lines(text, source_format)
    masked_lines, embedded_blocks = embedded_mod.mask(logical_lines)
    tokens = lexer_mod.tokenize(masked_lines)

    # Phase 3 (E-11): divisions.py/data_division.py bauen sich ihren eigenen
    # ANTLR-Parse-Tree aus denselben masked_lines - procedure.py/copybook.py/
    # xref.py bleiben unverändert auf dem flachen Token-Strom von lexer.py.
    program, div_errors = divisions_mod.scan(masked_lines)
    errors.extend(div_errors)

    items, file_descriptors, dd_errors = data_division_mod.parse(program, masked_lines)
    errors.extend(dd_errors)

    proc_edges, proc_errors = procedure_mod.scan(program, tokens)
    errors.extend(proc_errors)

    copy_edges, copy_errors = copybook_mod.scan(program, tokens, copybook_index)
    errors.extend(copy_errors)

    sql_blocks, sql_edges, sql_errors = sql_mod.scan(program, embedded_blocks, items)
    errors.extend(sql_errors)

    data_division_index = next(
        (index for index, division in enumerate(program.divisions) if division.name == "DATA"),
        None,
    )
    data_division = (
        program.divisions[data_division_index]
        if data_division_index is not None else None
    )
    data_end_line = (
        program.divisions[data_division_index + 1].start_line - 1
        if data_division_index is not None and data_division_index + 1 < len(program.divisions)
        else data_division.end_line if data_division is not None else None
    )
    data_copy_edges = [
        edge for edge in copy_edges
        if data_division is not None
        and data_division.start_line <= edge.src_start_line <= data_end_line
    ]
    inherited_fields = copybook_mod.inherited_fields(data_copy_edges, copybook_index)
    xref_edges, xref_errors = xref_mod.scan(program, tokens, items, inherited_fields)
    errors.extend(xref_errors)

    edges = [*proc_edges, *copy_edges, *sql_edges, *xref_edges]
    entities = _build_entities(program, items, file_descriptors, sql_blocks)

    source_lines = text.splitlines()
    chunks = chunk_paragraphs(program, source_lines, source_format)
    if not chunks:
        chunks = _fallback_chunks(program, source_lines, source_format)

    return ParseResult(
        program_name=program.name,
        path=path,
        source_format=source_format,
        entities=entities,
        edges=edges,
        chunks=chunks,
        errors=errors,
    )


def _build_entities(
    program: CobolProgram,
    items: list[DataItem],
    file_descriptors: list[FileDescriptor],
    sql_blocks: list[SqlBlock],
) -> list[Entity]:
    entities: list[Entity] = []

    entities.append(
        Entity(
            type="program",
            name=program.name,
            start_line=program.start_line,
            end_line=program.end_line,
            parent_name=None,
            qualified_name=program.name,
        )
    )

    section_qnames: dict[str, str] = {}
    for section in program.sections:
        qname = _qualify(program.name, section.name)
        section_qnames[section.name] = qname
        entities.append(
            Entity(
                type="section",
                name=section.name,
                start_line=section.start_line,
                end_line=section.end_line,
                parent_name=program.name,
                qualified_name=qname,
            )
        )

    for paragraph in program.paragraphs:
        parent_qname = section_qnames.get(paragraph.section, program.name) if paragraph.section else program.name
        entities.append(
            Entity(
                type="paragraph",
                name=paragraph.name,
                start_line=paragraph.start_line,
                end_line=paragraph.end_line,
                parent_name=paragraph.section or program.name,
                qualified_name=_qualify(parent_qname, paragraph.name),
            )
        )

    entities.extend(_build_field_entities(program.name, items, file_descriptors))

    for block in sql_blocks:
        entities.append(
            Entity(
                type="sql_block",
                name=block.name,
                start_line=block.start_line,
                end_line=block.end_line,
                parent_name=program.name,
                qualified_name=_qualify(program.name, block.name),
                meta={
                    "statement_type": block.statement_type,
                    "tables": block.tables,
                    "host_variables": block.host_variables,
                    "cursor_name": block.cursor_name,
                },
            )
        )

    return entities


def _build_field_entities(
    root_name: str, items: list[DataItem], file_descriptors: list[FileDescriptor]
) -> list[Entity]:
    """FD/SD- und DataItem-Entities unter einer Wurzel (Programm- oder
    Copybook-Name) - gemeinsam genutzt von _build_entities() und
    parse_copybook(), weil beide dieselbe Gruppenhierarchie in
    qualified_names auflösen müssen (E-2: Copybook-Felder brauchen exakt
    dieselbe Qualified-Name-Form wie Programm-Felder, sonst funktioniert die
    XREF-Vererbung über COPY-Grenzen hinweg nicht).

    field_qnames deckt sowohl FD/SD-Namen als auch DataItem-Namen ab -
    DataItem.parent (data_division.py) referenziert wahlweise eines von
    beiden, ohne dass am Namen selbst zu erkennen ist, welches gemeint war.
    """
    entities: list[Entity] = []
    field_qnames: dict[str, str] = {}
    qname_occurrences: dict[str, int] = {}

    for fd in file_descriptors:
        qname = _qualify(root_name, fd.name)
        field_qnames[fd.name] = qname
        entities.append(
            Entity(
                type="file_fd",
                name=fd.name,
                start_line=fd.start_line,
                end_line=fd.end_line,
                parent_name=root_name,
                qualified_name=qname,
            )
        )

    for item in items:
        parent_qname = field_qnames.get(item.parent, root_name) if item.parent else root_name
        qname = _qualify(parent_qname, item.name)
        # FILLER ist in COBOL absichtlich namenlos und darf beliebig oft als
        # Geschwister unter derselben Gruppe vorkommen. Der Klartextname allein
        # ist deshalb kein stabiler Entity-Schlüssel. Ohne Disambiguierung
        # kollidieren zwei FILLER beim Persistieren mit
        # uq_code_entities_source_qname und vergiften anschließend die gesamte
        # SQLAlchemy-Transaktion. Die physische Startzeile ist bereits Teil der
        # Parser-Invariante und macht den internen Schlüssel eindeutig, während
        # der sichtbare Entity-Name weiterhin exakt "FILLER" bleibt. Ein Zähler
        # deckt auch mehrere Beschreibungen auf derselben physischen Zeile ab.
        if item.name.upper() == "FILLER":
            base_qname = f"{qname}@{item.start_line}"
            occurrence = qname_occurrences.get(base_qname, 0) + 1
            qname_occurrences[base_qname] = occurrence
            qname = base_qname if occurrence == 1 else f"{base_qname}#{occurrence}"
        field_qnames[item.name] = qname
        entities.append(
            Entity(
                type="data_item",
                name=item.name,
                start_line=item.start_line,
                end_line=item.end_line,
                parent_name=item.parent or root_name,
                qualified_name=qname,
                meta={
                    "level": item.level,
                    "picture": item.picture,
                    "redefines": item.redefines,
                    "occurs": item.occurs,
                    "occurs_depending_on": item.occurs_depending_on,
                    "value": item.value,
                },
            )
        )

    return entities


def _qualify(parent_qname: str | None, name: str) -> str:
    return f"{parent_qname}.{name}" if parent_qname else name


def _pack_whole_file(source_lines: list[str], chunk_size: int) -> list[tuple[str, int, int]]:
    """Zeilenweises, nicht-überlappendes Packen der gesamten Datei in
    (content, start_line, end_line)-Tripel - dieselbe Strategie wie
    chunking._split_paragraph(), nur ohne Paragraphengrenzen. Gemeinsam
    genutzt von _fallback_chunks() (F-029) und parse_copybook() (Copybooks
    haben keine PROCEDURE-DIVISION-Paragraphen, an denen chunking.chunk()
    entlang chunken könnte)."""
    packed: list[tuple[str, int, int]] = []
    n = len(source_lines)
    i = 0
    while i < n:
        current: list[str] = []
        current_len = 0
        j = i
        while j < n:
            line = source_lines[j]
            if current_len > 0 and current_len + len(line) > chunk_size:
                break
            current.append(line)
            current_len += len(line) + 1
            j += 1
        if j == i:
            current.append(source_lines[j])
            j += 1
        packed.append(("\n".join(current), i + 1, j))
        i = j
    return packed


def _fallback_chunks(
    program: CobolProgram, source_lines: list[str], source_format: SourceFormat, chunk_size: int = DEFAULT_CHUNK_SIZE
) -> list[Chunk]:
    return [
        Chunk(
            content=content,
            start_line=start_line,
            end_line=end_line,
            meta={"program": program.name, "format": source_format, "fallback": True},
        )
        for content, start_line, end_line in _pack_whole_file(source_lines, chunk_size)
    ]


def parse_copybook(
    text: str,
    path: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    copybook_index: CopybookIndex | None = None,
) -> ParseResult:
    """F-022/E-2: eine Copybook-Datei als eigenständige Entity mit eigenen
    data_item-Kindern parsen - eigene Zeilennummern, NIE in den Programmtext
    expandiert (CLAUDE.md „Zeilennummern sind heilig"). Analog zu
    parse_program(), aber ohne IDENTIFICATION/PROCEDURE DIVISION: ein
    Copybook ist laut COBOL-Grammatik reine Datenbeschreibung, meist ohne
    jeden DIVISION-Header. data_division.parse() braucht dennoch ein
    CobolProgram mit einer DATA-Division, um deren Zeilenbereich zu kennen -
    hier synthetisch über die gesamte Datei aufgespannt.

    name (= Entity-Typ "copybook") ist der Dateiname ohne Endung, uppercased
    - das ist der Bezeichner, über den COPY-Statements ihn referenzieren
    (copybook.py löst genauso auf, siehe CopybookIndex)."""
    errors: list[str] = []

    source_format = source_format_mod.detect_format(text)
    logical_lines = source_format_mod.split_logical_lines(text, source_format)
    masked_lines, _ = embedded_mod.mask(logical_lines)
    tokens = lexer_mod.tokenize(masked_lines)

    name = _copybook_name(path)
    source_lines = text.splitlines()

    if not tokens:
        errors.append("Keine Tokens gefunden - leere oder nicht lesbare Copybook-Datei.")
        return ParseResult(program_name=name, path=path, source_format=source_format, errors=errors)

    start_line = tokens[0].phys_line
    end_line = tokens[-1].phys_line
    synthetic = CobolProgram(
        name=name,
        start_line=start_line,
        end_line=end_line,
        divisions=[Division("DATA", start_line, end_line)],
    )

    items, file_descriptors, dd_errors = data_division_mod.parse(synthetic, masked_lines)
    errors.extend(dd_errors)
    copy_edges, copy_errors = copybook_mod.scan(synthetic, tokens, copybook_index)
    errors.extend(copy_errors)

    entities = [
        Entity(type="copybook", name=name, start_line=start_line, end_line=end_line, qualified_name=name)
    ]
    entities.extend(_build_field_entities(name, items, file_descriptors))

    chunks = [
        Chunk(content=content, start_line=s, end_line=e, meta={"copybook": name, "format": source_format})
        for content, s, e in _pack_whole_file(source_lines, chunk_size)
    ]

    return ParseResult(
        program_name=name,
        path=path,
        source_format=source_format,
        entities=entities,
        edges=copy_edges,
        chunks=chunks,
        errors=errors,
    )


def _copybook_name(path: str) -> str:
    stem = os.path.basename(path).partition(".")[0]
    return stem.upper()
