"""O-090 follow-up: a citation/pin built from a repo-backed chunk must stay
openable even when no project is currently selected in the workspace — a new,
general chat spanning multiple projects has no `project.repo_id` for the
frontend to fall back to. See `_resolve_citation_source_id` in api/chat.py.
"""

from types import SimpleNamespace

import api.chat as chat_module
from api.chat import (
    _attach_analysis_status,
    _append_agent_source_fallback,
    _extract_tool_edge_pairs,
    _extract_tool_sources,
    _record_agent_source,
    _resolve_citation_source_id,
    _validate_answer_sources,
)
from models.database import KnowledgeSource, SourceScanFile


def test_repo_chunk_without_source_id_resolves_to_the_projects_git_source(
    db_session, test_project, test_team
):
    git_source = KnowledgeSource(
        project_id=test_project, team_id=test_team, type="Git", name="repo"
    )
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


def test_repo_id_lookup_is_cached_across_chunks_from_the_same_project(
    db_session, test_project, test_team, monkeypatch
):
    git_source = KnowledgeSource(
        project_id=test_project, team_id=test_team, type="Git", name="repo"
    )
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


def test_call_flow_tool_sources_make_traced_steps_citable():
    agent_sources: list = []
    event = {
        "type": "tool_result",
        "name": "trace_call_flow",
        "result": {
            "nodes": [
                {"file_path": "api/orders.py", "start_line": 12, "end_line": 24},
                {"file_path": "services/orders.py", "start_line": 40, "end_line": 58},
            ]
        },
    }

    _extract_tool_sources(event, agent_sources, source_id=99)

    assert agent_sources == [
        {"file": "api/orders.py", "lines": [12, 24], "source_id": 99},
        {"file": "services/orders.py", "lines": [40, 58], "source_id": 99},
    ]


def test_record_agent_source_still_dedupes_by_file_and_lines():
    agent_sources: list = []
    _record_agent_source(agent_sources, "cbl/PROGRAM.cbl", 1, 10, source_id=7)
    _record_agent_source(agent_sources, "cbl/PROGRAM.cbl", 1, 10, source_id=7)

    assert len(agent_sources) == 1


def test_agent_source_fallback_adds_exact_location_when_model_omits_citation():
    answer = "Die Methode verarbeitet die Zahlungsdaten."
    result = _append_agent_source_fallback(
        answer,
        [{"file": "src/main/java/PaymentService.java", "lines": [42, 68]}],
    )

    assert "`src/main/java/PaymentService.java:42`" in result


def test_agent_source_fallback_keeps_a_valid_model_citation_unchanged():
    answer = "Die Validierung steht in `src/main/java/PaymentService.java:55`."
    result = _append_agent_source_fallback(
        answer,
        [{"file": "src/main/java/PaymentService.java", "lines": [42, 68]}],
    )

    assert result == answer


def test_answer_source_validation_rejects_an_unread_file_or_line():
    sources = [{"file": "src/PaymentService.java", "lines": [42, 68]}]

    valid, is_valid = _validate_answer_sources("Belegt: `src/PaymentService.java:55`.", sources)
    wrong_file, wrong_file_valid = _validate_answer_sources("Belegt: `src/Other.java:55`.", sources)
    wrong_line, wrong_line_valid = _validate_answer_sources("Belegt: `src/PaymentService.java:69`.", sources)

    assert is_valid and valid.startswith("Belegt")
    assert not wrong_file_valid and "nicht belastbar belegt" in wrong_file
    assert not wrong_line_valid and "nicht belastbar belegt" in wrong_line


def test_answer_source_validation_requires_a_trace_edge_for_call_claims():
    event = {
        "type": "tool_result",
        "name": "trace_call_flow",
        "result": {
            "status": "ok",
            "nodes": [{"id": 1, "name": "ENTRY"}, {"id": 2, "name": "TARGET"}],
            "edges": [{"source": 1, "target": 2, "resolution": "resolved"}],
        },
    }
    edges = _extract_tool_edge_pairs(event)

    _, supported = _validate_answer_sources("ENTRY ruft TARGET auf.", [], edges)
    rejected, unsupported = _validate_answer_sources("ENTRY ruft OTHER auf.", [], edges)

    assert edges == {("entry", "target")}
    assert supported
    assert not unsupported and "Codebeziehung" in rejected


