import os

import pytest

from cobol import source_format
from cobol.lexer import tokenize
from cobol.profile import SourceColumns

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


def test_detect_format_honors_an_indented_initial_source_directive():
    assert (
        source_format.detect_format(
            "       >>SOURCE FORMAT FREE\n       IDENTIFICATION DIVISION.\n"
        )
        == "free"
    )


def test_detect_format_honors_initial_directive_after_a_sequence_number():
    assert source_format.detect_format("000100 >>SOURCE FORMAT VARIABLE\n") == "variable"


def test_source_directives_switch_format_after_the_directive_line():
    text = "\n".join(
        (
            "       BEFORE-SWITCH.",
            "       >>SOURCE FORMAT FREE",
            "AFTER-FREE-SWITCH.",
            ">>SOURCE FORMAT IS FIXED",
            "       AFTER-FIXED-SWITCH.",
        )
    )
    lines = source_format.split_logical_lines(text, "fixed")

    assert [(line.text, line.source_format) for line in lines if not line.is_comment] == [
        ("BEFORE-SWITCH.", "fixed"),
        ("AFTER-FREE-SWITCH.", "free"),
        ("AFTER-FIXED-SWITCH.", "fixed"),
    ]
    assert [line.phys_start_line for line in lines if line.is_comment] == [2, 4]


def test_variable_and_extended_formats_retain_text_beyond_column_72():
    text = "       " + "X" * 180 + ".\n"
    variable = source_format.split_logical_lines(text, "variable")
    extended = source_format.split_logical_lines(text, "extended")
    fixed = source_format.split_logical_lines(text, "fixed")

    assert variable[0].text == "X" * 180 + "."
    assert extended[0].text == "X" * 180 + "."
    assert len(fixed[0].text) == 65  # Spalten 8–72


@pytest.mark.parametrize("fmt", ["variable", "extended"])
def test_variable_and_extended_formats_keep_fixed_style_literal_continuations(fmt):
    text = "       DISPLAY '" + "X" * 80 + "\n" + "      -'TAIL'.\n"
    lines = source_format.split_logical_lines(text, fmt)

    assert len(lines) == 1
    assert lines[0].source_format == fmt
    assert lines[0].phys_start_line == 1
    assert lines[0].phys_end_line == 2
    assert lines[0].text == "DISPLAY '" + "X" * 80 + "TAIL'."


def test_profile_columns_override_the_fixed_boundaries_and_preserve_positions():
    columns = SourceColumns(
        sequence_end=1, indicator_column=2, area_a_start=3, area_b_start=5, code_end=40
    )
    lines = source_format.split_logical_lines("  PROGRAM-ID. CUSTOM.\n", "fixed", columns)

    assert lines[0].text == "PROGRAM-ID. CUSTOM."
    assert lines[0].segments[0].col_start == 2


def test_split_fixed_minimal_produces_one_logical_line_per_statement():
    lines = source_format.split_logical_lines(_read("01_minimal.cbl"), "fixed")
    assert [line.text for line in lines] == [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. MINIMAL.",
        "PROCEDURE DIVISION.",
        "MAIN-PARA.",
        "DISPLAY 'HELLO'.",
        "STOP RUN.",
    ]
    for line in lines:
        assert line.phys_start_line == line.phys_end_line
        assert not line.is_comment


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


def test_split_fixed_debug_indicator_is_code_only_in_confirmed_debug_mode():
    text = "000100D    DISPLAY 'DEBUG-ONLY'.\n000200     DISPLAY 'NORMAL'.\n"

    disabled = source_format.split_logical_lines(text, "fixed")
    enabled = source_format.split_logical_lines(text, "fixed", debug_mode=True)

    assert [line.text for line in disabled if not line.is_comment] == ["DISPLAY 'NORMAL'."]
    assert [line.text for line in enabled] == ["DISPLAY 'DEBUG-ONLY'.", "DISPLAY 'NORMAL'."]
    assert enabled[0].is_debug is True


def test_columnar_compiler_cards_are_not_cobol_tokens():
    text = "       CBL DEBUG\n       PROCESS FLAG(I)\n      $SET SOURCEFORMAT\n       DISPLAY 'NORMAL'.\n"
    lines = source_format.split_logical_lines(text, "fixed")

    assert [line.text for line in lines if not line.is_comment] == ["DISPLAY 'NORMAL'."]
    assert [line.directive for line in lines if line.is_comment] == [
        "CBL DEBUG",
        "PROCESS FLAG(I)",
        "SET SOURCEFORMAT",
    ]


def test_fixed_tabs_are_expanded_to_display_columns_before_slicing():
    lines = source_format.split_logical_lines("\tDISPLAY 'TAB'.\n", "fixed")

    assert lines[0].text == "DISPLAY 'TAB'."
    assert lines[0].segments[0].col_start == 8


def test_split_fixed_truncates_after_column_72():
    lines = source_format.split_logical_lines(_read("02_fixed_edge.cbl"), "fixed")
    display_line = next(line for line in lines if line.text.startswith("DISPLAY"))
    assert "IGNOREME" not in display_line.text


def test_split_fixed_continuation_merges_into_one_logical_line():
    lines = source_format.split_logical_lines(_read("02_fixed_edge.cbl"), "fixed")
    display_line = next(line for line in lines if line.text.startswith("DISPLAY"))
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
    display_line = next(line for line in lines if line.text.startswith("DISPLAY"))
    assert "''" not in display_line.text


def test_continuation_handles_escaped_quotes_and_keeps_one_literal_token():
    text = "       DISPLAY 'DON''T-\n      -'STOP'.\n"
    lines = source_format.split_logical_lines(text, "fixed")
    literals = [token for token in tokenize(lines) if token.kind == "LITERAL"]

    assert lines[0].text == "DISPLAY 'DON''T-STOP'."
    assert [(token.value, token.phys_line) for token in literals] == [("'DON''T-STOP'", 1)]


def test_word_continuation_is_one_word_token_at_its_original_start_position():
    text = "       CALL TARGET-\n      -NAME.\n"
    lines = source_format.split_logical_lines(text, "fixed")
    words = [token for token in tokenize(lines) if token.kind == "WORD"]

    assert lines[0].text == "CALL TARGET-NAME."
    assert [(token.value, token.phys_line, token.col) for token in words] == [
        ("CALL", 1, 7),
        ("TARGET-NAME", 1, 12),
    ]


def test_split_free_strips_inline_comment_but_keeps_code():
    lines = source_format.split_logical_lines(_read("03_free_format.cbl"), "free")
    display_line = next(line for line in lines if line.text.startswith("display"))
    assert display_line.text == "display 'hello'"
    assert "Begruessung" not in display_line.text


def test_free_comment_marker_inside_a_literal_is_not_a_comment():
    text = "display 'literal *> remains'. *> actual comment\n"
    lines = source_format.split_logical_lines(text, "free")
    literals = [token.value for token in tokenize(lines) if token.kind == "LITERAL"]

    assert lines[0].text == "display 'literal *> remains'."
    assert literals == ["'literal *> remains'"]


def test_free_compiler_cards_are_not_cobol_tokens():
    text = "CBL DEBUG\nPROCESS FLAG(I)\n$SET SOURCEFORMAT\ndisplay 'NORMAL'.\n"
    lines = source_format.split_logical_lines(text, "free")

    assert [line.text for line in lines if not line.is_comment] == ["display 'NORMAL'."]


def test_split_free_each_physical_line_is_its_own_logical_line():
    lines = source_format.split_logical_lines(_read("03_free_format.cbl"), "free")
    for line in lines:
        assert line.phys_start_line == line.phys_end_line
