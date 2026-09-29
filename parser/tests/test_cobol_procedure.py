import os

from cobol import divisions, embedded, lexer, procedure, source_format

FIXTURES = os.path.join(os.path.dirname(__file__), "cobol_corpus", "fixtures")


def _edges(text: str, fmt: str = "fixed"):
    lines = source_format.split_logical_lines(text, fmt)
    masked, _ = embedded.mask(lines)
    tokens = lexer.tokenize(masked)
    programs, div_errors, _ = divisions.scan(masked)
    program = programs[0]
    edges, proc_errors = procedure.scan(program, tokens, masked)
    return program, edges, div_errors + proc_errors


def _edges_from_fixture(name: str, fmt: str = "fixed"):
    with open(os.path.join(FIXTURES, name)) as f:
        text = f.read()
    return _edges(text, fmt)


def test_dynamic_call_is_marked_dynamic_not_unresolved():
    _, edges, errors = _edges_from_fixture("09_dynamic_call.cbl")
    assert errors == []
    call_ws_pgm = next(e for e in edges if e.dst_name == "WS-PGM")
    assert call_ws_pgm.type == "CALL"
    assert call_ws_pgm.resolution == "dynamic"
    assert call_ws_pgm.scope is None


def test_static_literal_call_is_unresolved_until_pass_two():
    _, edges, errors = _edges_from_fixture("09_dynamic_call.cbl")
    assert errors == []
    call_literal = next(e for e in edges if e.dst_name == "FIXEDPGM")
    assert call_literal.type == "CALL"
    assert call_literal.resolution == "unresolved"
    assert call_literal.src_name == "MAIN-PARA"


def test_perform_thru_resolves_locally_and_carries_thru_in_meta():
    program, edges, errors = _edges_from_fixture("10_perform_thru.cbl")
    assert errors == []
    perform = next(e for e in edges if e.dst_name == "INIT-PARA")
    assert perform.type == "PERFORM"
    assert perform.resolution == "resolved"
    assert perform.meta == {
        "thru": "CLEANUP-PARA",
        "thru_resolution": "resolved",
        "thru_target_qualified_name": "PERFTHRU.CLEANUP-PARA",
        "program": "PERFTHRU",
    }
    assert perform.scope == program.name == "PERFTHRU"


def test_perform_of_unknown_paragraph_stays_unresolved():
    _, edges, errors = _edges_from_fixture("10_perform_thru.cbl")
    assert errors == []
    perform = next(e for e in edges if e.dst_name == "UNKNOWN-PARA")
    assert perform.resolution == "unresolved"
    assert "thru" not in perform.meta


def test_go_to_known_paragraph_resolves_locally():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. GOTOTEST.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           GO TO NEXT-PARA.\n"
        "       NEXT-PARA.\n"
        "           DISPLAY 'X'.\n"
        "           GO TO UNKNOWN-PARA.\n"
    )
    program, edges, errors = _edges(text)
    assert errors == []
    goto_known = next(e for e in edges if e.dst_name == "NEXT-PARA")
    assert goto_known.type == "GOTO"
    assert goto_known.resolution == "resolved"
    assert goto_known.src_name == "MAIN-PARA"
    assert goto_known.scope == program.name

    goto_unknown = next(e for e in edges if e.dst_name == "UNKNOWN-PARA")
    assert goto_unknown.resolution == "unresolved"
    assert goto_unknown.src_name == "NEXT-PARA"


def test_inline_perform_until_produces_no_edge_but_scans_its_body():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. INLINEPERF.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           PERFORM UNTIL WS-DONE = 'Y'\n"
        "               CALL 'INNER-PGM'\n"
        "           END-PERFORM.\n"
        "           STOP RUN.\n"
    )
    _, edges, errors = _edges(text)
    assert errors == []
    assert [e.type for e in edges] == ["CALL"]
    assert edges[0].dst_name == "INNER-PGM"


def test_no_procedure_division_reports_error_without_crashing():
    text = "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. NOPROC.\n"
    lines = source_format.split_logical_lines(text, "fixed")
    masked, _ = embedded.mask(lines)
    tokens = lexer.tokenize(masked)
    programs, _, _ = divisions.scan(masked)
    edges, errors = procedure.scan(programs[0], tokens)

    assert edges == []
    assert errors != []


def test_goto_inside_if_else_does_not_produce_keyword_targets():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. O360GOTO.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           IF WS-FLAG = 1\n"
        "               GO TO DONE-PARA\n"
        "           ELSE\n"
        "               DISPLAY 'Y'\n"
        "           END-IF.\n"
        "       DONE-PARA.\n"
        "           STOP RUN.\n"
    )
    _, edges, errors = _edges(text)
    assert errors == []
    gotos = [e for e in edges if e.type == "GOTO"]
    assert len(gotos) == 1
    assert gotos[0].dst_name == "DONE-PARA"
    assert gotos[0].src_start_line == 6
    assert gotos[0].src_end_line == 6
    assert gotos[0].meta.get("control_context") == [{"type": "IF", "branch": "THEN"}]


