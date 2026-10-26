"""Jira-Tickets aus Jira Server (Text statt ADF, null-Felder) müssen sich für die Anzeige auflösen lassen."""

import httpx
import respx

from api.knowledge_sources import _resolve_jira

BASE = "https://jira.example/jira"


@respx.mock
def test_resolve_jira_server_issue_with_text_description_and_null_fields():
    respx.get(f"{BASE}/rest/api/3/issue/ABC-1").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE}/rest/api/2/issue/ABC-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "fields": {
                    "summary": "Propagation schlägt fehl",
                    "status": {"name": "Closed"},
                    "priority": None,
                    "assignee": None,
                    "description": "Zeile 1\nZeile 2 mit <b>Tag</b>",
                    "comment": {
                        "comments": [
                            {
                                "author": None,
                                "created": "2026-01-02T10:00:00.000+0000",
                                "body": "Kommentar\nzweite Zeile",
                            }
                        ]
                    },
                }
            },
        )
    )

    result = _resolve_jira("https://jira.example/jira/browse/ABC-1", BASE, None, {})

    assert result["format"] == "html"
    content = result["content"]
    assert "Zeile 1<br>Zeile 2 mit &lt;b&gt;Tag&lt;/b&gt;" in content
    assert "Kommentar<br>zweite Zeile" in content
    assert "<b>Tag</b>" not in content
