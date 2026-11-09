"""Analysestand einer Git-Quelle im Chat-Agenten (Katalogtest 08.11.2026, C1/C11)."""

import asyncio
import json

from doctus_models.database import KnowledgeSource, SourceScanFile
from services.agent_tool_executor import AgentToolExecutor


def test_the_agent_sees_incomplete_files_with_reasons_and_the_build_profile(
    db_session, test_project, test_team
):
    source = KnowledgeSource(
        name="carddemo",
        type="Git",
        project_id=test_project,
        team_id=test_team,
        sync_status="completed",
        sync_cursor={"last_commit": "a" * 40},
        spaces={
            "build_profile": {"source": {"compiler_family": "IBM_ENTERPRISE_COBOL"}, "paths": {}}
        },
    )
    db_session.add(source)
    db_session.flush()
    rows = [
        ("app/cbl/COSGN00C.cbl", "cobol", "complete", None),
        ("app/cpy/CSSETATY.cpy", "copybook", "partial", "mismatched input '-' expecting SECTION"),
        ("app/bms/COSGN00.bms", "text", "text_fallback", "kein Strukturparser"),
        ("app/data/ACCTDATA.PS", "binary", "skipped", "Binärformat"),
    ]
    for path, language, status, reason in rows:
        db_session.add(
            SourceScanFile(
                source_id=source.id,
                file_path=path,
                content_hash=path[-16:],
                language=language,
                parse_status=status,
                parse_error=reason,
            )
        )
    db_session.flush()
    executor = AgentToolExecutor(
        repo_id=source.id,
        repo_available=False,
        project_id=test_project,
        db_session=db_session,
        audit_user_id=None,
        audit_chat_session_id=None,
        audit_chat_message_id=None,
        walkthrough_documents=[],
        mcp_tool_map={},
        prompt="Welche Dateien sind nur teilweise analysiert?",
    )

    result = json.loads(asyncio.run(executor.execute("get_source_status", {})))

    assert result["status"] == "ok" and result["indexed_commit"] == "a" * 40
    assert result["build_profile"]["source"]["compiler_family"] == "IBM_ENTERPRISE_COBOL"
    incomplete = result["incomplete_files"]
    assert incomplete["partial"]["files"][0]["path"] == "app/cpy/CSSETATY.cpy"
    assert "SECTION" in incomplete["partial"]["files"][0]["reason"]
    assert set(incomplete) == {"partial", "text_fallback", "skipped"}
    assert result["files"]["by_language"]["cobol"] == {"complete": 1}

    only_copybooks = json.loads(
        asyncio.run(executor.execute("get_source_status", {"language": "copybook"}))
    )
    assert set(only_copybooks["incomplete_files"]) == {"partial"}
