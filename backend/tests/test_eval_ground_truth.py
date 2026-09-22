"""Offline regression contract for the J1–J5/C1–C6 evaluation cases (O-322)."""

import json
from pathlib import Path

import pytest

import agent as agent_module
from api.chat import _validate_answer_sources
from agent import find_repo_files


CASES = json.loads((Path(__file__).parent / "fixtures" / "eval_ground_truth.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_eval_case_never_substitutes_a_neighbouring_file(monkeypatch, tmp_path, case):
    """Every eval case retains its declared primary file and physical line.

    The fixture is intentionally offline: it guards the retrieval/source gates
    without requiring the proprietary target repositories or a model endpoint.
    """
    primary = tmp_path / case["file"]
    primary.parent.mkdir(parents=True)
    primary.write_text("\n".join(f"LINE-{number}" for number in range(1, 41)), encoding="utf-8")
    decoy = tmp_path / "neighbour" / primary.name
    decoy.parent.mkdir(parents=True, exist_ok=True)
    decoy.write_text("wrong program", encoding="utf-8")
    monkeypatch.setattr(
        agent_module,
        "get_repo_path",
        lambda _repo_id, path="": str(tmp_path / path) if path else str(tmp_path),
    )

    # A full path resolves uniquely; a duplicate basename deliberately stays
    # ambiguous rather than becoming a plausible replacement source.
    assert find_repo_files(1, case["file"]) == [case["file"]]
    assert len(find_repo_files(1, primary.name)) == 2

    answer = f"Belegt: `{case['file']}:{case['line']}`."
    _, accepted = _validate_answer_sources(answer, [{"file": case["file"], "lines": [1, 40]}])
    fallback, accepted_fallback = _validate_answer_sources(
        f"Falsch: `neighbour/{primary.name}:{case['line']}`.",
        [{"file": case["file"], "lines": [1, 40]}],
    )

    assert accepted
    assert not accepted_fallback
    assert "nicht belastbar belegt" in fallback


@pytest.mark.parametrize("case", [case for case in CASES if "edge" in case], ids=lambda case: case["id"])
def test_eval_call_claims_require_the_ground_truth_edge(case):
    source, target = case["edge"]
    _, accepted = _validate_answer_sources(
        f"{source} ruft {target} auf.", [], {(source.casefold(), target.casefold())}
    )
    _, rejected = _validate_answer_sources(f"{source} ruft UNKNOWN auf.", [], {(source.casefold(), target.casefold())})

    assert accepted
    assert not rejected
