import os

from cobol import source_format

FIXTURES = os.path.join(os.path.dirname(__file__), "cobol_corpus", "fixtures")


def _read(name: str) -> str:
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


def test_detect_format_fixed_fixture():
    assert source_format.detect_format(_read("01_minimal.cbl")) == "fixed"


def test_detect_format_free_fixture():
    assert source_format.detect_format(_read("03_free_format.cbl")) == "free"


def test_detect_format_free_via_inline_comment_marker():
    text = "some code *> free-format comment\nmore code\n"
    assert source_format.detect_format(text) == "free"


def test_detect_format_fixed_via_column_seven_indicator():
    text = "000100*THIS IS A FIXED-FORMAT COMMENT LINE\n000200 IDENTIFICATION DIVISION.\n"
    assert source_format.detect_format(text) == "fixed"


def test_split_fixed_minimal_produces_one_logical_line_per_statement():
    lines = source_format.split_logical_lines(_read("01_minimal.cbl"), "fixed")
    assert [l.text for l in lines] == [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. MINIMAL.",
        "PROCEDURE DIVISION.",
        "MAIN-PARA.",
        "DISPLAY 'HELLO'.",
        "STOP RUN.",
    ]
    for l in lines:
        assert l.phys_start_line == l.phys_end_line
        assert not l.is_comment


def test_split_fixed_comment_indicator():
    text = "000100*THIS IS A COMMENT\n000200 DISPLAY 'X'.\n"
    lines = source_format.split_logical_lines(text, "fixed")
    assert lines[0].is_comment is True
    assert lines[0].text == ""
    assert lines[1].text == "DISPLAY 'X'."


def test_split_fixed_debug_indicator_is_excluded_from_code():
    text = "000100D    DISPLAY 'DEBUG-ONLY'.\n000200  DISPLAY 'NORMAL'.\n"
    lines = source_format.split_logical_lines(text, "fixed")
    assert lines[0].is_comment is True
    assert lines[0].is_debug is True
    assert lines[1].text == "DISPLAY 'NORMAL'."


def test_split_fixed_truncates_after_column_72():
    lines = source_format.split_logical_lines(_read("02_fixed_edge.cbl"), "fixed")
    display_line = next(l for l in lines if l.text.startswith("DISPLAY"))
    assert "IGNOREME" not in display_line.text


def test_split_fixed_continuation_merges_into_one_logical_line():
    lines = source_format.split_logical_lines(_read("02_fixed_edge.cbl"), "fixed")
    display_line = next(l for l in lines if l.text.startswith("DISPLAY"))
    assert display_line.phys_start_line == 5
    assert display_line.phys_end_line == 6
    assert display_line.text == (
        "DISPLAY 'LONG-LINE-CONTENT-THAT-RUNS-ALL-THE-WAY-TO-SEVENTY-TWO-AND-BEYOND'."
    )


def test_split_fixed_continuation_drops_leading_resume_quote():
    # Die Continuation-Zeile beginnt mit einem Anfuehrungszeichen, das nur die
    # Fortsetzung des offenen Literals markiert - es darf nicht Teil des
    # Literalwerts werden (sonst zwei Anfuehrungszeichen mitten im Text).
    lines = source_format.split_logical_lines(_read("02_fixed_edge.cbl"), "fixed")
    display_line = next(l for l in lines if l.text.startswith("DISPLAY"))
    assert "''" not in display_line.text


def test_split_free_strips_inline_comment_but_keeps_code():
    lines = source_format.split_logical_lines(_read("03_free_format.cbl"), "free")
    display_line = next(l for l in lines if l.text.startswith("display"))
    assert display_line.text == "display 'hello'"
    assert "Begruessung" not in display_line.text


def test_split_free_each_physical_line_is_its_own_logical_line():
    lines = source_format.split_logical_lines(_read("03_free_format.cbl"), "free")
    for l in lines:
        assert l.phys_start_line == l.phys_end_line
