import os

import pytest

from cobol.copybook import CopybookIndex, inherited_fields
from cobol.parse import parse_copybook, parse_program
from cobol.profile import BuildProfile

FIXTURES = os.path.join(os.path.dirname(__file__), "cobol_corpus", "fixtures")


def _parse_fixture(name: str, path: str = "x"):
    with open(os.path.join(FIXTURES, name)) as f:
        text = f.read()
    return parse_program(text, path)


def test_minimal_program_produces_program_and_paragraph_entity_plus_one_chunk():
    result = _parse_fixture("01_minimal.cbl")

    assert result.program_name == "MINIMAL"
    assert result.path == "x"
    assert result.source_format == "fixed"

    types = [e.type for e in result.entities]
    assert types == ["program", "paragraph"]

    program_entity = result.entities[0]
    assert program_entity.parent_name is None
    assert program_entity.qualified_name == "MINIMAL"

    paragraph_entity = result.entities[1]
    assert paragraph_entity.name == "MAIN-PARA"
    assert paragraph_entity.parent_name == "MINIMAL"
    assert paragraph_entity.qualified_name == "MINIMAL.MAIN-PARA"

    assert len(result.chunks) == 1
    assert result.chunks[0].meta.get("fallback") is None


def test_data_item_hierarchy_produces_dotted_qualified_names():
    result = _parse_fixture("06_data_qualified.cbl")

    by_name = {e.name: e for e in result.entities if e.type == "data_item"}
    record = by_name["EMPLOYEE-RECORD"]
    field = by_name["EMP-ID"]

    assert record.parent_name == "EMPLOYEE-FILE"
    assert record.qualified_name == "DATAQUAL.EMPLOYEE-FILE.EMPLOYEE-RECORD"
    assert field.parent_name == "EMPLOYEE-RECORD"
    assert field.qualified_name == "DATAQUAL.EMPLOYEE-FILE.EMPLOYEE-RECORD.EMP-ID"
    assert field.meta["picture"] == "9(6)"
    assert field.meta["level"] == 5

    fd_entity = next(e for e in result.entities if e.type == "file_fd")
    assert fd_entity.name == "EMPLOYEE-FILE"
    assert fd_entity.qualified_name == "DATAQUAL.EMPLOYEE-FILE"


def test_repeated_fillers_under_same_group_have_unique_internal_qualified_names():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. REPORTPROG.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-REPORT-HEADER.\n"
        "          05 FILLER PIC X(05) VALUE SPACE.\n"
        "          05 FILLER PIC X(03) VALUE '---'.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n"
    )

    result = parse_program(text, "src/REPORTPROG.cbl")
    fillers = [entity for entity in result.entities if entity.name.upper() == "FILLER"]

    assert [entity.qualified_name for entity in fillers] == [
        "REPORTPROG.WS-REPORT-HEADER.FILLER@6",
        "REPORTPROG.WS-REPORT-HEADER.FILLER@7",
    ]
    assert len({entity.qualified_name for entity in result.entities}) == len(result.entities)


def test_redefines_with_the_same_sibling_name_have_unique_qualified_names():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. EDITPROG.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 CICS-OUTPUT-EDIT-VARS.\n"
        "          10 WS-EDIT-DATE-X PIC X(10).\n"
        "          10 WS-EDIT-DATE-X REDEFINES WS-EDIT-DATE-X PIC 9(10).\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n"
    )

    result = parse_program(text, "src/EDITPROG.cbl")
    dates = [
        entity
        for entity in result.entities
        if entity.type == "data_item" and entity.name == "WS-EDIT-DATE-X"
    ]

    assert [entity.qualified_name for entity in dates] == [
        "EDITPROG.CICS-OUTPUT-EDIT-VARS.WS-EDIT-DATE-X",
        "EDITPROG.CICS-OUTPUT-EDIT-VARS.WS-EDIT-DATE-X@7",
    ]
    assert dates[1].meta["redefines"] == "WS-EDIT-DATE-X"
    assert len({entity.qualified_name for entity in result.entities}) == len(result.entities)


def test_copybook_index_flips_copy_edge_resolution():
    without_index = _parse_fixture("04_copy_replacing.cbl")
    assert without_index.edges[0].resolution == "unresolved"

    with open(os.path.join(FIXTURES, "04_copy_replacing.cbl")) as f:
        text = f.read()
    result = parse_program(text, "x", copybook_index={"WSFIELDS": ["/repo/copy/wsfields.cpy"]})

    assert result.edges[0].resolution == "resolved"
    assert result.edges[0].meta["replacing"] == [{"from": ":TAG:", "to": "WS-FIELD"}]


