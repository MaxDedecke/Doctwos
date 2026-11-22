"""Anhänge fürs Modell: HTML als Text samt eingebetteter Daten, faire Aufteilung, sichtbare Kürzung."""

import json

import pytest

from services.attachment_text import html_to_text, readable
from services.chat_attachments import prompt_block

PAGE = """<!doctype html><html><head><title>Benchmark</title><style>body{color:red}</style></head>
<body><h1>Ergebnis</h1><p>Doctus hilft &amp; misst, etwa bei COSGN00C.cbl.</p>
<table><tr><th>Modell</th><th>Rubrik</th></tr><tr><td>qwen3:8b</td><td>0,61</td></tr></table>
<script>const DATA = {"runs": [{"model": "qwen3:8b", "score": 0.61}]}; render(DATA);</script>
<script>function render(d) { document.body.append(d); }</script>
<script type="application/json">{"meta": {"date": "2026-11-17"}}</script></body></html>"""


def test_html_becomes_readable_text_with_the_page_data():
    text = html_to_text(PAGE)

    assert "color:red" not in text and "function render" not in text
    assert "## Ergebnis" in text and "Doctus hilft & misst, etwa bei COSGN00C.cbl." in text
    assert "Modell | Rubrik" in text and "qwen3:8b | 0,61" in text
    data = text.split("## Eingebettete Daten der Seite (aus Skripten)\n", 1)[1].splitlines()
    assert data[0] == 'DATA = {"runs":[{"model":"qwen3:8b","score":0.61}]}'
    assert json.loads(data[1]) == {"meta": {"date": "2026-11-17"}}


def test_non_html_attachments_stay_as_they_are():
    assert readable("job.log", "<b>kein HTML</b>") == "<b>kein HTML</b>"
    assert readable("seite.txt", PAGE) != PAGE  # am Anfang als HTML erkennbar


def test_small_attachments_leave_their_budget_to_large_ones():
    block, trimmed = prompt_block(
        [{"name": "kurz.log", "content": "a" * 100}, {"name": "lang.log", "content": "b" * 20_000}],
        8192,
    )

    assert "a" * 100 in block
    assert trimmed[0]["name"] == "lang.log" and trimmed[0]["total"] == 20_000
    assert trimmed[0]["shown"] == int(8192 * 3.5 * 0.3) - 100
    assert block.count("b") < 20_000


@pytest.mark.asyncio
async def test_a_question_with_an_attachment_is_not_forced_into_code_research(
    client, test_project, monkeypatch
):
    seen = {}

    async def embed(*_args, **_kwargs):
        return [0.01] * 1024

    async def stream(**kwargs):
        seen.update(kwargs)
        yield {
            "type": "answer",
            "content": "Der Bericht nennt qwen3:8b mit 0,61 und verweist auf `COSGN00C.cbl`.",
            "agent_steps": [],
        }

    monkeypatch.setattr("services.chat_service.embed_text", embed)
    monkeypatch.setattr("services.chat_turn.agent_profile_supports_tools", lambda _: True)
    monkeypatch.setattr("services.chat_turn.stream_agent_events", stream)
    session_id = None
    try:
        response = client.post(
            "/chat",
            json={
                "message": "Was steht im Bericht?",
                "project_id": test_project,
                "mode": "evidence",
                "attachments": [{"name": "bench.html", "content": PAGE}],
            },
        )
        events = [
            json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
        ]
        session_id = next(e["session_id"] for e in events if e["type"] == "session")
        assert seen["require_initial_tool_call"] is False
        assert "qwen3:8b | 0,61" in seen["prompt"] and "color:red" not in seen["prompt"]
        assert "### Angehängte Dateien" in seen["system_prompt"]
        answer = next(e for e in events if e["type"] == "answer")["content"]
        assert "nicht belegt" not in answer
    finally:
        if session_id:
            client.delete(f"/chat/sessions/{session_id}")
