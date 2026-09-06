"""
O-083: connectors.base._section_boundaries() -- reine Unit-Tests ohne DB.
Leitet aus einer line_sections-Liste (O-082) die 1-basierten Zeilennummern
ab, an denen chunk_file() bevorzugt schneiden soll.
"""

from connectors.base import _section_boundaries


def test_no_sections_no_boundaries():
    assert _section_boundaries([None, None, None]) == frozenset()


def test_single_section_from_the_start_has_no_boundary():
    # Die Section beginnt schon auf Zeile 1 -- kein "Wechsel" gegenüber einer
    # Vorzeile, die es nicht gibt.
    assert _section_boundaries(["A", "A", "A"]) == frozenset()


def test_section_change_marks_the_first_line_of_the_new_section():
    # Zeile 1: keine Section, Zeile 2: "A" beginnt, Zeile 4: "B" beginnt.
    assert _section_boundaries([None, "A", "A", "B"]) == frozenset({2, 4})


def test_change_back_to_none_is_also_a_boundary():
    assert _section_boundaries(["A", "A", None]) == frozenset({3})


def test_empty_list_has_no_boundaries():
    assert _section_boundaries([]) == frozenset()