def test_xref_inherits_copybook_field_without_expanding_source_lines():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. COPYXREF.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       COPY FIELDS.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           DISPLAY SHARED-FIELD.\n"
    )
    index = CopybookIndex(
        {"FIELDS": ["copy/FIELDS.CPY"]},
        fields_by_path={
            "copy/FIELDS.CPY": [
                {
                    "name": "SHARED-FIELD",
                    "parent": "SHARED-RECORD",
                    "qualified_name": "FIELDS.SHARED-RECORD.SHARED-FIELD",
                    "path": "copy/FIELDS.CPY",
                }
            ]
        },
    )

    result = parse_program(text, "MAIN.CBL", index)
    edge = next(e for e in result.edges if e.type == "USES")

    assert edge.resolution == "resolved"
    assert edge.src_start_line == 8
    assert {key: value for key, value in edge.meta.items() if key != "evidence"} == {
        "program": "COPYXREF",
        "copybook_path": "copy/FIELDS.CPY",
        "target_qualified_name": "FIELDS.SHARED-RECORD.SHARED-FIELD",
    }


def test_xref_applies_copy_replacing_to_inherited_field_name():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. COPYREPL.\n"
        "       DATA DIVISION.\n"
        "       COPY FIELDS REPLACING ==:TAG:== BY ==CUSTOMER==.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           DISPLAY CUSTOMER-ID.\n"
    )
    index = CopybookIndex(
        {"FIELDS": ["FIELDS.CPY"]},
        fields_by_path={
            "FIELDS.CPY": [
                {
                    "name": ":TAG:-ID",
                    "parent": ":TAG:-RECORD",
                    "qualified_name": "FIELDS.:TAG:-RECORD.:TAG:-ID",
                    "path": "FIELDS.CPY",
                }
            ]
        },
    )

    result = parse_program(text, "MAIN.CBL", index)
    edge = next(e for e in result.edges if e.type == "USES")
    assert edge.dst_name == ":TAG:-ID"
    assert edge.resolution == "resolved"


def test_xref_does_not_inherit_data_fields_from_procedure_copy():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. PROCEDURECOPY.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           COPY CODEBOOK.\n"
        "           DISPLAY SHARED-FIELD.\n"
    )
    index = CopybookIndex(
        {"CODEBOOK": ["CODEBOOK.CPY"]},
        fields_by_path={
            "CODEBOOK.CPY": [
                {
                    "name": "SHARED-FIELD",
                    "parent": "SHARED-RECORD",
                    "qualified_name": "CODEBOOK.SHARED-RECORD.SHARED-FIELD",
                    "path": "CODEBOOK.CPY",
                }
            ]
        },
    )

    result = parse_program(text, "MAIN.CBL", index)

    assert not [edge for edge in result.edges if edge.type == "USES"]


def test_xref_inherits_transitive_copybook_field_and_composes_replacing():
    """Der Pass-0-Index liefert fuer ein Copybook auch Felder seiner COPYs.
    Die Definitions-Identitaet bleibt dabei beim urspruenglichen Copybook."""
    base_field = {
        "name": ":TAG:-ID",
        "parent": ":TAG:-RECORD",
        "qualified_name": "BASE.:TAG:-RECORD.:TAG:-ID",
        "path": "copy/BASE.CPY",
    }
    wrapper_copy = parse_copybook(
        "       COPY BASE REPLACING ==:TAG:== BY ==CUSTOMER==.\n", "copy/WRAP.CPY"
    )
    wrapper_fields = inherited_fields(
        wrapper_copy.edges,
        CopybookIndex({"BASE": ["copy/BASE.CPY"]}, fields_by_path={"copy/BASE.CPY": [base_field]}),
    )
    assert wrapper_fields[0]["effective_name"] == "CUSTOMER-ID"

    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. NESTEDCOPY.\n"
        "       DATA DIVISION.\n"
        "       COPY WRAP REPLACING ==CUSTOMER== BY ==ACCOUNT==.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           DISPLAY ACCOUNT-ID.\n"
    )
    index = CopybookIndex(
        {"WRAP": ["copy/WRAP.CPY"]},
        fields_by_path={"copy/WRAP.CPY": wrapper_fields},
    )
    result = parse_program(text, "MAIN.CBL", index)
    edge = next(edge for edge in result.edges if edge.type == "USES")

    assert edge.resolution == "resolved"
    assert {key: value for key, value in edge.meta.items() if key != "evidence"} == {
        "program": "NESTEDCOPY",
        "copybook_path": "copy/BASE.CPY",
        "target_qualified_name": "BASE.:TAG:-RECORD.:TAG:-ID",
    }


