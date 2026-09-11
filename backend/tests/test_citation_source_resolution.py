"""O-090 follow-up: a citation/pin built from a repo-backed chunk must stay
openable even when no project is currently selected in the workspace — a new,
general chat spanning multiple projects has no `project.repo_id` for the
frontend to fall back to. See `_resolve_citation_source_id` in api/chat.py.
"""

from types import SimpleNamespace

import api.chat as chat_module
from api.chat import _extract_tool_sources, _record_agent_source, _resolve_citation_source_id
from models.database import KnowledgeSource


def test_repo_chunk_without_source_id_resolves_to_the_projects_git_source(db_session, test_project, test_team):
    git_source = KnowledgeSource(project_id=test_project, team_id=test_team, type="Git", name="repo")
    db_session.add(git_source)
    db_session.commit()

    try:
        chunk = SimpleNamespace(source_id=None, project_id=test_project)
        cache: dict = {}

        assert _resolve_citation_source_id(db_session, chunk, cache) == git_source.id
        assert cache == {test_project: git_source.id}
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == git_source.id).delete()
        db_session.commit()


def test_chunk_with_its_own_source_id_is_left_untouched(db_session, test_project):
    # A chunk from a project's own (non-repo) knowledge source already has a
    # resolvable source_id — no lookup needed or wanted.
    chunk = SimpleNamespace(source_id=42, project_id=test_project)
    assert _resolve_citation_source_id(db_session, chunk, {}) == 42


def test_project_without_a_git_source_resolves_to_none(db_session, test_project):
    chunk = SimpleNamespace(source_id=None, project_id=test_project)
    assert _resolve_citation_source_id(db_session, chunk, {}) is None


def test_chunk_without_a_project_resolves_to_none():
    chunk = SimpleNamespace(source_id=None, project_id=None)
    assert _resolve_citation_source_id(None, chunk, {}) is None


def test_repo_id_lookup_is_cached_across_chunks_from_the_same_project(db_session, test_project, test_team, monkeypatch):
    git_source = KnowledgeSource(project_id=test_project, team_id=test_team, type="Git", name="repo")
    db_session.add(git_source)
    db_session.commit()

    calls = []
    original = chat_module.resolve_repository_id

    def counting(project_id, db):
        calls.append(project_id)
        return original(project_id, db)

    monkeypatch.setattr(chat_module, "resolve_repository_id", counting)

    try:
        cache: dict = {}
        chunk_a = SimpleNamespace(source_id=None, project_id=test_project)
        chunk_b = SimpleNamespace(source_id=None, project_id=test_project)

        _resolve_citation_source_id(db_session, chunk_a, cache)
        _resolve_citation_source_id(db_session, chunk_b, cache)

        assert calls == [test_project]
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == git_source.id).delete()
        db_session.commit()


def test_agent_tool_sources_carry_the_agents_resolved_repository_id():
    """The agent reads from exactly one repository per run (`resolved_repo_id`) —
    a citation to a file it viewed must carry that id, not None, or opening it
    fails the same way as the standard-RAG citation gap this follows up on."""
    agent_sources: list = []
    event = {
        "type": "tool_result",
        "name": "view_repo_file",
        "result": {"file_path": "cbl/PROGRAM.cbl", "start_line": 10, "end_line": 40},
    }

    _extract_tool_sources(event, agent_sources, source_id=99)

    assert agent_sources == [{"file": "cbl/PROGRAM.cbl", "lines": [10, 40], "source_id": 99}]


def test_agent_tool_sources_without_a_resolved_repository_stay_none():
    agent_sources: list = []
    event = {
        "type": "tool_result",
        "name": "search_repo_code",
        "result": {"matches": [{"file": "cbl/OTHER.cbl", "line": 5}]},
    }

    _extract_tool_sources(event, agent_sources, source_id=None)

    assert agent_sources == [{"file": "cbl/OTHER.cbl", "lines": [5, 5], "source_id": None}]


def test_record_agent_source_still_dedupes_by_file_and_lines():
    agent_sources: list = []
    _record_agent_source(agent_sources, "cbl/PROGRAM.cbl", 1, 10, source_id=7)
    _record_agent_source(agent_sources, "cbl/PROGRAM.cbl", 1, 10, source_id=7)

    assert len(agent_sources) == 1
