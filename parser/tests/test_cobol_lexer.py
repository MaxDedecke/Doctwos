import os

from cobol import lexer, source_format

FIXTURES = os.path.join(os.path.dirname(__file__), "cobol_corpus", "fixtures")


def _tokens(name: str, fmt: str = "fixed"):
    with open(os.path.join(FIXTURES, name)) as f:
        text = f.read()
    lines = source_format.split_logical_lines(text, fmt)
    return lexer.tokenize(lines)


def test_tokenize_minimal_kinds_and_values():
    toks = _tokens("01_minimal.cbl")
    kinds_values = [(t.kind, t.value) for t in toks]
    assert kinds_values == [
        ("WORD", "IDENTIFICATION"), ("WORD", "DIVISION"), ("PERIOD", "."),
        ("WORD", "PROGRAM-ID"), ("PERIOD", "."),
        ("WORD", "MINIMAL"), ("PERIOD", "."),
        ("WORD", "PROCEDURE"), ("WORD", "DIVISION"), ("PERIOD", "."),
        ("WORD", "MAIN-PARA"), ("PERIOD", "."),
        ("WORD", "DISPLAY"), ("LITERAL", "'HELLO'"), ("PERIOD", "."),
        ("WORD", "STOP"), ("WORD", "RUN"), ("PERIOD", "."),
    ]


def test_tokenize_area_a_vs_area_b_in_fixed_format():
    toks = _tokens("01_minimal.cbl")
    program_id = next(t for t in toks if t.value == "PROGRAM-ID")
    assert program_id.area == "A"
    display = next(t for t in toks if t.value == "DISPLAY")
    assert display.area == "B"


def test_tokenize_free_format_has_no_area():
    toks = _tokens("03_free_format.cbl", fmt="free")
    assert all(t.area is None for t in toks)


def test_tokenize_literal_with_doubled_quote_escape():
    lines = source_format.split_logical_lines("000100  DISPLAY 'IT''S FINE'.\n", "fixed")
    toks = lexer.tokenize(lines)
    literal = next(t for t in toks if t.kind == "LITERAL")
    assert literal.value == "'IT''S FINE'"


def test_tokenize_pseudo_text_for_replacing():
    lines = source_format.split_logical_lines(
        "000100  COPY WSFIELDS REPLACING ==:TAG:== BY ==WS-FIELD==.\n", "fixed"
    )
    toks = lexer.tokenize(lines)
    pseudo = [t for t in toks if t.kind == "PSEUDO_TEXT"]
    assert [t.value for t in pseudo] == ["==:TAG:==", "==WS-FIELD=="]


def test_tokenize_number_vs_word():
    lines = source_format.split_logical_lines(
        "000100  05 WS-FIELD PIC 9(3) VALUE 3.14.\n", "fixed"
    )
    toks = lexer.tokenize(lines)
    kinds_values = [(t.kind, t.value) for t in toks]
    assert ("NUMBER", "05") in kinds_values
    assert ("NUMBER", "3.14") in kinds_values
    # das satzabschliessende '.' bleibt ein eigenes PERIOD-Token, nicht Teil
    # der Dezimalzahl
    assert kinds_values[-1] == ("PERIOD", ".")


def test_tokenize_leading_digit_identifier_stays_one_word():
    lines = source_format.split_logical_lines("000100  MOVE 1D-ARRAY TO X.\n", "fixed")
    toks = lexer.tokenize(lines)
    assert ("WORD", "1D-ARRAY") in [(t.kind, t.value) for t in toks]


def test_tokenize_numbered_paragraph_name_stays_one_word():
    lines = source_format.split_logical_lines(
        "000100  PERFORM 010-SYSTEMDATEN-LADEN.\n", "fixed"
    )
    toks = lexer.tokenize(lines)
    kinds_values = [(t.kind, t.value) for t in toks]
    assert ("WORD", "010-SYSTEMDATEN-LADEN") in kinds_values
    assert not any(kind == "NUMBER" for kind, _ in kinds_values)


def test_tokenize_umlaut_identifier_stays_one_word():
    lines = source_format.split_logical_lines(
        "000100  PERFORM 020-DATEIEN-ÖFFNEN.\n", "fixed"
    )
    toks = lexer.tokenize(lines)
    assert ("WORD", "020-DATEIEN-ÖFFNEN") in [(t.kind, t.value) for t in toks]


def test_tokenize_exec_block_becomes_single_word_token():
    from cobol import embedded

    with open(os.path.join(FIXTURES, "08_exec_cics.cbl")) as f:
        text = f.read()
    lines = source_format.split_logical_lines(text, "fixed")
    masked, _ = embedded.mask(lines)
    toks = lexer.tokenize(masked)
    values = [t.value for t in toks]
    assert "EMBEDDED-BLOCK-CICS" in values
    assert "SEND" not in values
