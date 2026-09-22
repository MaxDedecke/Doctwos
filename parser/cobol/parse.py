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

from . import antlr_bridge
from . import copybook as copybook_mod
from . import conditional as conditional_mod
from . import data_division as data_division_mod
from . import divisions as divisions_mod
from . import embedded as embedded_mod
from . import exec as exec_mod
from . import io as io_mod
from . import lexer as lexer_mod
from . import procedure as procedure_mod
from . import replace as replace_mod
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
    ExecBlock,
    Entity,
    FileDescriptor,
    ParseDiagnostic,
    ParsedEdge,
    ParseResult,
    SourceFormat,
    SqlBlock,
    program_own_range,
)
from .profile import BuildProfile
from .names import canonical_identifier
from core.evidence import source_evidence, variant_key


def _determine_source_format(
    text: str, profile: BuildProfile | None
) -> tuple[SourceFormat, list[ParseDiagnostic]]:
    """O-121: ein Profil-Wert ist eine bestätigte Tatsache, die Heuristik
    (`source_format.detect_format()`) bleibt eine unbestätigte Vermutung -
    Abnahme "keine automatische Dialekterkennung als Gewissheit ausgeben".
    Ohne Profil-Bestätigung markiert eine eigene Diagnose das Ergebnis
    entsprechend, statt es kommentarlos wie eine Tatsache zu behandeln."""
    if profile is not None and profile.source_format is not None:
        return profile.source_format, []

    detected = source_format_mod.detect_format(text)
    if source_format_mod.initial_format_directive(text) is not None:
        # Eine anfängliche SOURCE-FORMAT-Direktive ist eine ausdrückliche
        # Quellvorgabe, keine bloße Vermutung. Spätere Direktiven werden bei
        # split_logical_lines() je Zeile angewandt.
        return detected, []
    diagnostic = ParseDiagnostic(
        code="SOURCE_FORMAT_HEURISTIC",
        severity="info",
        phase="profile",
        message=(
            f"Quellformat '{detected}' heuristisch erkannt, kein Buildprofil "
            "oder eine anfängliche SOURCE-FORMAT-Direktive hat es bestätigt "
            "(siehe O-121)."
        ),
        line=0,
        column=0,
    )
    return detected, [diagnostic]


