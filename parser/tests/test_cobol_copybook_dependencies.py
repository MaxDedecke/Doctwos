"""O-137: präzise statt konservative Copybook-Abhängigkeits-Eingrenzung.

Reine In-Memory-Tests ohne DB-Verbindung (anders als test_git_connector.py/
test_ap4_persistence.py) - `SourceScanFile` ist ein plain SQLAlchemy-Objekt
und braucht für reine Attributzugriffe keine Session.
"""

from cobol.copybook import CopybookIndex, dependency_state, resolve_path
from cobol.model import ParsedEdge, ParseResult
from connectors.git import _discover_copybook_dependencies, _fingerprint_libraries
from models.database import SourceScanFile


def _copy_edge(
    dst_name: str, resolution: str = "resolved", library: str | None = None
) -> ParsedEdge:
    meta = {"library": library} if library else {}
    return ParsedEdge(
        type="COPY",
        src_name="",
        dst_name=dst_name,
        resolution=resolution,
        src_start_line=1,
        src_end_line=1,
        scope=None,
        meta=meta,
    )


# --- cobol/copybook.py::dependency_state() ----------------------------------


def test_dependency_state_follows_the_whole_copy_chain():
    index = CopybookIndex(
        {"A": ["copy/A.CPY"], "B": ["copy/B.CPY"], "C": ["copy/C.CPY"]},
        copy_edges_by_path={
            "copy/A.CPY": [_copy_edge("B")],
            "copy/B.CPY": [_copy_edge("C")],
        },
    )
    visited, names = dependency_state(["copy/A.CPY"], index)
    assert visited == {"copy/A.CPY", "copy/B.CPY", "copy/C.CPY"}
    assert names == set()


def test_dependency_state_never_loops_on_a_cycle():
    index = CopybookIndex(
        {"A": ["copy/A.CPY"], "B": ["copy/B.CPY"]},
        copy_edges_by_path={
            "copy/A.CPY": [_copy_edge("B")],
            "copy/B.CPY": [_copy_edge("A")],
        },
    )
    visited, names = dependency_state(["copy/A.CPY"], index)
    assert visited == {"copy/A.CPY", "copy/B.CPY"}
    assert names == set()


def test_dependency_state_keeps_all_candidates_and_the_name_of_an_ambiguous_link():
    index = CopybookIndex(
        {"A": ["copy/A.CPY"], "AMBIG": ["copy/X1.CPY", "copy/X2.CPY"]},
        copy_edges_by_path={"copy/A.CPY": [_copy_edge("AMBIG")]},
    )
    visited, names = dependency_state(["copy/A.CPY"], index)
    assert {"copy/X1.CPY", "copy/X2.CPY"} <= visited
    assert names == {"AMBIG"}


def test_dependency_state_marks_a_missing_system_member_by_name_only():
    index = CopybookIndex(
        {"A": ["copy/A.CPY"]}, copy_edges_by_path={"copy/A.CPY": [_copy_edge("DFHAID")]}
    )
    visited, names = dependency_state(["copy/A.CPY"], index)
    assert visited == {"copy/A.CPY"}
    assert names == {"DFHAID"}


def test_search_order_resolves_the_first_directory_with_exactly_one_hit():
    index = CopybookIndex({"KUNDE": ["lib/common/KUNDE.cpy", "lib/prod/KUNDE.cpy"]})
    assert resolve_path("KUNDE", None, index) is None
    assert resolve_path("KUNDE", None, index, ("lib/prod", "lib/common")) == "lib/prod/KUNDE.cpy"
    assert resolve_path("KUNDE", None, index, ("LIB/COMMON/",)) == "lib/common/KUNDE.cpy"
    assert resolve_path("KUNDE", None, index, ("elsewhere",)) is None


def test_search_order_does_not_guess_inside_a_directory_with_several_hits():
    index = CopybookIndex({"KUNDE": ["lib/prod/a/KUNDE.cpy", "lib/prod/b/KUNDE.cpy"]})
    assert resolve_path("KUNDE", None, index, ("lib/prod",)) is None


# --- connectors/git.py::_discover_copybook_dependencies() -------------------


def test_discover_dependencies_resolves_direct_and_transitive_copies():
    index = CopybookIndex(
        {"B": ["copy/B.CPY"], "C": ["copy/C.CPY"]},
        copy_edges_by_path={"copy/B.CPY": [_copy_edge("C")]},
    )
    result = ParseResult(
        program_name="X",
        path="x.cbl",
        source_format="fixed",
        edges=[_copy_edge("B")],
    )
    deps = _discover_copybook_dependencies(result, index)
    assert deps == {"copy/B.CPY", "copy/C.CPY"}


def test_discover_dependencies_tracks_a_missing_copybook_by_name_instead_of_giving_up():
    result = ParseResult(
        program_name="X",
        path="x.cbl",
        source_format="fixed",
        edges=[_copy_edge("DFHAID", resolution="unresolved")],
    )
    assert _discover_copybook_dependencies(result, CopybookIndex()) == {"?DFHAID"}