def test_sql_block_becomes_entity_with_extraction_meta():
    result = _parse_fixture("07_exec_sql.cbl")

    sql_entities = [e for e in result.entities if e.type == "sql_block"]
    assert len(sql_entities) == 4

    declare = sql_entities[0]
    assert declare.name == "SQL-BLOCK@10"
    assert declare.parent_name == "EXECSQL"
    assert declare.qualified_name == "EXECSQL.SQL-BLOCK@10"
    assert declare.meta["statement_type"] == "DECLARE_CURSOR"
    assert declare.meta["cursor_name"] == "EMP-CURSOR"
    assert declare.meta["tables"] == ["EMPLOYEE"]


def test_sql_include_and_file_descriptor_record_are_explicit_relationships():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. RELATIONS.\n"
        "       DATA DIVISION.\n"
        "       FILE SECTION.\n"
        "       FD  ORDERS-FILE.\n"
        "       01  ORDER-RECORD PIC X(20).\n"
        "       WORKING-STORAGE SECTION.\n"
        "           EXEC SQL INCLUDE SQLCA END-EXEC.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n"
    )
    result = parse_program(text, "relations.cbl")

    include = next(entity for entity in result.entities if entity.type == "sql_include")
    assert include.name == "SQLCA"
    include_edge = next(edge for edge in result.edges if edge.type == "INCLUDES")
    assert include_edge.dst_name == "SQLCA"
    assert include_edge.resolution == "resolved"

    layout_edge = next(edge for edge in result.edges if edge.type == "DEFINES")
    assert (layout_edge.src_name, layout_edge.dst_name, layout_edge.resolution) == (
        "ORDERS-FILE",
        "ORDER-RECORD",
        "resolved",
    )


def test_sql_tables_and_cobol_file_io_carry_read_write_direction():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. ACCESS.\n"
        "       DATA DIVISION.\n"
        "       FILE SECTION.\n"
        "       FD  ORDERS-FILE.\n"
        "       01  ORDER-RECORD PIC X(20).\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           OPEN INPUT ORDERS-FILE.\n"
        "           READ ORDERS-FILE INTO ORDER-RECORD.\n"
        "           WRITE ORDERS-FILE FROM ORDER-RECORD.\n"
        "           EXEC SQL\n"
        "               SELECT ORDER-ID INTO :WS-ORDER FROM ORDERS\n"
        "           END-EXEC.\n"
        "           STOP RUN.\n"
    )
    result = parse_program(text, "access.cbl")

    tables = [entity for entity in result.entities if entity.type == "sql_table"]
    assert [(table.name, table.qualified_name) for table in tables] == [
        ("ORDERS", "ACCESS.SQL-TABLE@ORDERS")
    ]
    access_edges = [edge for edge in result.edges if edge.type in {"READS", "WRITES"}]
    assert {(edge.type, edge.dst_name) for edge in access_edges} >= {
        ("READS", "ORDERS-FILE"),
        ("WRITES", "ORDERS-FILE"),
        ("WRITES", "ORDER-RECORD"),
        ("READS", "ORDER-RECORD"),
        ("READS", "ORDERS"),
        ("WRITES", "WS-ORDER"),
    }
    assert any(
        edge.type == "USES"
        and edge.dst_name == "ORDERS-FILE"
        and edge.meta["open_mode"] == "INPUT"
        for edge in result.edges
    )


def test_write_and_rewrite_follow_the_fd_record_layout_not_an_invented_file_name():
    result = parse_program(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. RECORDIO.\n"
        "       DATA DIVISION.\n"
        "       FILE SECTION.\n"
        "       FD  ORDERS-FILE.\n"
        "       01  ORDER-RECORD PIC X(20).\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01  WS-ORDER PIC X(20).\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           WRITE ORDER-RECORD FROM WS-ORDER.\n"
        "           REWRITE ORDER-RECORD FROM WS-ORDER.\n",
        "recordio.cbl",
    )

    record_writes = [
        edge for edge in result.edges
        if edge.type == "WRITES" and edge.dst_name == "ORDER-RECORD"
    ]
    assert len(record_writes) == 2
    assert all(edge.resolution == "resolved" for edge in record_writes)
    assert all(edge.meta["io_target_kind"] == "record" for edge in record_writes)
    assert all(edge.meta["target_qualified_name"] == "RECORDIO.ORDERS-FILE.ORDER-RECORD" for edge in record_writes)

    buffer_reads = [
        edge for edge in result.edges
        if edge.type == "READS" and edge.dst_name == "WS-ORDER"
    ]
    assert len(buffer_reads) == 2
    assert all(edge.resolution == "resolved" for edge in buffer_reads)