def test_perform_times_n_times_does_not_produce_perform_edge():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. O360PERF.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           PERFORM TIMES-N TIMES\n"
        "               DISPLAY 'X'\n"
        "           END-PERFORM.\n"
        "           STOP RUN.\n"
    )
    _, edges, errors = _edges(text)
    assert errors == []
    perf_edges = [e for e in edges if e.type == "PERFORM"]
    assert perf_edges == []


def test_goto_depending_on_captures_all_targets():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. O360DEP.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           GO TO PARA-1 PARA-2 PARA-3 DEPENDING ON WS-IDX.\n"
        "       PARA-1.\n"
        "           STOP RUN.\n"
        "       PARA-2.\n"
        "           STOP RUN.\n"
        "       PARA-3.\n"
        "           STOP RUN.\n"
    )
    _, edges, errors = _edges(text)
    assert errors == []
    gotos = [e for e in edges if e.type == "GOTO"]
    assert [g.dst_name for g in gotos] == ["PARA-1", "PARA-2", "PARA-3"]
    assert all(g.resolution == "resolved" for g in gotos)


_FLOW_PROGRAM = (
    "       IDENTIFICATION DIVISION.\n"
    "       PROGRAM-ID. FLOWDEMO.\n"
    "       PROCEDURE DIVISION.\n"
    "       MAIN-PARA.\n"
    "           IF WS-A = 'Y'\n"
    "               PERFORM ONE-PARA\n"
    "           ELSE\n"
    "               PERFORM TWO-PARA\n"
    "           END-IF\n"
    "           PERFORM THREE-PARA UNTIL WS-A = 'N'\n"
    "           PERFORM THREE-PARA 3 TIMES\n"
    "           PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > 5\n"
    "               PERFORM ONE-PARA\n"
    "           END-PERFORM\n"
    "           PERFORM ONE-PARA\n"
    "           EVALUATE WS-A\n"
    "               WHEN 'A'\n"
    "                   PERFORM ONE-PARA\n"
    "               WHEN OTHER\n"
    "                   GO TO TWO-PARA\n"
    "           END-EVALUATE\n"
    "           STOP RUN.\n"
    "       ONE-PARA.\n"
    "           EXIT.\n"
    "       TWO-PARA.\n"
    "           EXIT.\n"
    "       THREE-PARA.\n"
    "           EXIT.\n"
)


def _flow_edges():
    _, edges, errors = _edges(_FLOW_PROGRAM)
    assert errors == []
    return {(e.type, e.dst_name, e.src_start_line): e for e in edges}


def test_control_path_records_condition_text_and_branch():
    edges = _flow_edges()
    assert edges[("PERFORM", "ONE-PARA", 6)].meta["control_path"] == [
        {"type": "IF", "branch": "THEN", "condition": "WS-A = 'Y'"}
    ]
    assert edges[("PERFORM", "TWO-PARA", 8)].meta["control_path"] == [
        {"type": "IF", "branch": "ELSE", "condition": "WS-A = 'Y'"}
    ]
    # stabiler Vertrag: control_context bleibt unverändert
    assert edges[("PERFORM", "ONE-PARA", 6)].meta["control_context"] == [{"type": "IF", "branch": "THEN"}]


def test_control_path_records_evaluate_when_and_scope_end():
    edges = _flow_edges()
    assert edges[("PERFORM", "ONE-PARA", 18)].meta["control_path"] == [
        {"type": "EVALUATE", "branch": "WHEN", "subject": "WS-A", "when": "'A'"}
    ]
    assert edges[("GOTO", "TWO-PARA", 20)].meta["control_path"][0]["when"] == "OTHER"


def test_out_of_line_perform_carries_loop_head():
    edges = _flow_edges()
    assert edges[("PERFORM", "THREE-PARA", 10)].meta["loop"] == {"kind": "UNTIL", "text": "WS-A = 'N'"}
    assert edges[("PERFORM", "THREE-PARA", 11)].meta["loop"] == {"kind": "TIMES", "text": "3"}
    assert "loop" not in edges[("PERFORM", "ONE-PARA", 15)].meta


def test_inline_perform_loop_scopes_only_its_body():
    edges = _flow_edges()
    assert edges[("PERFORM", "ONE-PARA", 13)].meta["control_path"] == [
        {"type": "LOOP", "kind": "VARYING", "text": "WS-I FROM 1 BY 1 UNTIL WS-I > 5"}
    ]
    # nach END-PERFORM / END-IF / END-EVALUATE: kein Kontext mehr
    assert "control_path" not in edges[("PERFORM", "ONE-PARA", 15)].meta
