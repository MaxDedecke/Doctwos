"""Struktur der Produktschnitt-Szenarien (O-304); der Lauf gegen die Instanz ist scripts/eval_product_slice.py."""

import json
from pathlib import Path

import pytest

CATALOGUE = json.loads((Path(__file__).parent / "fixtures" / "eval_product_scenarios.json").read_text())
SCENARIOS = CATALOGUE["scenarios"]
VIEWS = {"structure", "process", "impact", "graph", "negative"}


def test_every_project_pins_a_commit_revision():
    for project in CATALOGUE["projects"].values():
        assert len(project["revision"]) == 40 and set(project["revision"]) <= set("0123456789abcdef")


def test_ids_are_unique_and_projects_declared():
    ids = [item["id"] for item in SCENARIOS]
    assert len(ids) == len(set(ids))
    assert {item["project"] for item in SCENARIOS} <= set(CATALOGUE["projects"])


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item["id"])
def test_scenario_declares_what_its_view_checks(scenario):
    assert scenario["view"] in VIEWS
    expect = scenario["expect"]
    if scenario["view"] == "negative":
        assert scenario["request"] in {"process", "change-package-without-target"} and expect["status"] >= 400
        return
    assert scenario["entity"]["query"] and scenario["entity"]["qualified_name"]
    required = {"structure": {"group", "targets"}, "process": {"root_label", "labels"},
                "impact": {"impact_status", "affected_count"}, "graph": {"labels"}}[scenario["view"]]
    assert required <= set(expect)


def test_each_view_is_covered_for_java_and_cobol_with_a_negative_case_per_project():
    for project in CATALOGUE["projects"]:
        views = {item["view"] for item in SCENARIOS if item["project"] == project}
        assert views == VIEWS, f"{project}: {sorted(VIEWS - views)} fehlt"