def test_edges_combine_call_perform_copy_sql_and_xref():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. COMBINED.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01  WS-FLAG              PIC X(1).\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           MOVE 'Y' TO WS-FLAG.\n"
        "           PERFORM SUB-PARA.\n"
        "           CALL 'OTHERPGM'.\n"
        "       SUB-PARA.\n"
        "           STOP RUN.\n"
    )
    result = parse_program(text, "x")

    edge_types = {e.type for e in result.edges}
    assert edge_types == {"USES", "PERFORM", "CALL"}


def test_broken_file_never_raises_and_falls_back_to_generic_chunking():
    result = _parse_fixture("99_garbage.cbl")

    assert result.program_name == ""
    assert result.errors
    assert result.chunks
    assert all(c.meta.get("fallback") is True for c in result.chunks)
    # Programm-Entity bleibt trotz leerem Namen erhalten - kein Abbruch (F-029).
    assert result.entities[0].type == "program"
    assert result.entities[0].name == ""


def test_no_procedure_division_falls_back_to_generic_chunking_too():
    text = "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. NOPROC.\n"
    result = parse_program(text, "x")

    assert result.chunks


def test_without_profile_source_format_is_flagged_as_heuristic():
    result = _parse_fixture("01_minimal.cbl")
    diag = next(d for d in result.diagnostics if d.code == "SOURCE_FORMAT_HEURISTIC")
    assert diag.phase == "profile"
    assert diag.severity == "info"


def test_profile_source_format_overrides_the_heuristic_without_a_note():
    text = "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. MINIMAL.\n"
    profile = BuildProfile(source_format="free")
    result = parse_program(text, "x", profile=profile)

    assert result.source_format == "free"
    assert not any(d.code == "SOURCE_FORMAT_HEURISTIC" for d in result.diagnostics)


@pytest.mark.parametrize("fmt", ["variable", "extended"])
def test_confirmed_variable_and_extended_profiles_keep_their_format(fmt):
    text = "\n".join(
        (
            "       IDENTIFICATION DIVISION.",
            "       PROGRAM-ID. LONGFMT.",
            "       DATA DIVISION.",
            "       WORKING-STORAGE SECTION.",
            "       01 WS-LONG-FIELD PIC X.",
            "       PROCEDURE DIVISION.",
            "       MAIN-PARA.",
            "           DISPLAY WS-LONG-FIELD.",
        )
    )
    result = parse_program(text, "x", profile=BuildProfile(source_format=fmt))

    assert result.source_format == fmt
    assert result.program_name == "LONGFMT"
    assert result.errors == []
    assert not any(d.code == "SOURCE_FORMAT_HEURISTIC" for d in result.diagnostics)


def test_indented_source_format_directive_is_an_explicit_start_format():
    result_without_profile = _parse_fixture("16_source_format_free_directive_indented.cbl")
    assert result_without_profile.source_format == "free"
    assert result_without_profile.program_name == "INDENTDIR"
    assert result_without_profile.errors == [
        "Keine DATA DIVISION gefunden - Datenfelder nicht durchsucht."
    ]
    assert not any(d.code == "SOURCE_FORMAT_HEURISTIC" for d in result_without_profile.diagnostics)

    with open(os.path.join(FIXTURES, "16_source_format_free_directive_indented.cbl")) as f:
        text = f.read()
    result_with_profile = parse_program(text, "x", profile=BuildProfile(source_format="free"))

    assert result_with_profile.source_format == "free"
    assert result_with_profile.program_name == "INDENTDIR"
    # Divisions werden jetzt gefunden - nur die für diese Datei korrekte
    # Meldung (kein DATA DIVISION vorhanden) bleibt, die O-123-spezifischen
    # Folgefehler (keine Division/kein PROGRAM-ID/keine PROCEDURE DIVISION)
    # sind weg.
    assert result_with_profile.errors == [
        "Keine DATA DIVISION gefunden - Datenfelder nicht durchsucht."
    ]


