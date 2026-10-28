"""Bausteine des Chat-Antwortablaufs, ohne HTTP und ohne Modell."""

import json
from types import SimpleNamespace

from services.chat_sources import ToolEvidence
from services.chat_turn import build_system_prompt
from services.chat_view_actions import ViewActionTracker


def _walkthrough_result(call_id: str) -> dict:
    return {
        "type": "tool_result",
        "id": call_id,
        "name": "offer_source_walkthrough",
        "result": json.dumps(
            {
                "status": "ok",
                "title": "Ablauf",
                "steps": [
                    {
                        "file_path": "src/PAY.cbl",
                        "start_line": 10,
                        "end_line": 12,
                        "explanation": "Prüfung",
                    }
                ],
            }
        ),
    }


def test_view_action_tracker_dedupes_and_survives_the_final_step_list():
    tracker = ViewActionTracker(session_id=1, turn_id=2, project_id=3)
    action = tracker.observe(_walkthrough_result("call-1"))
    assert action and action["view"] == "walkthrough" and action["status"] == "requested"
    assert tracker.observe(_walkthrough_result("call-1")) is None

    final_steps = [{"type": "thought", "content": "..."}]
    merged = tracker.merge_into(final_steps)
    assert merged[-1]["action_id"] == action["action_id"]
    assert tracker.merge_into(merged) == merged


def test_tool_evidence_accepts_only_observed_citations_and_edges():
    evidence = ToolEvidence(repository_id=7)
    evidence.observe(
        {
            "type": "tool_result",
            "name": "view_repo_file",
            "result": {"file_path": "src/PAY.cbl", "start_line": 10, "end_line": 20},
        }
    )
    assert evidence.sources == [{"file": "src/PAY.cbl", "lines": [10, 20], "source_id": 7}]

    answer, consistent = evidence.validate("Siehe `src/PAY.cbl:12`.", [], "Frage")
    assert consistent and "`src/PAY.cbl:12`" in answer

    answer, consistent = evidence.validate("Siehe `src/OTHER.cbl:3`.", [], "Frage")
    assert not consistent and "OTHER.cbl" not in answer


def test_normal_mode_prompt_adds_guards_once_and_skips_source_context():
    request = SimpleNamespace(
        mode="normal", system_prompt=None, project_id=None, source_id=None, metadata=None
    )
    prompt = build_system_prompt(None, None, request)
    assert prompt.startswith("Du bist Doctus, ein hilfreicher Gesprächsassistent.")
    assert prompt.count("### Sicherheitshinweis") == 1
    assert prompt.count("### Sprachkonsistenz") == 1
    assert "### Normaler Chat" in prompt
