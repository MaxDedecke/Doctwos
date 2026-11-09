"""Lesender Commit-Diff für den Agenten (Katalogtest 08.11.2026, J11: Vorher/Nachher fehlte)."""

import json
import subprocess

from doctus_models.database import KnowledgeSource
from services import commit_diff as commit_diff_module
from services.agent_tool_executor import AgentToolExecutor
from services.chat_sources import extract_tool_sources


def test_the_agent_reads_removed_and_added_lines_with_their_method(
    db_session, test_project, test_team, tmp_path, monkeypatch
):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()

    git("init")
    git("config", "user.email", "fixture@example.com")
    git("config", "user.name", "Fixture")
    checker = tmp_path / "src" / "Checker.java"
    checker.parent.mkdir()
    checker.write_text(
        "class Checker {\n" + "  int pad;\n" * 8 + "  int timeout() {\n    int base = 1;\n"
        "    int factor = 2;\n    int more = 3;\n    int extra = 4;\n    return 30;\n  }\n"
        "\n  boolean check() {\n    return ping(timeout());\n  }\n}\n"
    )
    program = tmp_path / "src" / "AUTH.cbl"
    program.write_text(
        "       PROCEDURE DIVISION.\n       MAIN-PARA.\n           PERFORM DECIDE.\n"
        "           GOBACK.\n       DECIDE.\n"
        + "           CONTINUE\n" * 6
        + "           MOVE 05 TO RESP-CODE\n           MOVE 0 TO APPR-AMT.\n"
    )
    git("add", ".")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    program.write_text(program.read_text().replace("MOVE 05 TO", "MOVE 51 TO"))
    checker.write_text(checker.read_text().replace("return 30;", "return confTimeout();"))
    (tmp_path / "src" / "Status.java").write_text("class Status {}\n")
    git("add", ".")
    git("commit", "-m", "head")
    head = git("rev-parse", "HEAD")
    source = KnowledgeSource(name="diff", type="Git", project_id=test_project, team_id=test_team)
    db_session.add(source)
    db_session.flush()
    monkeypatch.setattr(commit_diff_module, "_git_worktree", lambda *a: tmp_path)
    executor = AgentToolExecutor(
        repo_id=source.id,
        repo_available=True,
        project_id=test_project,
        db_session=db_session,
        audit_user_id=None,
        audit_chat_session_id=None,
        audit_chat_message_id=None,
        walkthrough_documents=[],
        mcp_tool_map={},
        prompt="Was hat sich geändert?",
    )
    import asyncio

    result = json.loads(
        asyncio.run(executor.execute("view_commit_diff", {"base_ref": base[:10], "head_ref": head}))
    )

    assert result["status"] == "ok" and result["file_count"] == 3
    files = {item["path"]: item for item in result["files"]}
    assert files["src/Status.java"]["status"] == "added"
    hunk = files["src/Checker.java"]["hunks"][0]
    assert "-    return 30;" in hunk["text"] and "+    return confTimeout();" in hunk["text"]
    assert hunk["context"] == "int timeout() {"
    cobol = files["src/AUTH.cbl"]["hunks"][0]
    assert cobol["context"] == "DECIDE" and "+           MOVE 51 TO RESP-CODE" in cobol["text"]
    sources: list = []
    extract_tool_sources(
        {"type": "tool_result", "name": "view_commit_diff", "result": json.dumps(result)},
        sources,
        source.id,
    )
    start, count = hunk["new_start"], hunk["new_lines"]
    assert {
        "file": "src/Checker.java",
        "lines": [start, start + count - 1],
        "source_id": source.id,
    } in sources

    single = json.loads(
        asyncio.run(
            executor.execute(
                "view_commit_diff",
                {"base_ref": base, "head_ref": head, "file_path": "../etc/passwd"},
            )
        )
    )
    assert "error" in single
