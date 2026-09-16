"""O-136: globales REPLACE/REPLACE OFF (nicht an ein COPY gebunden)."""

from cobol import replace, source_format
from cobol.parse import parse_program


def _lines(text: str, fmt: str = "fixed"):
    return source_format.split_logical_lines(text, fmt)


def _texts(lines) -> list[str]:
    return [line.text for line in lines]


def test_no_replace_statement_leaves_lines_untouched():
    text = "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. NOREPL.\n"
    lines = _lines(text)
    out = replace.apply(lines)
    assert out == lines


def test_plain_pseudo_text_substitutes_only_between_replace_and_off():
    text = (
        "       01  :TAG:-ID PIC 9(5).\n"
        "       REPLACE ==:TAG:== BY ==CUSTOMER==.\n"
        "       01  :TAG:-NAME PIC X(10).\n"
        "       REPLACE OFF.\n"
        "       01  :TAG:-DATE PIC 9(8).\n"
    )
    out = _texts(replace.apply(_lines(text)))
    assert out[0] == "01  :TAG:-ID PIC 9(5).", "vor dem REPLACE unveraendert"
    assert out[1].strip() == "", "die REPLACE-Anweisung selbst wird unsichtbar"
    assert out[2] == "01  CUSTOMER-NAME PIC X(10).", "innerhalb des Bereichs ersetzt"
    assert out[3].strip() == "", "REPLACE OFF wird ebenfalls unsichtbar"
    assert out[4] == "01  :TAG:-DATE PIC 9(8).", "nach OFF wieder unveraendert"


def test_substitution_never_touches_literal_content():
    text = "       REPLACE ==:TAG:== BY ==CUSTOMER==.\n       DISPLAY 'KEEP :TAG: LITERAL'.\n"
    out = _texts(replace.apply(_lines(text)))
    assert out[1] == "DISPLAY 'KEEP :TAG: LITERAL'."


def test_leading_qualifier_replaces_only_the_matched_prefix():
    text = "       REPLACE LEADING ==WS-== BY ==NEW-==.\n       MOVE WS-A TO WS-B.\n"
    out = _texts(replace.apply(_lines(text)))
    assert out[1] == "MOVE NEW-A TO NEW-B."


def test_trailing_qualifier_replaces_only_the_matched_suffix():
    text = "       REPLACE TRAILING ==-OLD== BY ==-NEW==.\n       MOVE FIELD-OLD TO OTHER-OLD.\n"
    out = _texts(replace.apply(_lines(text)))
    assert out[1] == "MOVE FIELD-NEW TO OTHER-NEW."


def test_a_second_replace_statement_supersedes_the_first_instead_of_stacking():
    text = "       REPLACE ==A== BY ==B==.\n       REPLACE ==C== BY ==D==.\n       MOVE A TO C.\n"
    out = _texts(replace.apply(_lines(text)))
    # A ist nicht mehr aktiv (vom zweiten REPLACE abgeloest), nur C->D gilt.
    assert out[2] == "MOVE A TO D."


def test_replace_inside_an_inactive_conditional_branch_has_no_effect():
    from cobol import conditional

    # Freies Format, weil >>IF nur so als eigene Direktivenzeile erkannt wird
    # (siehe 17_conditional_compilation_true_branch.cbl) - fuer diesen Test
    # unerheblich, replace.py arbeitet formatunabhaengig auf LogicalLines.
    text = ">>IF 1 = 2\nREPLACE ==A== BY ==B==.\n>>END-IF\nMOVE A TO WS-A.\n"
    lines = source_format.split_logical_lines(text, "free")
    lines = conditional.apply(lines, {})
    out = _texts(replace.apply(lines))
    assert out[-1] == "MOVE A TO WS-A."


def test_end_to_end_definitions_and_uses_reflect_the_substitution_original_text_stays_visible():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. REPLTEST.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       REPLACE ==:TAG:== BY ==CUSTOMER==.\n"
        "       01  :TAG:-ID PIC 9(5).\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           DISPLAY :TAG:-ID.\n"
        "           STOP RUN.\n"
    )
    result = parse_program(text, "x")

    assert result.errors == []
    field = next(e for e in result.entities if e.type == "data_item")
    assert field.name == "CUSTOMER-ID"
    uses = next(e for e in result.edges if e.type == "USES")
    assert uses.dst_name == "CUSTOMER-ID"
    assert uses.resolution == "resolved"
    # Der angezeigte Chunk-Text bleibt der Originaltext, keine stille
    # Expansion (Abnahme O-136).
    chunk = result.chunks[0]
    assert ":TAG:-ID" in chunk.content
    assert "CUSTOMER-ID" not in chunk.content
