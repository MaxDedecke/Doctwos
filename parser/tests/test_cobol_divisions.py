import os

from cobol import divisions, embedded, source_format
from cobol.model import Division, EntryPoint, Paragraph, Section

FIXTURES = os.path.join(os.path.dirname(__file__), "cobol_corpus", "fixtures")


def _program(name: str, fmt: str = "fixed"):
    """O-138: divisions.scan() liefert seither eine Liste von CobolProgram
    (mehrere/verschachtelte Programme pro Datei) - alle bestehenden Tests
    hier prüfen Ein-Programm-Fixtures, deshalb entpackt der Helper auf das
    einzige Element. Mehrprogramm-Verhalten selbst wird unten separat
    getestet (test_multiple_top_level_programs_stay_separate() u.a.)."""
    with open(os.path.join(FIXTURES, name)) as f:
        text = f.read()
    lines = source_format.split_logical_lines(text, fmt)
    masked, _ = embedded.mask(lines)
    programs, errors, diagnostics = divisions.scan(masked)
    return programs[0], errors, diagnostics


def _scan_text(text: str, fmt: str = "fixed"):
    lines = source_format.split_logical_lines(text, fmt)
    masked, _ = embedded.mask(lines)
    return divisions.scan(masked)


def test_minimal_program_structure():
    program, errors, _ = _program("01_minimal.cbl")
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
    program, errors, _ = _program("02_fixed_edge.cbl")
    assert errors == []
    assert program.paragraphs == [Paragraph("MAIN-PARA", None, 4, 7)]


def test_free_format_program_structure():
    program, errors, _ = _program("03_free_format.cbl", fmt="free")
    assert errors == []
    assert program.name == "freeformat"
    assert program.paragraphs == [Paragraph("main-para", None, 4, 6)]


def test_embedded_block_does_not_close_enclosing_paragraph_early():
    # Bug gefunden beim Bauen dieses Tests: der Platzhalter EMBEDDED-BLOCK-CICS
    # gefolgt vom Punkt nach END-EXEC sieht strukturell genauso aus wie ein
    # Paragraphen-Header (WORD PERIOD) - divisions.py muss ihn ausnehmen.
    program, errors, _ = _program("08_exec_cics.cbl")
    assert errors == []
    assert program.paragraphs == [Paragraph("MAIN-PARA", None, 4, 9)]


def test_data_division_section_is_recognized():
    program, errors, _ = _program("09_dynamic_call.cbl")
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
    program, errors, _ = _program("10_perform_thru.cbl")
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
    programs, errors, _ = _scan_text(text)
    program = programs[0]

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
    programs, errors, _ = _scan_text(text)
    program = programs[0]

    assert program.name == ""
    assert "PROGRAM-ID nicht gefunden." in errors


def test_bare_reserved_verbs_do_not_open_spurious_paragraphs():
    # Bug gefunden über CobolTestRepository/LEGACYKONV.cbl: ein alleinstehendes
    # "GOBACK." (zweimal im selben Programm) bzw. "EXIT." sieht strukturell
    # wie ein Paragraphen-Kopf aus (WORD PERIOD) und wurde als solcher
    # gewertet - beim zweiten "GOBACK." kollidierte der qualified_name beim
    # Persistieren am Unique-Constraint uq_code_entities_source_qname.
    program, errors, _ = _program("11_bare_verb_statements.cbl")
    assert errors == []
    assert program.paragraphs == [
        Paragraph("MAIN-PARA", None, 4, 6),
        Paragraph("FIRST-EXIT-PARA", None, 7, 8),
        Paragraph("FIRST-EXIT-PARA-ENDE", None, 9, 10),
        Paragraph("SECOND-PARA", None, 11, 13),
        Paragraph("THIRD-PARA", None, 14, 16),
    ]


def test_empty_token_stream_does_not_crash():
    programs, errors, diagnostics = divisions.scan([])
    assert len(programs) == 1
    assert programs[0].name == ""
    assert programs[0].divisions == []
    assert errors != []
    assert diagnostics == []


def test_multiple_top_level_programs_stay_separate():
    # O-138: zwei eigenständige Compilation Units (kein Nesting) in
    # derselben Datei - gleicher Paragraphenname in beiden darf nicht
    # zusammenfallen, jedes Programm behält seine eigene Paragraphenliste.
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. FIRSTPGM.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n"
        "       END PROGRAM FIRSTPGM.\n"
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. SECONDPGM.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n"
        "       END PROGRAM SECONDPGM.\n"
    )
    programs, errors, _ = _scan_text(text)

    assert errors == []
    assert [p.name for p in programs] == ["FIRSTPGM", "SECONDPGM"]
    assert [p.parent_name for p in programs] == [None, None]
    for program in programs:
        assert [p.name for p in program.paragraphs] == ["MAIN-PARA"]


def test_nested_program_gets_its_own_scope_and_parent_link():
    # O-138: NESTED ist textuell innerhalb OUTER (programUnit* in der
    # Grammatik) - eigene Paragraphenliste, aber mit parent_name = OUTER.
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. OUTER.\n"
        "       PROCEDURE DIVISION.\n"
        "       OUTER-PARA.\n"
        "           CALL 'NESTED'.\n"
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. NESTED.\n"
        "       PROCEDURE DIVISION.\n"
        "       OUTER-PARA.\n"
        "           STOP RUN.\n"
        "       END PROGRAM NESTED.\n"
        "       END PROGRAM OUTER.\n"
    )
    programs, errors, _ = _scan_text(text)

    assert errors == []
    by_name = {p.name: p for p in programs}
    assert set(by_name) == {"OUTER", "NESTED"}
    assert by_name["OUTER"].parent_name is None
    assert by_name["NESTED"].parent_name == "OUTER"
    # Derselbe Paragraphenname in beiden Programmen bleibt getrennt gezählt.
    assert [p.name for p in by_name["OUTER"].paragraphs] == ["OUTER-PARA"]
    assert [p.name for p in by_name["NESTED"].paragraphs] == ["OUTER-PARA"]


def test_entry_statement_is_attributed_to_its_own_program():
    from cobol import procedure
    from cobol.lexer import tokenize

    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. WITHENTRY.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           ENTRY 'ALTENTRY' USING WS-PARM.\n"
        "           STOP RUN.\n"
    )
    programs, errors, _ = _scan_text(text)
    program = programs[0]
    tokens = tokenize(embedded.mask(source_format.split_logical_lines(text, "fixed"))[0])
    procedure.scan(program, tokens)

    assert errors == []
    assert program.entry_points == [EntryPoint("ALTENTRY", "MAIN-PARA", 5, 5)]
