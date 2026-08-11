from cobol import chunking, divisions, embedded, source_format


def _chunk(text: str, chunk_size: int, min_chunk_size: int, fmt: str = "fixed"):
    lines = source_format.split_logical_lines(text, fmt)
    masked, _ = embedded.mask(lines)
    program, _ = divisions.scan(masked)
    source_lines = text.splitlines()
    return program, chunking.chunk(program, source_lines, fmt, chunk_size, min_chunk_size)


def test_normal_sized_paragraphs_each_get_their_own_chunk():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. NORMSIZE.\n"
        "       PROCEDURE DIVISION.\n"
        "       PARA-A.\n"
        "           DISPLAY 'LINE ONE OF PARA A'.\n"
        "           DISPLAY 'LINE TWO OF PARA A'.\n"
        "       PARA-B.\n"
        "           DISPLAY 'LINE ONE OF PARA B'.\n"
        "           DISPLAY 'LINE TWO OF PARA B'.\n"
        "           STOP RUN.\n"
    )
    _, chunks = _chunk(text, chunk_size=1000, min_chunk_size=10)

    assert len(chunks) == 2
    assert chunks[0].meta["paragraph"] == "PARA-A"
    assert chunks[1].meta["paragraph"] == "PARA-B"
    assert "paragraphs" not in chunks[0].meta
    assert chunks[0].meta["program"] == "NORMSIZE"
    assert chunks[0].meta["format"] == "fixed"
    assert "PARA-A" in chunks[0].content
    assert "PARA-B" in chunks[1].content


def test_tiny_paragraphs_in_same_section_are_merged():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. MERGETINY.\n"
        "       PROCEDURE DIVISION.\n"
        "       SECT-A SECTION.\n"
        "       PARA-A.\n"
        "           STOP RUN.\n"
        "       PARA-B.\n"
        "           STOP RUN.\n"
    )
    _, chunks = _chunk(text, chunk_size=5000, min_chunk_size=1000)

    assert len(chunks) == 1
    assert chunks[0].meta["paragraphs"] == ["PARA-A", "PARA-B"]
    assert "paragraph" not in chunks[0].meta
    assert chunks[0].meta["section"] == "SECT-A"


def test_tiny_paragraphs_in_different_sections_are_not_merged():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. NOSECTMRG.\n"
        "       PROCEDURE DIVISION.\n"
        "       SECT-A SECTION.\n"
        "       PARA-A.\n"
        "           STOP RUN.\n"
        "       SECT-B SECTION.\n"
        "       PARA-B.\n"
        "           STOP RUN.\n"
    )
    _, chunks = _chunk(text, chunk_size=5000, min_chunk_size=1000)

    assert len(chunks) == 2
    assert chunks[0].meta["paragraph"] == "PARA-A"
    assert chunks[0].meta["section"] == "SECT-A"
    assert chunks[1].meta["paragraph"] == "PARA-B"
    assert chunks[1].meta["section"] == "SECT-B"


def test_oversized_paragraph_is_split_without_dropping_or_duplicating_lines():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. BIGPARA.\n"
        "       PROCEDURE DIVISION.\n"
        "       ONLY-PARA.\n"
        "           DISPLAY 'LINE 01'.\n"
        "           DISPLAY 'LINE 02'.\n"
        "           DISPLAY 'LINE 03'.\n"
        "           DISPLAY 'LINE 04'.\n"
        "           STOP RUN.\n"
    )
    program, chunks = _chunk(text, chunk_size=1, min_chunk_size=10)

    paragraph = program.paragraphs[0]
    line_count = paragraph.end_line - paragraph.start_line + 1

    # chunk_size=1 zwingt jede physische Zeile in ein eigenes Stück.
    assert len(chunks) == line_count
    assert all(c.meta["paragraph"] == "ONLY-PARA" for c in chunks)
    assert [c.meta["part"] for c in chunks] == list(range(1, line_count + 1))
    assert all(c.meta["parts"] == line_count for c in chunks)
    assert chunks[0].start_line == paragraph.start_line
    assert chunks[-1].end_line == paragraph.end_line
    for a, b in zip(chunks, chunks[1:]):
        assert b.start_line == a.end_line + 1

    reconstructed = "\n".join(c.content for c in chunks)
    original = "\n".join(text.splitlines()[paragraph.start_line - 1 : paragraph.end_line])
    assert reconstructed == original


def test_split_paragraph_still_flushes_pending_tiny_neighbor_first():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. MIXED.\n"
        "       PROCEDURE DIVISION.\n"
        "       SECT-A SECTION.\n"
        "       TINY-PARA.\n"
        "           STOP RUN.\n"
        "       BIG-PARA.\n"
        "           DISPLAY 'LINE 01'.\n"
        "           DISPLAY 'LINE 02'.\n"
        "           STOP RUN.\n"
    )
    # chunk_size liegt zwischen den beiden Paragraphgrößen: TINY-PARA (38
    # Zeichen) bleibt unter der Schwelle und landet im Merge-Puffer, BIG-PARA
    # (99 Zeichen) überschreitet sie und wird gesplittet - der Puffer muss
    # davor geleert werden, sonst würde TINY-PARA fälschlich mit einem Teil
    # von BIG-PARA verschmelzen.
    _, chunks = _chunk(text, chunk_size=50, min_chunk_size=1000)

    assert chunks[0].meta["paragraph"] == "TINY-PARA"
    assert all(c.meta["paragraph"] == "BIG-PARA" for c in chunks[1:])


def test_no_procedure_division_produces_no_chunks_without_crashing():
    text = "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. NOPROC.\n"
    _, chunks = _chunk(text, chunk_size=1000, min_chunk_size=200)
    assert chunks == []