def parse_program(
    text: str,
    path: str,
    copybook_index: CopybookIndex | None = None,
    profile: BuildProfile | None = None,
) -> ParseResult:
    errors: list[str] = []

    source_format, profile_diagnostics = _determine_source_format(text, profile)
    logical_lines = source_format_mod.split_logical_lines(
        text,
        source_format,
        profile.source_columns if profile is not None else None,
        profile.debug_mode if profile is not None else False,
    )
    logical_lines = conditional_mod.apply(
        logical_lines, profile.defines if profile is not None else {}
    )
    # O-136: globales REPLACE/REPLACE OFF (nicht an ein COPY gebunden) - läuft
    # nach conditional.py (ein REPLACE in einem sicher inaktiven >>IF-Zweig
    # bleibt wirkungslos) und vor embedded.py (REPLACE gilt laut COBOL85 auch
    # für eingebetteten SQL/CICS-Text). Ersetzt nur die für Struktur/Xref
    # relevante Sicht - der an chunking.py/_attach_source_evidence gehende
    # Originaltext (text.splitlines()) bleibt unverändert.
    logical_lines = replace_mod.apply(logical_lines)
    masked_lines, embedded_blocks = embedded_mod.mask(logical_lines)
    tokens = lexer_mod.tokenize(masked_lines)
    lexer_diagnostics = lexer_mod.diagnostics(
        tokens, profile.literal_delimiter if profile is not None else "both"
    )

    # Phase 3 (E-11): divisions.py/data_division.py bauen sich ihren eigenen
    # ANTLR-Parse-Tree aus denselben masked_lines - procedure.py/copybook.py/
    # xref.py bleiben unverändert auf dem flachen Token-Strom von lexer.py.
    # Beide liefern deshalb potenziell dieselben ANTLR-Diagnosen ein zweites
    # Mal - antlr_bridge.consolidate_diagnostics() dedupliziert (O-119).
    #
    # O-138: eine Datei kann mehrere bzw. verschachtelte Programme enthalten
    # (`programUnit+`/`programUnit*` in der Grammatik) - divisions_mod.scan()
    # liefert deshalb eine LISTE von CobolProgram, jedes mit ausschließlich
    # seinen eigenen Paragraphen/Sections/Feldern. Alle nachfolgenden Scans
    # laufen je Programm einmal, damit gleichnamige Paragraphen/Felder
    # verschiedener Programme nie vermischt werden (Abnahme O-138).
    programs, div_errors, div_diagnostics = divisions_mod.scan(masked_lines)
    errors.extend(div_errors)

    source_lines = text.splitlines()
    entities: list[Entity] = []
    edges: list[ParsedEdge] = []
    chunks: list[Chunk] = []
    dd_diagnostics_all: list[ParseDiagnostic] = []
    single_program = len(programs) == 1

    for program in programs:
        # own_range grenzt COPY-/EXEC-SQL-Vorkommen bei mehreren Programmen
        # auf die eigenen Divisions DIESES Programms ein (sonst würde ein
        # COPY/EXEC SQL aus Programm A auch bei Programm B noch einmal
        # auftauchen). None im Einzelprogramm-Normalfall - siehe
        # copybook.py/sql.py-Docstrings für die Begründung.
        own_range = None if single_program else program_own_range(program)

        items, file_descriptors, dd_errors, dd_diagnostics = data_division_mod.parse(
            program, masked_lines
        )
        errors.extend(dd_errors)
        dd_diagnostics_all.extend(dd_diagnostics)

        proc_edges, proc_errors = procedure_mod.scan(program, tokens)
        errors.extend(proc_errors)

        copy_edges, copy_errors = copybook_mod.scan(program, tokens, copybook_index, own_range)
        errors.extend(copy_errors)

        sql_blocks, sql_edges, sql_errors = sql_mod.scan(program, embedded_blocks, items, own_range)
        errors.extend(sql_errors)
        sql_include_edges = _sql_include_edges(program, sql_blocks)
        exec_blocks, exec_edges, exec_errors = exec_mod.scan(program, embedded_blocks, own_range)
        errors.extend(exec_errors)

        data_division_index = next(
            (index for index, division in enumerate(program.divisions) if division.name == "DATA"),
            None,
        )
        data_division = (
            program.divisions[data_division_index] if data_division_index is not None else None
        )
        data_end_line = (
            program.divisions[data_division_index + 1].start_line - 1
            if data_division_index is not None and data_division_index + 1 < len(program.divisions)
            else data_division.end_line
            if data_division is not None
            else None
        )
        data_copy_edges = [
            edge
            for edge in copy_edges
            if data_division is not None
            and data_division.start_line <= edge.src_start_line <= data_end_line
        ]
        inherited_fields = copybook_mod.inherited_fields(data_copy_edges, copybook_index)
        xref_edges, xref_errors = xref_mod.scan(program, tokens, items, inherited_fields)
        errors.extend(xref_errors)

        fd_edges = data_division_mod.file_descriptor_edges(program, file_descriptors, items)
        io_edges = io_mod.scan(program, tokens, file_descriptors, items)
        edges.extend(
            [
                *proc_edges,
                *copy_edges,
                *sql_edges,
                *sql_include_edges,
                *exec_edges,
                *fd_edges,
                *io_edges,
                *xref_edges,
            ]
        )
        entities.extend(_build_entities(program, items, file_descriptors, sql_blocks, exec_blocks))

        program_chunks = chunk_paragraphs(program, source_lines, source_format)
        if not program_chunks:
            # Einzelprogramm-Normalfall (siehe divisions_mod.scan()): der
            # Fallback deckt wie vor O-138 die GESAMTE Datei ab, nicht nur
            # program.start_line/end_line - unverändertes Verhalten für alle
            # bestehenden Golden Files (F-029, z.B. 99_garbage.cbl).
            fallback_bounds = None if single_program else (program.start_line, program.end_line)
            program_chunks = _fallback_chunks(program, source_lines, source_format, fallback_bounds)
        chunks.extend(program_chunks)

    result = ParseResult(
        program_name=programs[0].name,
        path=path,
        source_format=source_format,
        variant_key=variant_key(profile),
        entities=entities,
        edges=edges,
        chunks=chunks,
        errors=errors,
        diagnostics=profile_diagnostics
        + lexer_diagnostics
        + antlr_bridge.consolidate_diagnostics(div_diagnostics, dd_diagnostics_all),
    )
    _attach_source_evidence(result, profile, logical_lines)
    return result


