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

    program, div_errors = divisions_mod.scan(tokens)
    errors.extend(div_errors)

    items, file_descriptors, dd_errors = data_division_mod.parse(program, tokens)
    errors.extend(dd_errors)

    proc_edges, proc_errors = procedure_mod.scan(program, tokens)
    errors.extend(proc_errors)

    copy_edges, copy_errors = copybook_mod.scan(program, tokens, copybook_index)
    errors.extend(copy_errors)

    sql_blocks, sql_edges, sql_errors = sql_mod.scan(program, embedded_blocks, items)
    errors.extend(sql_errors)

    xref_edges, xref_errors = xref_mod.scan(program, tokens, items)
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

    # field_qnames deckt sowohl FD/SD-Namen als auch DataItem-Namen ab -
    # DataItem.parent (data_division.py) referenziert wahlweise eines von
    # beiden, ohne dass am Namen selbst zu erkennen ist, welches gemeint war.
    field_qnames: dict[str, str] = {}
    for fd in file_descriptors:
        qname = _qualify(program.name, fd.name)
        field_qnames[fd.name] = qname
        entities.append(
            Entity(
                type="file_fd",
                name=fd.name,
                start_line=fd.start_line,
                end_line=fd.end_line,
                parent_name=program.name,
                qualified_name=qname,
            )
        )

    for item in items:
        parent_qname = field_qnames.get(item.parent, program.name) if item.parent else program.name
        qname = _qualify(parent_qname, item.name)
        field_qnames[item.name] = qname
        entities.append(
            Entity(
                type="data_item",
                name=item.name,
                start_line=item.start_line,
                end_line=item.end_line,
                parent_name=item.parent or program.name,
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


def _qualify(parent_qname: str | None, name: str) -> str:
    return f"{parent_qname}.{name}" if parent_qname else name


def _fallback_chunks(
    program: CobolProgram, source_lines: list[str], source_format: SourceFormat, chunk_size: int = DEFAULT_CHUNK_SIZE
) -> list[Chunk]:
    chunks: list[Chunk] = []
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
        chunks.append(
            Chunk(
                content="\n".join(current),
                start_line=i + 1,
                end_line=j,
                meta={"program": program.name, "format": source_format, "fallback": True},
            )
        )
        i = j
    return chunks
