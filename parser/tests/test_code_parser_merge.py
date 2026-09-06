"""
O-084: CodeParser.chunk_file() legt aufeinanderfolgende Chunks unterhalb von
min_chunk_size zusammen, analog zu cobol/chunking.py::chunk()s Pending-Merge,
aber ohne Section-Objekt -- boundary_lines begrenzt das Zusammenlegen, falls
angegeben. Reine Unit-Tests ohne DB.
"""

from code_parser import CodeParser


def test_short_lines_merge_into_one_chunk_by_default():
    # Zehn kurze Zeilen (je < min_chunk_size) landen ohne Merge als zehn
    # Winzling-Chunks -- mit dem neuen Default sollen sie sich zu einem
    # einzigen Chunk zusammenlegen, solange sie zusammen unter chunk_size
    # bleiben.
    lines = [f"Zeile {i}" for i in range(1, 11)]
    content = "\n".join(lines)
    parser = CodeParser("text")
    chunks = parser.chunk_file(content, chunk_size=1000, overlap_size=0)
    assert len(chunks) == 1
    assert chunks[0]["start_line"] == 1
    assert chunks[0]["end_line"] == 10


def test_merge_stops_once_minimum_size_is_reached():
    # Genug kurze Zeilen, dass die laufende Summe die min_chunk_size
    # mehrfach überschreitet -- muss in mehrere gemergte Gruppen zerfallen,
    # nicht in einen einzigen Riesenchunk.
    lines = [f"Zeile Nummer {i} mit etwas mehr Text drin" for i in range(1, 40)]
    content = "\n".join(lines)
    parser = CodeParser("text")
    chunks = parser.chunk_file(content, chunk_size=1000, overlap_size=0, min_chunk_size=200)
    assert len(chunks) > 1
    for chunk in chunks[:-1]:
        # Jede gemergte Gruppe außer eventuell der letzten erreicht die
        # Mindestgröße.
        assert len(chunk["content"]) >= 200


def test_min_chunk_size_zero_disables_merging():
    # chunk_size so knapp, dass jede der fünf Zeilen schon in der
    # Primär-Schleife ihren eigenen Rohchunk bildet (7 Zeichen pro Zeile,
    # eine zweite Zeile würde chunk_size=8 sprengen).
    lines = [f"Zeile {i}" for i in range(1, 6)]
    content = "\n".join(lines)
    parser = CodeParser("text")
    without_merge = parser.chunk_file(content, chunk_size=8, overlap_size=0, min_chunk_size=0)
    assert len(without_merge) == 5


def test_does_not_merge_across_a_boundary_even_when_both_sides_are_small():
    lines = [f"Zeile {i}" for i in range(1, 5)]
    content = "\n".join(lines)
    parser = CodeParser("text")
    # Ohne boundary_lines würden Zeilen 1-2 und 3-4 zu einem Chunk
    # verschmelzen (beide winzig) -- mit einer Grenze bei Zeile 3 (O-083)
    # muss die Section-Trennung erhalten bleiben.
    chunks = parser.chunk_file(
        content,
        chunk_size=1000,
        overlap_size=0,
        boundary_lines=frozenset({3}),
        min_chunk_size=1000,
    )
    assert len(chunks) == 2
    assert chunks[0]["start_line"] == 1
    assert chunks[1]["start_line"] == 3


def test_large_chunk_is_not_merged_with_a_small_neighbour():
    # 240 Zeichen -- über min_chunk_size, aber unter chunk_size (kein O-085-
    # Einzelzeilen-Split). chunk_size ist so knapp bemessen, dass die
    # folgenden winzigen Zeilen nicht mehr in denselben Rohchunk passen und
    # dieser dadurch isoliert bleibt.
    big_line = "A" * 240
    content = "\n".join([big_line, "b1", "b2", "b3"])
    parser = CodeParser("text")
    chunks = parser.chunk_file(content, chunk_size=241, overlap_size=0, min_chunk_size=200)
    assert chunks[0]["content"] == big_line
    # Der Rest (winzig) darf sich untereinander mergen, aber nicht mit dem
    # bereits über der Mindestgröße liegenden ersten Chunk vermischen.
    assert big_line not in "".join(c["content"] for c in chunks[1:])