def _build_entities(
    program: CobolProgram,
    items: list[DataItem],
    file_descriptors: list[FileDescriptor],
    sql_blocks: list[SqlBlock],
    exec_blocks: list[ExecBlock],
) -> list[Entity]:
    entities: list[Entity] = []

    # O-138: ein echt verschachteltes Unterprogramm bekommt einen
    # elternqualifizierten qualified_name ("AUSSEN.INNEN") - sonst würden
    # zwei gleichnamige Unterprogramme unter verschiedenen Elternprogrammen
    # derselben Datei kollidieren (uq_code_entities_source_qname). Eigene
    # Sections/Paragraphen/Felder bleiben trotzdem am einfachen `program.name`
    # verankert (siehe unten) - das ist die Invariante, auf die sich
    # structure_persist.py::_belongs_to_program() verlässt.
    entities.append(
        Entity(
            type="program",
            name=program.name,
            start_line=program.start_line,
            end_line=program.end_line,
            parent_name=program.parent_name,
            qualified_name=_qualify(program.parent_name, program.name),
            parent_qualified_name=program.parent_name,
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
                parent_qualified_name=program.name,
            )
        )

    for paragraph in program.paragraphs:
        parent_qname = (
            section_qnames.get(paragraph.section, program.name)
            if paragraph.section
            else program.name
        )
        entities.append(
            Entity(
                type="paragraph",
                name=paragraph.name,
                start_line=paragraph.start_line,
                end_line=paragraph.end_line,
                parent_name=paragraph.section or program.name,
                qualified_name=_qualify(parent_qname, paragraph.name),
                parent_qualified_name=parent_qname,
            )
        )

    entities.extend(_build_field_entities(program.name, items, file_descriptors))

    for entry in program.entry_points:
        entities.append(
            Entity(
                type="entry",
                name=entry.name,
                start_line=entry.start_line,
                end_line=entry.end_line,
                parent_name=program.name,
                qualified_name=_qualify(program.name, entry.name),
                parent_qualified_name=program.name,
                meta={"paragraph": entry.paragraph},
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
                parent_qualified_name=program.name,
                meta={
                    "statement_type": block.statement_type,
                    "tables": block.tables,
                    "host_variables": block.host_variables,
                    "cursor_name": block.cursor_name,
                    "include_name": block.include_name,
                },
            )
        )
        if block.include_name:
            include_qname = f"{_qualify(program.name, block.name)}.INCLUDE@{block.start_line}"
            entities.append(
                Entity(
                    type="sql_include",
                    name=block.include_name,
                    start_line=block.start_line,
                    end_line=block.end_line,
                    parent_name=block.name,
                    qualified_name=include_qname,
                    parent_qualified_name=_qualify(program.name, block.name),
                    meta={"statement_type": "INCLUDE"},
                )
            )

        for table in block.tables:
            table_qname = f"{program.name}.SQL-TABLE@{table.upper()}"
            if any(entity.qualified_name == table_qname for entity in entities):
                continue
            entities.append(
                Entity(
                    type="sql_table",
                    name=table,
                    start_line=block.start_line,
                    end_line=block.end_line,
                    parent_name=program.name,
                    qualified_name=table_qname,
                    parent_qualified_name=program.name,
                    meta={"table_name": table},
                )
            )

    # Blocks, operations and resources are separate entities: each is a
    # stable deep-link target, while edges preserve the source relationship.
    seen_resource_qnames: set[str] = set()
    for block in exec_blocks:
        block_qname = _qualify(program.name, block.name)
        entities.append(
            Entity(
                type="exec_block",
                name=block.name,
                start_line=block.start_line,
                end_line=block.end_line,
                parent_name=program.name,
                qualified_name=block_qname,
                parent_qualified_name=program.name,
                meta={"dialect": block.dialect, "operation": block.operation},
            )
        )
        entities.append(
            Entity(
                type="exec_operation",
                name=block.operation,
                start_line=block.start_line,
                end_line=block.end_line,
                parent_name=block.name,
                qualified_name=f"{block_qname}.{block.operation}@{block.start_line}",
                parent_qualified_name=block_qname,
                meta={"dialect": block.dialect},
            )
        )
        for resource in block.resources:
            resource_qname = (
                f"{program.name}.EXEC-RESOURCE@{block.dialect}:{resource.kind}:{resource.name}"
            )
            if resource_qname in seen_resource_qnames:
                continue
            seen_resource_qnames.add(resource_qname)
            entities.append(
                Entity(
                    type="exec_resource",
                    name=resource.name,
                    start_line=block.start_line,
                    end_line=block.end_line,
                    parent_name=program.name,
                    qualified_name=resource_qname,
                    parent_qualified_name=program.name,
                    meta={
                        "dialect": block.dialect,
                        "resource_kind": resource.kind,
                        "dynamic": resource.dynamic,
                    },
                )
            )

    return entities


