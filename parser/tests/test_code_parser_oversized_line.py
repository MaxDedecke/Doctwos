"""
O-085: CodeParser.chunk_file() teilt eine einzelne Zeile über chunk_size an
Wort-/Satzgrenzen auf, statt sie unverändert als übergroßen Einzelchunk zu
übernehmen. Passiert bei Confluence z. B., wenn _html_to_text() einen langen
<p>-Absatz ohne internes <br/> in eine einzige durchgehende Zeile umwandelt.
Reine Unit-Tests ohne DB.
"""

from code_parser import CodeParser, _split_oversized_line


def test_line_under_chunk_size_is_left_alone():
    parser = CodeParser("text")
    chunks = parser.chunk_file("Kurzer Satz.", chunk_size=1000, overlap_size=0, min_chunk_size=0)
    assert len(chunks) == 1
    assert chunks[0]["content"] == "Kurzer Satz."


def test_oversized_line_is_split_into_multiple_pieces():
    # Ein Absatz ohne <br/> -- eine einzige durchgehende Zeile, deutlich über
    # chunk_size.
    words = " ".join(f"Wort{i}" for i in range(1, 60))
    parser = CodeParser("text")
    chunks = parser.chunk_file(words, chunk_size=100, overlap_size=0, min_chunk_size=0)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk["content"]) <= 100
    # Kein Wort wurde verloren oder verdoppelt.
    assert " ".join(c["content"] for c in chunks).split() == words.split()


def test_split_pieces_keep_the_same_start_and_end_line():
    # Alle Teile stammen aus derselben einen physischen Quellzeile.
    words = " ".join(f"Wort{i}" for i in range(1, 60))
    content = "Vorher.\n" + words + "\nNachher."
    parser = CodeParser("text")
    chunks = parser.chunk_file(content, chunk_size=100, overlap_size=0, min_chunk_size=0)
    middle_chunks = [c for c in chunks if c["start_line"] == 2]
    assert len(middle_chunks) > 1
    assert all(c["end_line"] == 2 for c in middle_chunks)


def test_split_prefers_sentence_boundary_over_word_boundary():
    text = "Erster Satz ist hier zu Ende. " + ("x" * 90)
    pieces = _split_oversized_line(text, chunk_size=40)
    assert pieces[0] == "Erster Satz ist hier zu Ende."


def test_split_falls_back_to_word_boundary_without_sentence_end():
    text = " ".join(["wort"] * 30)
    pieces = _split_oversized_line(text, chunk_size=20)
    assert all(len(p) <= 20 for p in pieces)
    assert " ".join(pieces).split() == text.split()


def test_single_token_without_spaces_is_hard_cut_to_terminate():
    # Eine sehr lange URL ohne jedes Leerzeichen -- kein Wort-/Satzende
    # verfügbar, muss trotzdem terminieren statt in einer Endlosschleife zu
    # hängen.
    token = "https://example.invalid/" + ("a" * 200)
    pieces = _split_oversized_line(token, chunk_size=50)
    assert len(pieces) > 1
    assert "".join(pieces) == token
    assert all(len(p) <= 50 for p in pieces)


def test_line_exactly_at_chunk_size_is_not_split():
    line = "x" * 100
    assert _split_oversized_line(line, chunk_size=100) == [line]
