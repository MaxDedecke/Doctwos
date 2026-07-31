import os

from cobol import embedded, source_format

FIXTURES = os.path.join(os.path.dirname(__file__), "cobol_corpus", "fixtures")


def _logical_lines(name: str, fmt: str = "fixed"):
    with open(os.path.join(FIXTURES, name)) as f:
        text = f.read()
    return source_format.split_logical_lines(text, fmt)


def test_mask_finds_exec_cics_block():
    lines = _logical_lines("08_exec_cics.cbl")
    masked, blocks = embedded.mask(lines)

    assert len(blocks) == 1
    block = blocks[0]
    assert block.dialect == "CICS"
    assert block.start_line == 5
    assert block.end_line == 8
    assert "SEND TEXT FROM('HELLO. WORLD.')" in block.content
    assert "END-EXEC." in block.content


def test_mask_replaces_block_with_single_placeholder_line():
    lines = _logical_lines("08_exec_cics.cbl")
    masked, _ = embedded.mask(lines)

    # 9 LogicalLines im Original, davon 4 (EXEC..END-EXEC) zu einer verschmolzen
    assert len(masked) == 9 - 4 + 1


def test_mask_placeholder_has_no_period_and_no_exec_word():
    lines = _logical_lines("08_exec_cics.cbl")
    masked, _ = embedded.mask(lines)
    placeholder = next(l for l in masked if l.phys_start_line == 5)

    assert "." not in placeholder.segments[0].text
    words = placeholder.segments[0].text.split()
    assert "EXEC" not in [w.upper() for w in words]


def test_mask_preserves_trailing_period_after_end_exec():
    lines = _logical_lines("08_exec_cics.cbl")
    masked, _ = embedded.mask(lines)
    placeholder = next(l for l in masked if l.phys_start_line == 5)

    assert placeholder.text.endswith(".")


def test_mask_without_exec_block_is_a_noop():
    lines = _logical_lines("01_minimal.cbl")
    masked, blocks = embedded.mask(lines)

    assert blocks == []
    assert [l.text for l in masked] == [l.text for l in lines]


def test_mask_missing_end_exec_does_not_crash():
    lines = _logical_lines("08_exec_cics.cbl")
    truncated = lines[:6]  # bricht mitten im EXEC-Block ab, kein END-EXEC

    masked, blocks = embedded.mask(truncated)

    assert len(blocks) == 1
    assert blocks[0].end_line == truncated[-1].phys_end_line