def test_discover_dependencies_returns_empty_set_without_any_copy():
    result = ParseResult(program_name="X", path="x.cbl", source_format="fixed", edges=[])
    assert _discover_copybook_dependencies(result, CopybookIndex()) == set()


def test_discover_dependencies_returns_none_without_a_copybook_index():
    result = ParseResult(
        program_name="X", path="x.cbl", source_format="fixed", edges=[_copy_edge("B")]
    )
    assert _discover_copybook_dependencies(result, None) is None


# --- connectors/git.py::_fingerprint_libraries() ----------------------------


def test_fingerprint_libraries_is_none_for_non_structural_languages():
    assert _fingerprint_libraries("x.txt", "text", None, {}, None) is None


def test_fingerprint_libraries_stays_conservative_for_a_never_before_seen_program():
    copybook_hashes = {"copy/A.CPY": "sha-a", "copy/B.CPY": "sha-b"}
    libs = _fingerprint_libraries("x.cbl", "cobol", None, copybook_hashes, None)
    assert libs == copybook_hashes


def test_fingerprint_libraries_uses_the_stored_precise_set_for_a_known_program():
    copybook_hashes = {"copy/A.CPY": "sha-a-new", "copy/B.CPY": "sha-b"}
    existing = SourceScanFile(copybook_dependencies={"copy/A.CPY": "sha-a-old"})
    libs = _fingerprint_libraries("x.cbl", "cobol", existing, copybook_hashes, None)
    # Nur der gespeicherte Pfad zaehlt, mit dem AKTUELLEN Hash (nicht dem
    # damals gespeicherten) - eine Aenderung an B faellt dadurch bewusst weg.
    assert libs == {"copy/A.CPY": "sha-a-new"}


def test_fingerprint_libraries_changes_when_a_stored_dependency_was_deleted():
    existing = SourceScanFile(copybook_dependencies={"copy/GONE.CPY": "sha-old"})
    libs = _fingerprint_libraries("x.cbl", "cobol", existing, {}, None)
    assert libs == {"copy/GONE.CPY": ""}


def test_fingerprint_libraries_is_precise_for_a_copybook_via_the_pass0_index():
    index = CopybookIndex(
        {"B": ["copy/B.CPY"]}, copy_edges_by_path={"copy/A.CPY": [_copy_edge("B")]}
    )
    copybook_hashes = {"copy/A.CPY": "sha-a", "copy/B.CPY": "sha-b", "copy/UNRELATED.CPY": "sha-x"}
    libs = _fingerprint_libraries("copy/A.CPY", "copybook", None, copybook_hashes, index)
    assert libs == {"copy/A.CPY": "sha-a", "copy/B.CPY": "sha-b"}


def test_fingerprint_libraries_for_an_ambiguous_chain_is_bounded_to_its_candidates():
    index = CopybookIndex(
        {"AMBIG": ["copy/X1.CPY", "copy/X2.CPY"]},
        copy_edges_by_path={"copy/A.CPY": [_copy_edge("AMBIG")]},
    )
    copybook_hashes = {"copy/A.CPY": "sha-a", "copy/X1.CPY": "sha-1", "copy/X2.CPY": "sha-2"}
    libs = _fingerprint_libraries("copy/A.CPY", "copybook", None, copybook_hashes, index)
    assert set(libs) == {"copy/A.CPY", "copy/X1.CPY", "copy/X2.CPY", "?AMBIG"}


def test_missing_name_marker_changes_the_fingerprint_once_a_copybook_with_that_name_appears():
    existing = SourceScanFile(copybook_dependencies={"?DFHAID": ""})
    before = _fingerprint_libraries("x.cbl", "cobol", existing, {}, CopybookIndex())
    after = _fingerprint_libraries(
        "x.cbl",
        "cobol",
        existing,
        {"copy/DFHAID.cpy": "sha-new"},
        CopybookIndex({"DFHAID": ["copy/DFHAID.cpy"]}),
    )
    assert before == {"?DFHAID": ""}
    assert after != before


def test_unrelated_copybook_change_leaves_a_program_with_a_missing_system_member_unchanged():
    existing = SourceScanFile(copybook_dependencies={"copy/A.CPY": "x", "?DFHAID": ""})
    index = CopybookIndex({"A": ["copy/A.CPY"], "OTHER": ["copy/OTHER.CPY"]})
    first = _fingerprint_libraries(
        "x.cbl", "cobol", existing, {"copy/A.CPY": "a", "copy/OTHER.CPY": "1"}, index
    )
    second = _fingerprint_libraries(
        "x.cbl", "cobol", existing, {"copy/A.CPY": "a", "copy/OTHER.CPY": "2"}, index
    )
    assert first == second
