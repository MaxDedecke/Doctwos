"""
O-083: CodeParser.chunk_file() bekommt optionale boundary_lines -- ein neuer
Chunk soll bevorzugt an einer erkannten Section-Grenze beginnen statt
ausschließlich an der Zeichenzahl-Schwelle. Reine Unit-Tests ohne DB.
"""

from code_parser import CodeParser


def _lines(n: int, width: int = 20) -> list[str]:
    return [f"Zeile {i}".ljust(width, "x") for i in range(1, n + 1)]


def test_without_boundary_lines_behaves_like_before():
    content = "\n".join(_lines(10))
    parser = CodeParser("text")
    without = parser.chunk_file(content, chunk_size=1000, overlap_size=150)
    with_empty = parser.chunk_file(
        content, chunk_size=1000, overlap_size=150, boundary_lines=frozenset()
    )
    assert without == with_empty


def test_cuts_before_boundary_line_even_under_chunk_size():
    lines = _lines(6, width=20)
    content = "\n".join(lines)
    # chunk_size ist groß genug, dass ohne Grenzen alles in einen Chunk
    # passen würde -- die Grenze bei Zeile 4 muss trotzdem greifen.
    parser = CodeParser("text")
    chunks = parser.chunk_file(
        content, chunk_size=1000, overlap_size=0, boundary_lines=frozenset({4})
    )
    assert len(chunks) == 2
    assert chunks[0]["start_line"] == 1
    assert chunks[0]["end_line"] == 3
    assert chunks[1]["start_line"] == 4
    assert chunks[1]["end_line"] == 6


def test_no_overlap_across_a_boundary_cut():
    lines = _lines(6, width=20)
    content = "\n".join(lines)
    parser = CodeParser("text")
    # Großzügiger Overlap, der ohne die Sonderbehandlung Text aus Chunk 1
    # in Chunk 2 hineinziehen würde.
    chunks = parser.chunk_file(
        content, chunk_size=1000, overlap_size=1000, boundary_lines=frozenset({4})
    )
    assert chunks[1]["start_line"] == 4
    assert "Zeile 3" not in chunks[1]["content"]


def test_chunk_size_still_applies_within_a_section():
    # Boundary bei Zeile 100 (kommt nie), chunk_size zwingt trotzdem zum
    # Schneiden -- boundary_lines ersetzt die Obergrenze nicht.
    lines = _lines(10, width=50)
    content = "\n".join(lines)
    parser = CodeParser("text")
    chunks = parser.chunk_file(
        content, chunk_size=120, overlap_size=0, boundary_lines=frozenset({100})
    )
    assert len(chunks) > 1


def test_boundary_at_very_first_line_is_ignored():
    # current_len == 0 beim Start eines neuen Chunks -- eine Grenze auf der
    # ersten Zeile darf keinen leeren Chunk erzeugen.
    lines = _lines(4, width=20)
    content = "\n".join(lines)
    parser = CodeParser("text")
    chunks = parser.chunk_file(
        content, chunk_size=1000, overlap_size=0, boundary_lines=frozenset({1, 3})
    )
    assert all(c["content"] for c in chunks)
    assert chunks[0]["start_line"] == 1
    # Grenze bei Zeile 3 wird trotzdem respektiert.
    assert any(c["start_line"] == 3 for c in chunks)


def test_multiple_boundaries_produce_one_chunk_per_section():
    lines = _lines(9, width=20)
    content = "\n".join(lines)
    parser = CodeParser("text")
    chunks = parser.chunk_file(
        content, chunk_size=1000, overlap_size=0, boundary_lines=frozenset({4, 7})
    )
    assert [c["start_line"] for c in chunks] == [1, 4, 7]
    assert [c["end_line"] for c in chunks] == [3, 6, 9]
