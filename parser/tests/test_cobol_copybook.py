import os

from cobol import copybook, divisions, embedded, lexer, source_format

FIXTURES = os.path.join(os.path.dirname(__file__), "cobol_corpus", "fixtures")


def _edges(text: str, index=None, fmt: str = "fixed"):
    lines = source_format.split_logical_lines(text, fmt)
    masked, _ = embedded.mask(lines)
    tokens = lexer.tokenize(masked)
    program, div_errors = divisions.scan(tokens)
    edges, copy_errors = copybook.scan(program, tokens, index)
    return program, edges, div_errors + copy_errors


def _edges_from_fixture(name: str, index=None, fmt: str = "fixed"):
    with open(os.path.join(FIXTURES, name)) as f:
        text = f.read()
    return _edges(text, index, fmt)


def test_copy_replacing_captures_pseudo_text_pair_and_resolves():
    _, edges, errors = _edges_from_fixture(
        "04_copy_replacing.cbl", index={"WSFIELDS": ["/repo/copybooks/WSFIELDS.cpy"]}
    )
    assert errors == []
    copy_edge = edges[0]
    assert copy_edge.type == "COPY"
    assert copy_edge.dst_name == "WSFIELDS"
    assert copy_edge.resolution == "resolved"
    assert copy_edge.scope is None
    assert copy_edge.src_name == "COPYREPL"
    assert copy_edge.meta["replacing"] == [{"from": ":TAG:", "to": "WS-FIELD"}]


def test_copy_of_unindexed_copybook_is_unresolved_without_crashing():
    _, edges, errors = _edges_from_fixture("05_copy_missing.cbl", index={})
    assert errors == []
    copy_edge = edges[0]
    assert copy_edge.dst_name == "NOSUCHBOOK"
    assert copy_edge.resolution == "unresolved"
    assert "replacing" not in copy_edge.meta


def test_copy_without_index_is_unresolved_not_a_crash():
    _, edges, errors = _edges_from_fixture("04_copy_replacing.cbl", index=None)
    assert errors == []
    assert edges[0].resolution == "unresolved"


def test_multiple_paths_without_library_qualifier_stay_ambiguous():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. AMBIGCPY.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       COPY WSFIELDS.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n"
    )
    _, edges, errors = _edges(
        text, index={"WSFIELDS": ["/repo/LIB-A/WSFIELDS.cpy", "/repo/LIB-B/WSFIELDS.cpy"]}
    )
    assert errors == []
    assert edges[0].resolution == "unresolved"


def test_of_library_qualifier_disambiguates_between_multiple_paths():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. LIBCPY.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       COPY WSFIELDS OF LIB-B.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n"
    )
    _, edges, errors = _edges(
        text, index={"WSFIELDS": ["/repo/LIB-A/WSFIELDS.cpy", "/repo/LIB-B/WSFIELDS.cpy"]}
    )
    assert errors == []
    assert edges[0].resolution == "resolved"
    assert edges[0].meta["library"] == "LIB-B"


def test_multiple_replacing_pairs_without_separator():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. MULTIREP.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       COPY WSFIELDS REPLACING ==:TAG1:== BY ==A== ==:TAG2:== BY ==B==.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n"
    )
    _, edges, errors = _edges(text, index={"WSFIELDS": ["/repo/lib/WSFIELDS.cpy"]})
    assert errors == []
    assert edges[0].meta["replacing"] == [
        {"from": ":TAG1:", "to": "A"},
        {"from": ":TAG2:", "to": "B"},
    ]


def test_copy_inside_procedure_division_uses_enclosing_paragraph_as_src():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. PROCCOPY.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           COPY CPYCODE.\n"
        "           STOP RUN.\n"
    )
    _, edges, errors = _edges(text, index={"CPYCODE": ["/repo/lib/CPYCODE.cpy"]})
    assert errors == []
    assert edges[0].src_name == "MAIN-PARA"


def test_no_copy_statement_produces_no_edges_without_crashing():
    _, edges, errors = _edges_from_fixture("01_minimal.cbl")
    assert errors == []
    assert edges == []


def test_copy_of_quoted_literal_with_extension_still_resolves():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. QUOTEDCPY.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        '       COPY "WSFIELDS.cpy".\n'
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n"
    )
    _, edges, errors = _edges(text, index={"WSFIELDS": ["/repo/lib/WSFIELDS.cpy"]})
    assert errors == []
    # dst_name behaelt die Endung (Rohwert aus dem Quelltext, siehe
    # copybook.py-Docstring) - nur die Indexauflösung normalisiert sie weg.
    assert edges[0].dst_name == "WSFIELDS.cpy"
    assert edges[0].resolution == "resolved"