def _sql_include_edges(program: CobolProgram, blocks: list[SqlBlock]) -> list[ParsedEdge]:
    """Make ``EXEC SQL INCLUDE member`` a first-class local relationship."""
    edges: list[ParsedEdge] = []
    for block in blocks:
        if not block.include_name:
            continue
        block_qname = _qualify(program.name, block.name)
        edges.append(
            ParsedEdge(
                type="INCLUDES",
                src_name=block_qname,
                dst_name=block.include_name,
                resolution="resolved",
                src_start_line=block.start_line,
                src_end_line=block.end_line,
                scope=program.name,
                meta={
                    "program": program.name,
                    "language": "cobol",
                    "target_qualified_name": f"{block_qname}.INCLUDE@{block.start_line}",
                },
            )
        )
    return edges


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
                parent_qualified_name=root_name,
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
        if canonical_identifier(item.name) == "FILLER":
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
                parent_qualified_name=parent_qname,
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


def _pack_whole_file(
    source_lines: list[str],
    chunk_size: int,
    bounds: tuple[int, int] | None = None,
) -> list[tuple[str, int, int]]:
    """Zeilenweises, nicht-überlappendes Packen in (content, start_line,
    end_line)-Tripel - dieselbe Strategie wie chunking._split_paragraph(),
    nur ohne Paragraphengrenzen. Gemeinsam genutzt von _fallback_chunks()
    (F-029) und parse_copybook() (Copybooks haben keine PROCEDURE-DIVISION-
    Paragraphen, an denen chunking.chunk() entlang chunken könnte).

    bounds ist ein 1-basiertes, inklusives (start_line, end_line) - Default
    None packt wie vor O-138 die GESAMTE `source_lines`-Liste; O-138 nutzt
    das, um den F-029-Fallback bei mehreren Programmen pro Datei auf den
    Zeilenbereich EINES Programms einzugrenzen, statt versehentlich auch die
    Nachbarprogramme mit einzupacken."""
    start_line, end_line = bounds if bounds is not None else (1, len(source_lines))
    packed: list[tuple[str, int, int]] = []
    n = end_line
    i = start_line - 1
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
    program: CobolProgram,
    source_lines: list[str],
    source_format: SourceFormat,
    bounds: tuple[int, int] | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[Chunk]:
    return [
        Chunk(
            content=content,
            start_line=start_line,
            end_line=end_line,
            meta={"program": program.name, "format": source_format, "fallback": True},
        )
        for content, start_line, end_line in _pack_whole_file(source_lines, chunk_size, bounds)
    ]