def test_parse_artifacts_share_source_evidence_and_a_profile_variant():
    text = "\n".join(
        (
            "       IDENTIFICATION DIVISION.",
            "       PROGRAM-ID. EVIDENCE.",
            "       PROCEDURE DIVISION.",
            "       MAIN-PARA.",
            "           CALL 'TARGET'.",
        )
    )
    result = parse_program(text, "src/EVIDENCE.cbl", profile=BuildProfile(source_format="fixed"))

    assert result.variant_key.startswith("profile:")
    artifact_metas = [
        *(entity.meta for entity in result.entities),
        *(edge.meta for edge in result.edges),
    ]
    artifact_metas.extend(chunk.meta for chunk in result.chunks)
    assert artifact_metas
    for meta in artifact_metas:
        evidence = meta["evidence"]
        assert evidence["kind"] == "source"
        assert evidence["source"]["file_path"] == "src/EVIDENCE.cbl"
        assert evidence["variant"]["key"] == result.variant_key
        assert evidence["condition"] is None


def test_debug_mode_changes_only_the_debug_call_edges():
    text = "\n".join(
        (
            "       IDENTIFICATION DIVISION.",
            "       PROGRAM-ID. DEBUGMODE.",
            "       PROCEDURE DIVISION.",
            "       MAIN-PARA.",
            "      D    CALL 'DEBUG-TARGET'.",
            "           CALL 'NORMAL-TARGET'.",
        )
    )

    disabled = parse_program(text, "debug.cbl", profile=BuildProfile(source_format="fixed"))
    enabled = parse_program(
        text, "debug.cbl", profile=BuildProfile(source_format="fixed", debug_mode=True)
    )

    assert [edge.dst_name for edge in disabled.edges if edge.type == "CALL"] == ["NORMAL-TARGET"]
    assert [edge.dst_name for edge in enabled.edges if edge.type == "CALL"] == [
        "DEBUG-TARGET",
        "NORMAL-TARGET",
    ]


def test_unicode_identifier_comparison_does_not_collapse_distinct_data_names():
    text = "\n".join(
        (
            "       IDENTIFICATION DIVISION.",
            "       PROGRAM-ID. UNICODE-NAMES.",
            "       DATA DIVISION.",
            "       WORKING-STORAGE SECTION.",
            "       01 GROUP-A.",
            "          05 WS-Ä PIC X.",
            "          05 WS-ä PIC X.",
            "       PROCEDURE DIVISION.",
            "       MAIN-PARA.",
            "           MOVE 'A' TO WS-Ä.",
            "           MOVE 'a' TO WS-ä.",
        )
    )
    result = parse_program(text, "unicode.cbl", profile=BuildProfile(source_format="fixed"))

    uses = [edge for edge in result.edges if edge.type == "USES"]
    assert [(edge.dst_name, edge.resolution) for edge in uses] == [
        ("WS-Ä", "resolved"),
        ("WS-ä", "resolved"),
    ]


def test_national_and_hex_data_values_keep_their_original_spelling():
    text = "\n".join(
        (
            "       IDENTIFICATION DIVISION.",
            "       PROGRAM-ID. LITERALS.",
            "       DATA DIVISION.",
            "       WORKING-STORAGE SECTION.",
            "       01 WS-NATIONAL PIC N(5) VALUE N'Grüße'.",
            "       01 WS-HEX PIC X(2) VALUE X'F1F2'.",
            "       PROCEDURE DIVISION.",
            "       MAIN-PARA.",
            "           CONTINUE.",
        )
    )
    result = parse_program(text, "literals.cbl", profile=BuildProfile(source_format="fixed"))

    fields = {
        entity.name: entity.meta["value"]
        for entity in result.entities
        if entity.type == "data_item"
    }
    assert fields == {"WS-NATIONAL": "N'Grüße'", "WS-HEX": "X'F1F2'"}


def test_literal_profile_and_invalid_hex_are_visible_on_parse_result():
    text = "\n".join(
        (
            "       IDENTIFICATION DIVISION.",
            "       PROGRAM-ID. INVALID-LITERAL.",
            "       PROCEDURE DIVISION.",
            "       MAIN-PARA.",
            "           DISPLAY X'F1G'.",
        )
    )
    result = parse_program(
        text,
        "invalid.cbl",
        profile=BuildProfile(source_format="fixed", literal_delimiter="quote"),
    )

    assert {item.code for item in result.diagnostics} >= {
        "COBOL_LITERAL_DELIMITER_MISMATCH",
        "COBOL_INVALID_HEX_LITERAL",
    }


