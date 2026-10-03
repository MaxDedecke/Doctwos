"""Struktur der Chat-Fragen mit Checkliste (O-354); der Lauf gegen ein Modell ist scripts/eval_chat.py."""

import json
import re
from pathlib import Path

import pytest

CASES = json.loads((Path(__file__).parent / "fixtures" / "eval_chat_cases.json").read_text())["cases"]


def test_ids_are_unique_and_cover_both_projects():
    ids = [case["id"] for case in CASES]
    assert len(ids) == len(set(ids))
    assert {case["project"] for case in CASES} == {"Apache Syncope", "AWS CardDemo"}


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_every_case_has_checkable_and_valid_checks(case):
    assert case["question"].strip() and case["label"]
    checks = case["checks"]
    assert checks.get("answer_all") or checks.get("cites")
    for pattern in checks.get("answer_all", []) + checks.get("answer_any", []) + ([checks["no_claim"]] if checks.get("no_claim") else []):
        re.compile(pattern)
    for want in checks.get("cites", []):
        assert want["file"] and want["lines"][0] <= want["lines"][1]