def test_attach_analysis_status_marks_a_partial_citation(db_session, test_project, test_team):
    """O-120: eine Chat-Quelle, die aus einer nur teilweise geparsten Datei
    stammt, muss diesen Vorbehalt tragen -- sonst wirkt jedes Zitat gleich
    verlässlich, egal ob die Struktur dahinter vollständig ist."""
    git_source = KnowledgeSource(
        project_id=test_project, team_id=test_team, type="Git", name="repo"
    )
    db_session.add(git_source)
    db_session.commit()
    db_session.add(
        SourceScanFile(
            source_id=git_source.id,
            file_path="PAYROLL.cbl",
            content_hash="abc",
            parse_status="partial",
            parse_error="mismatched input",
        )
    )
    db_session.commit()

    sources = [{"file": "PAYROLL.cbl", "lines": [1, 5], "source_id": git_source.id}]
    result = _attach_analysis_status(db_session, sources)

    assert result[0]["analysis_status"] == "partial"
    assert result[0]["analysis_reasons"] == ["mismatched input"]
    assert result[0]["provenance"]["kind"] == "code_fact"
    assert result[0]["provenance"]["verification_status"] == "indexed_unreviewed"
    assert result[0]["provenance"]["analysis_status"] == "partial"


def test_attach_analysis_status_leaves_a_clean_citation_untouched(
    db_session, test_project, test_team
):
    git_source = KnowledgeSource(
        project_id=test_project, team_id=test_team, type="Git", name="repo"
    )
    db_session.add(git_source)
    db_session.commit()
    db_session.add(
        SourceScanFile(
            source_id=git_source.id, file_path="OK.cbl", content_hash="abc", parse_status="complete"
        )
    )
    db_session.commit()

    sources = [{"file": "OK.cbl", "lines": [1, 5], "source_id": git_source.id}]
    result = _attach_analysis_status(db_session, sources)

    assert "analysis_status" not in result[0]
    assert result[0]["provenance"]["source_name"] == "repo"


def test_attach_analysis_status_tolerates_a_source_without_source_id(db_session):
    # z.B. ein Fallback-Zitat ohne verknüpfte KnowledgeSource -- darf nicht crashen.
    sources = [{"file": "unknown.txt", "lines": None, "source_id": None}]
    result = _attach_analysis_status(db_session, sources)
    assert "analysis_status" not in result[0]
    assert result[0]["provenance"]["kind"] == "unknown"
    assert result[0]["provenance"]["verification_status"] == "unavailable"


def test_rejected_answer_still_lists_the_lines_the_tools_really_read():
    """O-346: eine verworfene Antwort darf nicht mit sources=[] enden, wenn Tools
    belegte Stellen geliefert haben."""
    from api.chat import _append_agent_source_fallback

    sources = [{"file": "a/Real.java", "lines": [10, 20]}]
    out = _append_agent_source_fallback("Nicht belegt.", sources, rejected=True)
    assert "`a/Real.java:10`" in out
    assert "keine Aussage zur Anfrage" in out
    assert _append_agent_source_fallback("Nicht belegt.", [], rejected=True) == "Nicht belegt."


def test_answer_with_one_verified_citation_keeps_its_text_and_flags_the_extra_one():
    """O-346: eine belegte Antwort mit zusätzlicher, nie abgerufener Nebenstelle
    (Live-Fall COBSWAIT/WAITSTEP.jcl) wird nicht verworfen, die Stelle wird markiert."""
    sources = [{"file": "app/cbl/COBSWAIT.cbl", "lines": [22, 40]}]
    answer = "Liest den Parameter in `app/cbl/COBSWAIT.cbl:36`; der JCL-Step steht in `app/jcl/WAITSTEP.jcl:26`."

    text, consistent = _validate_answer_sources(answer, sources)

    assert consistent
    assert "`app/cbl/COBSWAIT.cbl:36`" in text
    assert "`app/jcl/WAITSTEP.jcl:26`" not in text
    assert "app/jcl/WAITSTEP.jcl:26 (nicht belegt)" in text
    assert "nicht als Beleg verlinkt" in text


def test_answer_with_only_unverified_citations_is_still_rejected():
    sources = [{"file": "app/cbl/COBSWAIT.cbl", "lines": [22, 40]}]
    text, consistent = _validate_answer_sources("Siehe `app/jcl/WAITSTEP.jcl:26`.", sources)
    assert not consistent and "nicht belastbar belegt" in text