def test_carddemo_redefines_and_filler_siblings_preserve_hierarchy_and_uniqueness():
    """CardDemo case (COACTUPC.cbl / COTRTUPC.cbl): WS-EDIT-DATE-X REDEFINES

    WS-EDIT-DATE-X under CICS-OUTPUT-EDIT-VARS must not throw UniqueViolation,
    and elementary FILLER items must not pollute parent_qname of subsequent
    sibling items (O-311).
    """
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. COACTUPC.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       05 CICS-OUTPUT-EDIT-VARS.\n"
        "          10  WS-EDIT-DATE-X                      PIC X(10).\n"
        "          10  FILLER REDEFINES WS-EDIT-DATE-X.\n"
        "              20 WS-EDIT-DATE-X-YEAR              PIC X(4).\n"
        "              20 FILLER                           PIC X(1).\n"
        "              20 WS-EDIT-DATE-MONTH               PIC X(2).\n"
        "              20 FILLER                           PIC X(1).\n"
        "              20 WS-EDIT-DATE-DAY                 PIC X(2).\n"
        "          10  WS-EDIT-DATE-X REDEFINES\n"
        "              WS-EDIT-DATE-X                      PIC 9(10).\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n"
    )

    result = parse_program(text, "app/cbl/COACTUPC.cbl")
    qnames = [e.qualified_name for e in result.entities]
    assert len(set(qnames)) == len(qnames), "All qualified names must be strictly unique"

    dates = [e for e in result.entities if e.type == "data_item" and e.name == "WS-EDIT-DATE-X"]
    assert len(dates) == 2
    assert dates[0].qualified_name == "COACTUPC.CICS-OUTPUT-EDIT-VARS.WS-EDIT-DATE-X"
    assert dates[1].qualified_name == "COACTUPC.CICS-OUTPUT-EDIT-VARS.WS-EDIT-DATE-X@13"
    assert dates[1].parent_qualified_name == "COACTUPC.CICS-OUTPUT-EDIT-VARS"

    # WS-EDIT-DATE-MONTH and WS-EDIT-DATE-DAY must be direct children of FILLER@7,
    # not nested inside the sibling elementary FILLERs at line 9 or 11.
    month = next(e for e in result.entities if e.name == "WS-EDIT-DATE-MONTH")
    day = next(e for e in result.entities if e.name == "WS-EDIT-DATE-DAY")
    assert month.parent_qualified_name == "COACTUPC.CICS-OUTPUT-EDIT-VARS.FILLER@7"
    assert month.qualified_name == "COACTUPC.CICS-OUTPUT-EDIT-VARS.FILLER@7.WS-EDIT-DATE-MONTH"
    assert day.parent_qualified_name == "COACTUPC.CICS-OUTPUT-EDIT-VARS.FILLER@7"
    assert day.qualified_name == "COACTUPC.CICS-OUTPUT-EDIT-VARS.FILLER@7.WS-EDIT-DATE-DAY"


def test_multiple_redefines_and_fillers_on_same_line_disambiguated():
    """Multiple FILLERs or REDEFINES on the same line must be numbered #2, #3 without collisions."""
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. SAMELINE.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 REC.\n"
        "          05 FILLER PIC X. 05 FILLER PIC X.\n"
        "          05 A PIC X.\n"
        "          05 A REDEFINES A PIC 9. 05 A REDEFINES A PIC 9.\n"
        "          05 A REDEFINES A PIC S9.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n"
    )

    result = parse_program(text, "sameline.cbl")
    qnames = [e.qualified_name for e in result.entities]
    assert len(set(qnames)) == len(qnames), "All qualified names must be strictly unique"

    fillers = [e for e in result.entities if e.type == "data_item" and e.name == "FILLER"]
    assert [e.qualified_name for e in fillers] == [
        "SAMELINE.REC.FILLER@6",
        "SAMELINE.REC.FILLER@6#2",
    ]

    items = [e for e in result.entities if e.type == "data_item" and e.name == "A"]
    assert [e.qualified_name for e in items] == [
        "SAMELINE.REC.A",
        "SAMELINE.REC.A@8",
        "SAMELINE.REC.A@8#2",
        "SAMELINE.REC.A@9",
    ]

