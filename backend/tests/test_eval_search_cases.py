"""Struktur des versionierten Such-Katalogs (O-277); der Lauf gegen den Index ist scripts/eval_search.py."""

import json
from pathlib import Path

import pytest

CATALOGUE = json.loads((Path(__file__).parent / "fixtures" / "eval_search_cases.json").read_text())
CASES = CATALOGUE["cases"]


def test_catalogue_pins_a_source_revision_per_project():
    assert CATALOGUE["projects"]
    for project in CATALOGUE["projects"].values():
        assert project["name"]
        if project.get("synthetic"):  # Testdokumente aus dem Repository (O-284), keine Git-Revision
            assert project["note"]
            continue
        assert len(project["revision"]) == 40 and set(project["revision"]) <= set("0123456789abcdef")


def test_case_ids_are_unique_and_projects_are_declared():
    ids = [case["id"] for case in CASES]
    assert len(ids) == len(set(ids))
    assert {case["project"] for case in CASES} <= set(CATALOGUE["projects"])


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_every_case_declares_a_checkable_expectation(case):
    assert case["tool"] in {"search_code", "research_project", "search_knowledge"}
    assert case["query"].strip()
    expect = case["expect"]
    hit, passage = expect.get("hit"), expect.get("passage")
    kinds = [bool(hit), bool(expect.get("empty")), bool(passage), "absent" in expect]
    assert sum(kinds) == 1, "genau ein Erwartungstyp: Treffer, leer, Passage oder nicht belegt"
    if hit:
        assert hit["qualified_name"] and hit["file"] and hit["top"] >= 1
    if passage:
        assert passage["file"] and passage["contains"] and passage["top"] >= 1


def test_catalogue_covers_symbols_wording_entry_points_and_negatives_in_both_languages():
    assert {case["kind"] for case in CASES} >= {"symbol", "wording", "entry", "negative"}
    for project in CATALOGUE["projects"]:
        assert any(case["project"] == project and case["kind"] == "negative" for case in CASES)
