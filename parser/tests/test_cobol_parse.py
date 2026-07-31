import os

from cobol.copybook import CopybookIndex
from cobol.parse import parse_program

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
        fields_by_path={"copy/FIELDS.CPY": [{
            "name": "SHARED-FIELD", "parent": "SHARED-RECORD",
            "qualified_name": "FIELDS.SHARED-RECORD.SHARED-FIELD",
            "path": "copy/FIELDS.CPY",
        }]},
    )

    result = parse_program(text, "MAIN.CBL", index)
    edge = next(e for e in result.edges if e.type == "USES")

    assert edge.resolution == "resolved"
    assert edge.src_start_line == 8
    assert edge.meta == {
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
        fields_by_path={"FIELDS.CPY": [{
            "name": ":TAG:-ID", "parent": ":TAG:-RECORD",
            "qualified_name": "FIELDS.:TAG:-RECORD.:TAG:-ID", "path": "FIELDS.CPY",
        }]},
    )

    result = parse_program(text, "MAIN.CBL", index)
    edge = next(e for e in result.edges if e.type == "USES")
    assert edge.dst_name == ":TAG:-ID"
    assert edge.resolution == "resolved"


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
    assert all(c.meta.get("fallback") is True for c in result.chunks)