_ANSWER_CONTEXT = {
    "type": "tool_result",
    "name": "answer_context",
    "result": {
        "evidence": [{
            "symbol": "COBSWAIT",
            "entity": {"qualified_name": "COBSWAIT", "file_path": "app/cbl/COBSWAIT.cbl",
                       "start_line": 22, "end_line": 40},
            "callees": ["MVSWAIT (Zeile 38)"],
            "callers": [{"type": "EXECUTES", "from": "app/jcl/WAITSTEP.jcl::job:WAITSTEP::step:WAIT",
                         "line": 22, "location": "app/jcl/WAITSTEP.jcl:22"}],
            "call_sites": [{"file": "app/jcl/WAITSTEP.jcl", "around_line": 22,
                            "text": "18: //WAITSTEP JOB\n19: //WAIT EXEC PGM=COBSWAIT\n26: //SYSIN DD *"}],
        }],
    },
}


def test_answer_context_supplies_edges_and_sources_for_validation():
    """Live-Fall COBSWAIT: das Evidenzpaket nennt Aufrufer und Aufgerufene ausdrücklich."""
    edges = _extract_tool_edge_pairs(_ANSWER_CONTEXT)
    assert ("cobswait", "mvswait") in edges
    assert ("waitstep", "cobswait") in edges

    sources: list = []
    _extract_tool_sources(_ANSWER_CONTEXT, sources, 7)
    answer = "COBSWAIT ruft MVSWAIT auf (`app/cbl/COBSWAIT.cbl:38`); gestartet von `app/jcl/WAITSTEP.jcl:26`."
    text, consistent = _validate_answer_sources(answer, sources, edges)
    assert consistent
    assert "nicht belegt" not in text
    _, other = _validate_answer_sources("COBSWAIT ruft OTHERPGM auf.", sources, edges)
    assert not other


def test_quoted_call_statement_is_evidence_not_an_edge_claim():
    """Live-Fall COBSWAIT: „Zeile 38: CALL 'MVSWAIT' USING MVSWAIT-TIME“ zitiert den Beleg."""
    edges = {("cobswait", "mvswait")}
    for answer in (
        "Zeile 38: CALL 'MVSWAIT' USING MVSWAIT-TIME",
        "Aufruf in `CALL 'MVSWAIT' USING MVSWAIT-TIME` (Zeile 38).",
    ):
        _, consistent = _validate_answer_sources(answer, [], edges)
        assert consistent, answer
    _, invented = _validate_answer_sources("COBSWAIT ruft OTHERPGM auf", [], edges)
    assert not invented


def test_dots_inside_code_spans_do_not_split_a_sentence_into_a_false_edge_claim():
    """Live-Fall COBSWAIT: `COBSWAIT.cbl:36` zerschnitt den Satz mit dem zitierten CALL."""
    edges = {("cobswait", "mvswait")}
    answer = (
        "COBSWAIT liest den Parameter (`app/cbl/COBSWAIT.cbl:36`: `ACCEPT PARM-VALUE FROM SYSIN`), "
        "überträgt ihn nach `MVSWAIT-TIME` und übergibt ihn mit `CALL 'MVSWAIT' USING MVSWAIT-TIME`."
    )
    sources = [{"file": "app/cbl/COBSWAIT.cbl", "lines": [22, 40]}]
    text, consistent = _validate_answer_sources(answer, sources, edges)
    assert consistent and text.startswith("COBSWAIT liest")


def test_negated_statement_about_a_missing_edge_is_not_an_edge_claim():
    """Live-Fall C5: „keine nachgewiesene JCL-zu-COBOL-Kante“ ist die gewünschte Lückenaussage."""
    edges = {("cobswait", "mvswait")}
    for answer in (
        "Das ist ein Textbeleg, aber keine nachgewiesene Kante, die POSTTRAN ruft CBTRN02C aufruft.",
        "POSTTRAN ruft CBTRN02C nicht auf (Index).",
        "There is no edge: POSTTRAN calls CBTRN02C only in the README.",
    ):
        _, consistent = _validate_answer_sources(answer, [], edges)
        assert consistent, answer
    _, invented = _validate_answer_sources("POSTTRAN ruft CBTRN02C auf.", [], edges)
    assert not invented


def test_verified_answer_keeps_an_unbacked_edge_sentence_but_marks_it():
    """Live-Fall C5: eine zusätzliche JCL-Aussage ohne Flow-Beleg verwirft nicht die ganze Antwort."""
    sources = [{"file": "app/cbl/COBSWAIT.cbl", "lines": [22, 40]}]
    edges = {("cobswait", "mvswait")}
    answer = "COBSWAIT ruft MVSWAIT auf (`app/cbl/COBSWAIT.cbl:38`). Der JCL-Schritt ruft DFSRRC00 auf."

    text, consistent = _validate_answer_sources(answer, sources, edges)

    assert consistent
    assert "COBSWAIT ruft MVSWAIT auf" in text
    assert "ruft DFSRRC00 auf (Beziehung nicht im Index belegt)" in text
    assert "nicht im Index belegt" in text.rsplit("Hinweis", 1)[1]