def parse_copybook(
    text: str,
    path: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    copybook_index: CopybookIndex | None = None,
    profile: BuildProfile | None = None,
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

    source_format, profile_diagnostics = _determine_source_format(text, profile)
    logical_lines = source_format_mod.split_logical_lines(
        text,
        source_format,
        profile.source_columns if profile is not None else None,
        profile.debug_mode if profile is not None else False,
    )
    logical_lines = conditional_mod.apply(
        logical_lines, profile.defines if profile is not None else {}
    )
    logical_lines = replace_mod.apply(logical_lines)  # O-136, siehe parse_program()
    masked_lines, _ = embedded_mod.mask(logical_lines)
    tokens = lexer_mod.tokenize(masked_lines)
    lexer_diagnostics = lexer_mod.diagnostics(
        tokens, profile.literal_delimiter if profile is not None else "both"
    )

    name = _copybook_name(path)
    source_lines = text.splitlines()

    if not tokens:
        errors.append("Keine Tokens gefunden - leere oder nicht lesbare Copybook-Datei.")
        return ParseResult(
            program_name=name,
            path=path,
            source_format=source_format,
            variant_key=variant_key(profile),
            errors=errors,
            diagnostics=profile_diagnostics + lexer_diagnostics,
        )

    start_line = tokens[0].phys_line
    end_line = tokens[-1].phys_line
    synthetic = CobolProgram(
        name=name,
        start_line=start_line,
        end_line=end_line,
        divisions=[Division("DATA", start_line, end_line)],
    )

    items, file_descriptors, dd_errors, dd_diagnostics = data_division_mod.parse(
        synthetic, masked_lines
    )
    errors.extend(dd_errors)
    copy_edges, copy_errors = copybook_mod.scan(synthetic, tokens, copybook_index)
    errors.extend(copy_errors)

    entities = [
        Entity(
            type="copybook",
            name=name,
            start_line=start_line,
            end_line=end_line,
            qualified_name=name,
            parent_qualified_name=None,
        )
    ]
    entities.extend(_build_field_entities(name, items, file_descriptors))

    chunks = [
        Chunk(
            content=content,
            start_line=s,
            end_line=e,
            meta={"copybook": name, "format": source_format},
        )
        for content, s, e in _pack_whole_file(source_lines, chunk_size)
    ]

    result = ParseResult(
        program_name=name,
        path=path,
        source_format=source_format,
        variant_key=variant_key(profile),
        entities=entities,
        edges=copy_edges,
        chunks=chunks,
        errors=errors,
        diagnostics=profile_diagnostics
        + lexer_diagnostics
        + antlr_bridge.consolidate_diagnostics(dd_diagnostics),
    )
    _attach_source_evidence(result, profile, logical_lines)
    return result


def _attach_source_evidence(
    result: ParseResult, profile: BuildProfile | None, logical_lines: list
) -> None:
    """Macht Herkunft/Variante auf Entity, Kante und Chat-Chunk identisch sichtbar."""
    for entity in result.entities:
        entity.meta = {
            **entity.meta,
            "evidence": source_evidence(
                path=result.path,
                start_line=entity.start_line,
                end_line=entity.end_line,
                profile=profile,
            ),
        }
    for edge in result.edges:
        condition = next(
            (
                line.condition
                for line in logical_lines
                if line.phys_start_line <= edge.src_start_line <= line.phys_end_line
            ),
            None,
        )
        edge.meta = {
            **edge.meta,
            "evidence": source_evidence(
                path=result.path,
                start_line=edge.src_start_line,
                end_line=edge.src_end_line,
                profile=profile,
            ),
        }
        edge.meta["evidence"]["condition"] = condition
        if condition:
            edge.meta["condition"] = condition
    for chunk in result.chunks:
        chunk.meta = {
            **chunk.meta,
            "evidence": source_evidence(
                path=result.path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                profile=profile,
            ),
        }


def _copybook_name(path: str) -> str:
    stem = os.path.basename(path).partition(".")[0]
    return canonical_identifier(stem)
