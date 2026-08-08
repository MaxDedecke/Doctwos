import os

from cobol import divisions, embedded, lexer, source_format
from cobol.model import Division, Paragraph, Section

FIXTURES = os.path.join(os.path.dirname(__file__), "cobol_corpus", "fixtures")


def _program(name: str, fmt: str = "fixed"):
    with open(os.path.join(FIXTURES, name)) as f:
        text = f.read()
    lines = source_format.split_logical_lines(text, fmt)
    masked, _ = embedded.mask(lines)
    tokens = lexer.tokenize(masked)
    return divisions.scan(tokens)


def test_minimal_program_structure():
    program, errors = _program("01_minimal.cbl")
    assert errors == []
    assert program.name == "MINIMAL"
    assert program.start_line == 1
    assert program.end_line == 6
    assert program.divisions == [
        Division("IDENTIFICATION", 1, 2),
        Division("PROCEDURE", 3, 6),
    ]
    assert program.sections == []
    assert program.paragraphs == [Paragraph("MAIN-PARA", None, 4, 6)]


def test_continuation_line_does_not_split_paragraph():
    # 02_fixed_edge.cbl: DISPLAY-Literal über eine Continuation-Zeile hinweg -
    # MAIN-PARA muss trotzdem bis zur letzten Zeile (STOP RUN.) reichen.
    program, errors = _program("02_fixed_edge.cbl")
    assert errors == []
    assert program.paragraphs == [Paragraph("MAIN-PARA", None, 4, 7)]


def test_free_format_program_structure():
    program, errors = _program("03_free_format.cbl", fmt="free")
    assert errors == []
    assert program.name == "freeformat"
    assert program.paragraphs == [Paragraph("main-para", None, 4, 6)]


def test_embedded_block_does_not_close_enclosing_paragraph_early():
    # Bug gefunden beim Bauen dieses Tests: der Platzhalter EMBEDDED-BLOCK-CICS
    # gefolgt vom Punkt nach END-EXEC sieht strukturell genauso aus wie ein
    # Paragraphen-Header (WORD PERIOD) - divisions.py muss ihn ausnehmen.
    program, errors = _program("08_exec_cics.cbl")
    assert errors == []
    assert program.paragraphs == [Paragraph("MAIN-PARA", None, 4, 9)]


def test_data_division_section_is_recognized():
    program, errors = _program("09_dynamic_call.cbl")
    assert errors == []
    assert program.name == "DYNCALL"
    assert program.divisions == [
        Division("IDENTIFICATION", 1, 2),
        Division("DATA", 3, 5),
        Division("PROCEDURE", 6, 11),
    ]
    assert program.sections == [Section("WORKING-STORAGE", "DATA", 4, 5)]
    assert program.paragraphs == [Paragraph("MAIN-PARA", None, 7, 11)]


def test_multiple_paragraphs_get_exact_line_ranges():
    program, errors = _program("10_perform_thru.cbl")
    assert errors == []
    assert program.paragraphs == [
        Paragraph("MAIN-PARA", None, 4, 7),
        Paragraph("INIT-PARA", None, 8, 9),
        Paragraph("MIDDLE-PARA", None, 10, 11),
        Paragraph("CLEANUP-PARA", None, 12, 13),
    ]


def test_paragraph_inside_procedure_section_records_section_name():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. SECDEMO.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-SECTION SECTION.\n"
        "       MAIN-PARA.\n"
        "           DISPLAY 'HELLO'.\n"
        "           STOP RUN.\n"
    )
    lines = source_format.split_logical_lines(text, "fixed")
    masked, _ = embedded.mask(lines)
    tokens = lexer.tokenize(masked)
    program, errors = divisions.scan(tokens)

    assert errors == []
    assert program.sections == [Section("MAIN-SECTION", "PROCEDURE", 4, 7)]
    assert program.paragraphs == [Paragraph("MAIN-PARA", "MAIN-SECTION", 5, 7)]


def test_missing_program_id_is_reported_but_does_not_crash():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n"
    )
    lines = source_format.split_logical_lines(text, "fixed")
    masked, _ = embedded.mask(lines)
    tokens = lexer.tokenize(masked)
    program, errors = divisions.scan(tokens)

    assert program.name == ""
    assert "PROGRAM-ID nicht gefunden." in errors


def test_bare_reserved_verbs_do_not_open_spurious_paragraphs():
    # Bug gefunden über CobolTestRepository/LEGACYKONV.cbl: ein alleinstehendes
    # "GOBACK." (zweimal im selben Programm) bzw. "EXIT." sieht strukturell
    # wie ein Paragraphen-Kopf aus (WORD PERIOD) und wurde als solcher
    # gewertet - beim zweiten "GOBACK." kollidierte der qualified_name beim
    # Persistieren am Unique-Constraint uq_code_entities_source_qname.
    program, errors = _program("11_bare_verb_statements.cbl")
    assert errors == []
    assert program.paragraphs == [
        Paragraph("MAIN-PARA", None, 4, 6),
        Paragraph("FIRST-EXIT-PARA", None, 7, 8),
        Paragraph("FIRST-EXIT-PARA-ENDE", None, 9, 10),
        Paragraph("SECOND-PARA", None, 11, 13),
        Paragraph("THIRD-PARA", None, 14, 16),
    ]


def test_empty_token_stream_does_not_crash():
    program, errors = divisions.scan([])
    assert program.name == ""
    assert program.divisions == []
    assert errors != []