def test_fenced_mermaid_block_is_neither_checked_nor_annotated():
    """Live-Fall Syncope: `n1 -->|CALLS| n2` im Mermaid-Block zählte als Kantenbehauptung."""
    sources = [{"file": "UserLogic.java", "lines": [100, 140]}]
    answer = (
        "`UserLogic.create` delegiert (`UserLogic.java:133`).\n\n"
        "```mermaid\nflowchart TD\n  n1[\"a\"] -->|CALLS| n2[\"b\"]\n```\n"
    )
    text, consistent = _validate_answer_sources(answer, sources, {("x", "y")})
    assert consistent and text == answer


def test_no_result_answer_gets_no_unrelated_read_locations_appended():
    """Live-Fall: „Die Suche lieferte keine Treffer“ hängte zufällig gelesene JCL-Zeilen an."""
    sources = [{"file": "app/jcl/POSTTRAN.jcl", "lines": [34, 34]}]
    text = "Die Suche nach „Autorisierung“ lieferte keine Treffer."
    assert _append_agent_source_fallback(text, sources) == text
    assert "POSTTRAN" in _append_agent_source_fallback("Der Job ruft CBTRN02C auf.", sources)


def test_answer_source_validation_replaces_an_empty_answer_with_a_notice():
    for empty in ("", "  \n"):
        answer, consistent = _validate_answer_sources(empty, [{"file": "src/A.java", "lines": [1, 5]}])
        assert not consistent
        assert "keine Antwort geliefert" in answer


def test_answer_source_validation_marks_file_names_no_tool_result_mentions():
    from api.chat import _tool_evidence_text

    steps = [{"type": "tool_result", "name": "answer_context", "result": {"copybooks": ["CMQV", "CCPAURQY.cpy"]}}]
    evidence = _tool_evidence_text(steps, "Welche Copybooks bindet `COPAUA0C.cbl` ein?")
    answer = "Genutzt werden `CCPAURQY.cpy`, `COPAUA0C.cbl` und `CICS-UTILITIES.cbl`."

    checked, consistent = _validate_answer_sources(answer, [], evidence_text=evidence)

    assert consistent
    assert "CICS-UTILITIES.cbl (nicht belegt)" in checked
    assert "`CCPAURQY.cpy`" in checked and "`COPAUA0C.cbl`" in checked
    assert "kommt in keinem abgerufenen Werkzeugergebnis vor" in checked


def test_answer_source_validation_skips_file_name_check_without_tool_evidence():
    answer = "Siehe `Irgendwo.cbl`."
    assert _validate_answer_sources(answer, [], evidence_text=None) == (answer, True)


def test_answer_context_origin_chain_and_copybooks_become_clickable_sources():
    """Fundstellen aus Herkunftskette und COPY-Liste landen in der Quellenliste (Datei und Zeile)."""
    agent_sources: list = []
    event = {
        "type": "tool_result",
        "name": "answer_context",
        "result": {"evidence": [{
            "entity": {"file_path": "cpy/AMT.cpy", "start_line": 34, "end_line": 34},
            "data_origin": [
                {"field": "AMT-OUT", "file": "cbl/PROG.cbl", "line": 885, "cite": "cbl/PROG.cbl:885"},
                {"field": "AMT-RAW", "file": "cbl/PROG.cbl", "line": 376, "cite": "cbl/PROG.cbl:376"},
            ],
            "includes": {
                "resolved": [{"name": "CPYREC", "line": 178, "cite": "cbl/PROG.cbl:178", "file": "cpy/CPYREC.cpy"}],
                "external": [{"name": "CMQV", "line": 161, "cite": "cbl/PROG.cbl:161", "category": "mq"}],
                "unresolved": [],
            },
        }]},
    }

    _extract_tool_sources(event, agent_sources, source_id=7)

    cited = {(item["file"], tuple(item["lines"])) for item in agent_sources}
    assert {("cbl/PROG.cbl", (885, 885)), ("cbl/PROG.cbl", (376, 376)), ("cbl/PROG.cbl", (178, 178)),
            ("cbl/PROG.cbl", (161, 161)), ("cpy/AMT.cpy", (34, 34))} <= cited
    # Eine solche Zitatform besteht die Validierung gegen die abgerufenen Quellen.
    answer, consistent = _validate_answer_sources("Zuweisung in `cbl/PROG.cbl:885` und `cbl/PROG.cbl:376`.", agent_sources)
    assert consistent and "nicht belegt" not in answer
