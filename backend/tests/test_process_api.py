from doctus_models.database import CodeEdge, CodeEntity, KnowledgeSource


def test_process_focus_is_bounded_and_keeps_code_edge_provenance(
    client, db_session, test_project, test_team
):
    source = KnowledgeSource(
        name="process-api-source",
        type="Git",
        project_id=test_project,
        team_id=test_team,
        branch="main",
        spaces={"last_commit_hash": "deadbeef1234"},
    )
    db_session.add(source)
    db_session.flush()
    root = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="Payment.java",
        name="execute",
        qualified_name="Payment#execute()",
        type="method",
        start_line=10,
        end_line=20,
        meta_json={"language": "java"},
    )
    target = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="Repository.java",
        name="save",
        qualified_name="Repository#save()",
        type="method",
        start_line=30,
        end_line=40,
        meta_json={"language": "java"},
    )
    db_session.add_all([root, target])
    db_session.flush()
    db_session.add_all(
        [
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=root.id,
                dst_entity_id=target.id,
                dst_name="Repository#save()",
                type="CALLS",
                resolution="resolved",
                src_start_line=14,
                src_end_line=14,
            ),
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=root.id,
                dst_name="auditService",
                type="CALLS",
                resolution="unresolved",
                src_start_line=16,
                src_end_line=16,
            ),
        ]
    )
    db_session.commit()
    try:
        response = client.get(
            "/process/focus",
            params={
                "entity_id": root.id,
                "project_id": test_project,
                "direction": "outgoing",
                "hops": 1,
                "node_limit": 10,
                "edge_limit": 10,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["root_node_id"] == f"entity:{root.id}"
        assert payload["truncation"]["node_limit"] == 10
        assert payload["truncation"]["edge_limit"] == 10
        assert len(payload["projection_id"]) > 10
        resolved = next(
            item
            for item in payload["transitions"]
            if item["code_edge_types"] == ["CALLS"] and item["certainty"] == "certain"
        )
        assert {
            key: resolved["locator"][key]
            for key in ("source_id", "file_path", "start_line", "end_line")
        } == {
            "source_id": source.id,
            "file_path": "Payment.java",
            "start_line": 14,
            "end_line": 14,
        }
        assert resolved["locator"]["provenance"]["kind"] == "code_fact"
        assert resolved["locator"]["provenance"]["verification_status"] == "indexed_unreviewed"
        assert resolved["locator"]["provenance"]["source_revision"] == "deadbeef1234"
        assert resolved["locator"]["provenance"]["branch"] == "main"
        assert any(node["kind"] == "external_call" for node in payload["nodes"])

        limited = client.get(
            "/process/focus",
            params={"entity_id": root.id, "project_id": test_project, "node_limit": 1},
        ).json()
        assert limited["truncation"]["truncated"] is True
        assert "node_limit" in limited["truncation"]["reasons"]
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_process_focus_caps_a_high_degree_node_before_serializing_it(
    client, db_session, test_project, test_team
):
    source = KnowledgeSource(
        name="process-high-degree", type="Git", project_id=test_project, team_id=test_team
    )
    db_session.add(source)
    db_session.flush()
    root = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="Dispatcher.java",
        name="dispatch",
        qualified_name="Dispatcher#dispatch()",
        type="method",
        start_line=1,
        end_line=5,
        meta_json={"language": "java"},
    )
    db_session.add(root)
    db_session.flush()
    db_session.add_all(
        [
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=root.id,
                dst_name=f"dynamicTarget{index}",
                type="CALLS",
                resolution="unresolved",
                src_start_line=3,
                src_end_line=3,
            )
            for index in range(2_501)
        ]
    )
    db_session.commit()
    try:
        response = client.get(
            "/process/focus",
            params={
                "entity_id": root.id,
                "project_id": test_project,
                "node_limit": 100,
                "edge_limit": 25,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["nodes"]) <= 100
        assert len(payload["transitions"]) <= 25
        assert payload["truncation"]["truncated"] is True
        assert "edge_limit" in payload["truncation"]["reasons"]
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_process_focus_projects_existing_cobol_flow_semantics_without_inventing_io(
    client, db_session, test_project, test_team
):
    source = KnowledgeSource(
        name="cobol-process", type="Git", project_id=test_project, team_id=test_team
    )
    db_session.add(source)
    db_session.flush()
    paragraph = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="PAYMENT.CBL",
        name="MAIN-PARA",
        qualified_name="PAYMENT.MAIN-PARA",
        type="paragraph",
        start_line=10,
        end_line=30,
        meta_json={"language": "cobol"},
    )
    target = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="PAYMENT.CBL",
        name="PROCESS-PARA",
        qualified_name="PAYMENT.PROCESS-PARA",
        type="paragraph",
        start_line=40,
        end_line=50,
        meta_json={"language": "cobol"},
    )
    sql_block = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="PAYMENT.CBL",
        name="SQL-BLOCK@22",
        qualified_name="PAYMENT.SQL-BLOCK@22",
        type="sql_block",
        start_line=22,
        end_line=25,
        meta_json={"language": "cobol", "statement_type": "SELECT"},
    )
    file_fd = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="PAYMENT.CBL",
        name="PAYMENT-FILE",
        qualified_name="PAYMENT.PAYMENT-FILE",
        type="file_fd",
        start_line=4,
        end_line=7,
        meta_json={"language": "cobol"},
    )
    db_session.add_all([paragraph, target, sql_block, file_fd])
    db_session.flush()
    db_session.add_all(
        [
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=paragraph.id,
                dst_entity_id=target.id,
                dst_name=target.name,
                type="PERFORM",
                resolution="resolved",
                src_start_line=14,
                src_end_line=14,
                meta_json={
                    "thru": "PROCESS-EXIT",
                    "thru_resolution": "resolved",
                    "thru_target_qualified_name": "PAYMENT.PROCESS-EXIT",
                },
            ),
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=paragraph.id,
                dst_name="DYNAMIC-AUDIT",
                type="CALL",
                resolution="dynamic",
                src_start_line=18,
                src_end_line=18,
            ),
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=paragraph.id,
                dst_entity_id=target.id,
                dst_name=target.name,
                type="GOTO",
                resolution="resolved",
                src_start_line=20,
                src_end_line=20,
            ),
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=paragraph.id,
                dst_entity_id=sql_block.id,
                dst_name=sql_block.name,
                type="USES",
                resolution="resolved",
                src_start_line=22,
                src_end_line=25,
            ),
        ]
    )
    db_session.commit()
    try:
        response = client.get(
            "/process/focus",
            params={"entity_id": paragraph.id, "project_id": test_project, "hops": 1},
        )
        assert response.status_code == 200
        payload = response.json()
        perform = next(
            item for item in payload["transitions"] if item["code_edge_types"] == ["PERFORM"]
        )
        assert perform["kind"] == "call"
        assert perform["meta"] == {
            "thru": "PROCESS-EXIT",
            "thru_resolution": "resolved",
            "thru_target_qualified_name": "PAYMENT.PROCESS-EXIT",
        }
        dynamic_call = next(
            item for item in payload["transitions"] if item["resolution"] == "dynamic"
        )
        assert dynamic_call["kind"] == "external_call"
        assert dynamic_call["certainty"] == "possible"
        assert (
            next(item for item in payload["transitions"] if item["code_edge_types"] == ["GOTO"])[
                "kind"
            ]
            == "jump"
        )
        assert any(
            node["id"] == f"entity:{sql_block.id}" and node["kind"] == "data_access"
            for node in payload["nodes"]
        )
        assert f"entity:{file_fd.id}" not in {node["id"] for node in payload["nodes"]}
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_process_focus_projects_java_execution_without_structure_edges(
    client, db_session, test_project, test_team
):
    source = KnowledgeSource(
        name="java-process", type="Git", project_id=test_project, team_id=test_team
    )
    db_session.add(source)
    db_session.flush()
    caller = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="TransferService.java",
        name="execute",
        qualified_name="TransferService#execute()",
        type="method",
        start_line=10,
        end_line=30,
        meta_json={"language": "java"},
    )
    declared_target = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="FraudCheck.java",
        name="check",
        qualified_name="FraudCheck#check()",
        type="method",
        start_line=10,
        end_line=20,
        meta_json={"language": "java"},
    )
    constructor = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="Audit.java",
        name="Audit",
        qualified_name="Audit#<init>()",
        type="constructor",
        start_line=3,
        end_line=5,
        meta_json={"language": "java"},
    )
    parent_type = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="TransferService.java",
        name="TransferService",
        qualified_name="TransferService",
        type="class",
        start_line=1,
        end_line=35,
        meta_json={"language": "java"},
    )
    db_session.add_all([caller, declared_target, constructor, parent_type])
    db_session.flush()
    db_session.add_all(
        [
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=caller.id,
                dst_entity_id=declared_target.id,
                dst_name=declared_target.qualified_name,
                type="CALLS",
                resolution="resolved",
                src_start_line=14,
                src_end_line=14,
                meta_json={
                    "language": "java",
                    "invocation_kind": "virtual",
                    "dispatch_scope": "static_declaration_only",
                },
            ),
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=caller.id,
                dst_entity_id=constructor.id,
                dst_name=constructor.qualified_name,
                type="INSTANTIATES",
                resolution="resolved",
                src_start_line=16,
                src_end_line=16,
                meta_json={"language": "java", "invocation_kind": "constructor"},
            ),
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=caller.id,
                dst_name="remoteAudit",
                type="CALLS",
                resolution="unresolved",
                src_start_line=18,
                src_end_line=18,
                meta_json={"language": "java", "invocation_kind": "virtual"},
            ),
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=parent_type.id,
                dst_entity_id=declared_target.id,
                dst_name=declared_target.qualified_name,
                type="EXTENDS",
                resolution="resolved",
                src_start_line=1,
                src_end_line=1,
            ),
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=caller.id,
                dst_entity_id=declared_target.id,
                dst_name=declared_target.qualified_name,
                type="USES_TYPE",
                resolution="resolved",
                src_start_line=12,
                src_end_line=12,
            ),
        ]
    )
    db_session.commit()
    try:
        response = client.get(
            "/process/focus",
            params={"entity_id": caller.id, "project_id": test_project, "hops": 1},
        )
        assert response.status_code == 200
        payload = response.json()
        virtual_call = next(
            item
            for item in payload["transitions"]
            if item["code_edge_types"] == ["CALLS"] and item["resolution"] == "resolved"
        )
        assert virtual_call["kind"] == "call"
        assert virtual_call["certainty"] == "possible"
        assert virtual_call["meta"]["dispatch_scope"] == "static_declaration_only"
        constructor_call = next(
            item for item in payload["transitions"] if item["code_edge_types"] == ["INSTANTIATES"]
        )
        assert constructor_call["kind"] == "call"
        assert constructor_call["certainty"] == "certain"
        external_call = next(
            item for item in payload["transitions"] if item["resolution"] == "unresolved"
        )
        assert external_call["kind"] == "external_call"
        assert external_call["certainty"] == "unresolved"
        assert {"EXTENDS", "USES_TYPE"}.isdisjoint(
            {edge_type for item in payload["transitions"] for edge_type in item["code_edge_types"]}
        )
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_process_focus_exposes_branches_cycles_and_only_observed_order(
    client, db_session, test_project, test_team
):
    source = KnowledgeSource(
        name="process-semantics", type="Git", project_id=test_project, team_id=test_team
    )
    db_session.add(source)
    db_session.flush()
    root = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="FLOW.CBL",
        name="MAIN",
        qualified_name="FLOW.MAIN",
        type="paragraph",
        start_line=10,
        end_line=20,
        meta_json={"language": "cobol"},
    )
    left = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="FLOW.CBL",
        name="LEFT",
        qualified_name="FLOW.LEFT",
        type="paragraph",
        start_line=30,
        end_line=35,
        meta_json={"language": "cobol"},
    )
    right = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="FLOW.CBL",
        name="RIGHT",
        qualified_name="FLOW.RIGHT",
        type="paragraph",
        start_line=40,
        end_line=45,
        meta_json={"language": "cobol"},
    )
    db_session.add_all([root, left, right])
    db_session.flush()
    db_session.add_all(
        [
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=root.id,
                dst_entity_id=left.id,
                dst_name=left.name,
                type="GOTO",
                resolution="resolved",
                src_start_line=14,
                src_end_line=14,
            ),
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=root.id,
                dst_entity_id=right.id,
                dst_name=right.name,
                type="GOTO",
                resolution="resolved",
                src_start_line=14,
                src_end_line=14,
            ),
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=left.id,
                dst_entity_id=left.id,
                dst_name=left.name,
                type="PERFORM",
                resolution="resolved",
                src_start_line=32,
                src_end_line=32,
                meta_json={"sequence": 4, "condition": "UNTIL EOF"},
            ),
        ]
    )
    db_session.commit()
    try:
        response = client.get(
            "/process/focus",
            params={"entity_id": root.id, "project_id": test_project, "hops": 2},
        )
        assert response.status_code == 200
        transitions = response.json()["transitions"]
        branches = [item for item in transitions if item["code_edge_types"] == ["GOTO"]]
        assert len(branches) == 2
        assert all(
            item["kind"] == "branch" and item["certainty"] == "possible" for item in branches
        )
        assert all(item["meta"]["multiple_targets"] is True for item in branches)
        recursion = next(item for item in transitions if item["source"] == item["target"])
        assert recursion["meta"]["cycle"] is True
        assert recursion["meta"]["recursion"] is True
        assert recursion["sequence"] == 4
        assert recursion["condition"] == "UNTIL EOF"
        assert all(item["sequence"] is None for item in branches)
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_process_focus_passes_control_path_and_loop_and_survives_list_context(
    client, db_session, test_project, test_team
):
    source = KnowledgeSource(
        name="process-control-path", type="Git", project_id=test_project, team_id=test_team
    )
    db_session.add(source)
    db_session.flush()
    entities = [
        CodeEntity(
            project_id=test_project,
            source_id=source.id,
            file_path="FLOW.CBL",
            name=name,
            qualified_name=f"FLOW.{name}",
            type="paragraph",
            start_line=line,
            end_line=line + 4,
            meta_json={"language": "cobol"},
        )
        for name, line in (("MAIN", 10), ("ONE", 30), ("LOOPED", 40))
    ]
    db_session.add_all(entities)
    db_session.flush()
    root, one, looped = entities
    path = [{"type": "IF", "branch": "THEN", "condition": "WS-A = 'Y'"}]
    db_session.add_all(
        [
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=root.id,
                dst_entity_id=one.id,
                dst_name=one.name,
                type="PERFORM",
                resolution="resolved",
                src_start_line=12,
                src_end_line=12,
                # COBOL liefert control_context als Liste; das darf die Projektion nicht kippen.
                meta_json={
                    "control_context": [{"type": "IF", "branch": "THEN"}],
                    "control_path": path,
                },
            ),
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=root.id,
                dst_entity_id=looped.id,
                dst_name=looped.name,
                type="PERFORM",
                resolution="resolved",
                src_start_line=14,
                src_end_line=14,
                meta_json={"loop": {"kind": "UNTIL", "text": "WS-A = 'N'"}},
            ),
        ]
    )
    db_session.commit()
    try:
        response = client.get(
            "/process/focus", params={"entity_id": root.id, "project_id": test_project, "hops": 1}
        )
        assert response.status_code == 200
        by_target = {item["target"]: item for item in response.json()["transitions"]}
        conditional = by_target[f"entity:{one.id}"]
        assert conditional["kind"] == "call"
        assert conditional["condition"] is None
        assert conditional["meta"]["control_path"] == path
        loop = by_target[f"entity:{looped.id}"]
        assert loop["kind"] == "iteration"
        assert loop["meta"]["loop"] == {"kind": "UNTIL", "text": "WS-A = 'N'"}

        only_calls = client.get(
            "/process/focus",
            params={
                "entity_id": root.id,
                "project_id": test_project,
                "hops": 1,
                "kinds": "iteration",
            },
        )
        assert only_calls.status_code == 200
        assert [item["kind"] for item in only_calls.json()["transitions"]] == ["iteration"]
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_process_helpers_map_loops_to_iteration_and_never_return_list_conditions():
    """DB-frei: die Ableitung, die der Endpunkt-Test oben über die API prüft."""
    from api.process import _condition_text, _transition_kind

    perform = CodeEdge(
        type="PERFORM", resolution="resolved", meta_json={"loop": {"kind": "UNTIL", "text": "X"}}
    )
    assert _transition_kind(perform) == "iteration"
    assert _transition_kind(CodeEdge(type="PERFORM", resolution="resolved", meta_json={})) == "call"
    assert (
        _transition_kind(
            CodeEdge(type="PERFORM", resolution="unresolved", meta_json={"loop": {"kind": "TIMES"}})
        )
        == "external_call"
    )
    assert _transition_kind(CodeEdge(type="GOTO", resolution="resolved", meta_json={})) == "jump"

    assert _condition_text({"condition": "UNTIL EOF"}) == "UNTIL EOF"
    assert _condition_text({"control_context": "catch(IOException)"}) == "catch(IOException)"
    assert _condition_text({"control_context": [{"type": "IF", "branch": "THEN"}]}) is None
    assert _condition_text({}) is None


def test_process_focus_on_a_cobol_program_starts_at_its_entry_paragraph(
    client, db_session, test_project, test_team
):
    """Die Kanten hängen an Paragraphen: ein Programm als Einstieg lieferte nur den Wurzelknoten."""
    source = KnowledgeSource(
        name="process-program-entry",
        type="Git",
        project_id=test_project,
        team_id=test_team,
        branch="main",
    )
    db_session.add(source)
    db_session.flush()
    program = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="PAY.cbl",
        name="PAY",
        qualified_name="PAY",
        type="program",
        start_line=1,
        end_line=60,
        meta_json={"language": "cobol"},
    )
    db_session.add(program)
    db_session.flush()

    def paragraph(name, start):
        item = CodeEntity(
            project_id=test_project,
            source_id=source.id,
            file_path="PAY.cbl",
            name=name,
            qualified_name=f"PAY.{name}",
            type="paragraph",
            start_line=start,
            end_line=start + 5,
            parent_id=program.id,
            meta_json={"language": "cobol"},
        )
        db_session.add(item)
        db_session.flush()
        return item

    main, init = paragraph("MAIN-PARA", 10), paragraph("1000-INIT", 20)
    db_session.add(
        CodeEdge(
            project_id=test_project,
            source_id=source.id,
            src_entity_id=main.id,
            dst_entity_id=init.id,
            dst_name="1000-INIT",
            type="PERFORM",
            resolution="resolved",
            src_start_line=12,
            src_end_line=12,
        )
    )
    db_session.commit()
    try:
        body = client.get(
            "/process/focus",
            params={"entity_id": program.id, "project_id": test_project, "hops": 1},
        ).json()
        assert body["root_node_id"] == f"entity:{main.id}"
        assert [(t["source"], t["target"]) for t in body["transitions"]] == [
            (f"entity:{main.id}", f"entity:{init.id}")
        ]

        paragraph("MAIN", 30)  # Der Name zählt nicht: COBOL beginnt beim ersten Paragraphen.
        body = client.get(
            "/process/focus", params={"entity_id": program.id, "project_id": test_project}
        ).json()
        assert body["root_node_id"] == f"entity:{main.id}"
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def _cobol_program(db_session, project, team):
    source = KnowledgeSource(
        name="process-cics", type="Git", project_id=project, team_id=team, branch="main", spaces={}
    )
    db_session.add(source)
    db_session.flush()

    def entity(name, type_, line, parent=None, meta=None):
        row = CodeEntity(
            project_id=project,
            source_id=source.id,
            file_path="SIGNON.cbl",
            name=name,
            qualified_name=f"SIGNON.{name}",
            type=type_,
            start_line=line,
            end_line=line + 1,
            parent_id=parent.id if parent else None,
            meta_json={"language": "cobol", **(meta or {})},
        )
        db_session.add(row)
        db_session.flush()
        return row

    def edge(src, dst, type_, line, dst_name=None, resolution="resolved", meta=None):
        db_session.add(
            CodeEdge(
                project_id=project,
                source_id=source.id,
                src_entity_id=src.id,
                dst_entity_id=dst.id if dst else None,
                dst_name=dst_name or dst.name,
                type=type_,
                resolution=resolution,
                src_start_line=line,
                src_end_line=line,
                meta_json=meta or {},
            )
        )

    def remove_source():
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()

    return entity, edge, remove_source


def test_process_focus_shows_exec_statements_in_the_flow_of_their_paragraph(
    client, db_session, test_project, test_team
):
    entity, edge, remove_source = _cobol_program(db_session, test_project, test_team)
    program = entity("SIGNON", "program", 1)
    para = entity("LOGIN-PARA", "paragraph", 10, program)
    guard = [{"type": "IF", "branch": "THEN", "condition": "WS-ADMIN"}]
    transfer = entity(
        "EXEC-CICS-BLOCK@20", "exec_block", 20, program, {"dialect": "CICS", "operation": "XCTL"}
    )
    dynamic = entity(
        "EXEC-CICS-BLOCK@25", "exec_block", 25, program, {"dialect": "CICS", "operation": "XCTL"}
    )
    read = entity(
        "EXEC-CICS-BLOCK@30",
        "exec_block",
        30,
        program,
        {"dialect": "CICS", "operation": "READ", "resources": ["USRSEC"]},
    )
    done = entity(
        "EXEC-CICS-BLOCK@40", "exec_block", 40, program, {"dialect": "CICS", "operation": "RETURN"}
    )
    other_program = entity("COADM01C", "program", 1)
    edge(para, transfer, "CONTAINS", 20, meta={"control_path": guard})
    edge(transfer, other_program, "CALL", 20, meta={"invocation_kind": "cics_xctl"})
    edge(para, dynamic, "CONTAINS", 25)
    edge(
        dynamic,
        None,
        "CALL",
        25,
        dst_name="CDEMO-TO-PROGRAM",
        resolution="dynamic",
        meta={"invocation_kind": "cics_xctl", "candidate_targets": ["COMEN01C"]},
    )
    edge(para, read, "CONTAINS", 30)
    edge(para, done, "CONTAINS", 40)
    edge(read, None, "EXECUTES", 30, dst_name="READ")
    db_session.commit()

    response = client.get(
        f"/process/focus?entity_id={para.id}&hops=1&direction=outgoing&project_id={test_project}"
    )
    assert response.status_code == 200
    payload = response.json()
    labels = {node["id"]: node["label"] for node in payload["nodes"]}
    steps = {
        labels[item["target"]]: item
        for item in sorted(payload["transitions"], key=lambda item: item["locator"]["start_line"])
    }

    assert set(steps) == {"COADM01C", "CDEMO-TO-PROGRAM", "CICS READ USRSEC", "CICS RETURN"}
    call = steps["COADM01C"]
    assert call["source"] == f"entity:{para.id}"
    assert call["kind"] == "call"
    assert call["meta"]["invocation_kind"] == "cics_xctl"
    assert call["meta"]["control_path"] == guard
    assert steps["CDEMO-TO-PROGRAM"]["kind"] == "external_call"
    assert steps["CDEMO-TO-PROGRAM"]["meta"]["candidate_targets"] == ["COMEN01C"]
    assert steps["CICS READ USRSEC"]["kind"] == "step"
    assert steps["CICS RETURN"]["kind"] == "exit"

    # Aufgeklappt zeigt der Block seine Daten, nicht die Operation aus seiner eigenen Bezeichnung.
    opened = client.get(
        f"/process/focus?entity_id={read.id}&hops=1&direction=outgoing&project_id={test_project}"
    ).json()
    assert opened["transitions"] == []
    remove_source()


def test_process_focus_on_a_program_starts_at_the_first_procedure_paragraph(
    client, db_session, test_project, test_team
):
    entity, edge, remove_source = _cobol_program(db_session, test_project, test_team)
    program = entity("SIGNON", "program", 1)
    program.end_line = 100
    entity("WORKING-STORAGE", "section", 5, program)
    first = entity("0000-MAIN", "paragraph", 50, program)
    other = entity("1000-INIT", "paragraph", 80, program)
    edge(first, other, "PERFORM", 55)
    db_session.commit()

    payload = client.get(
        f"/process/focus?entity_id={program.id}&hops=1&direction=outgoing&project_id={test_project}"
    ).json()

    assert payload["root_node_id"] == f"entity:{first.id}"
    assert [item["target"] for item in payload["transitions"]] == [f"entity:{other.id}"]
    remove_source()


def _java_unit(db_session, project, team):
    source = KnowledgeSource(
        name="process-java", type="Git", project_id=project, team_id=team, branch="main", spaces={}
    )
    db_session.add(source)
    db_session.flush()

    def entity(name, type_, start, end, parent=None, meta=None):
        row = CodeEntity(
            project_id=project,
            source_id=source.id,
            file_path="Flow.java",
            name=name,
            qualified_name=f"Flow#{name}",
            type=type_,
            start_line=start,
            end_line=end,
            parent_id=parent.id if parent else None,
            meta_json={"language": "java", **(meta or {})},
        )
        db_session.add(row)
        db_session.flush()
        return row

    def remove():
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()

    return source, entity, remove


def test_entry_routines_show_the_methods_of_a_java_file_and_mark_getters(
    client, db_session, test_project, test_team
):
    _, entity, remove = _java_unit(db_session, test_project, test_team)
    unit = entity("Flow.java", "compilation_unit", 1, 40)
    cls = entity("Flow", "class", 3, 40)
    run = entity("run", "method", 5, 20, cls, {"parameter_types": []})
    getter = entity(
        "getName",
        "method",
        22,
        26,
        cls,
        {"parameter_types": [], "return_expressions": [{"expression": "this.name"}]},
    )
    heavy = entity(
        "getReport",
        "method",
        28,
        30,
        cls,
        {"parameter_types": [], "return_expressions": [{"expression": "build(name)"}]},
    )
    db_session.commit()

    def focus(entity_id, **params):
        return client.get(
            "/process/focus",
            params={"entity_id": entity_id, "project_id": test_project, **params},
        ).json()

    for root in (unit, cls):
        body = focus(root.id, entry_routines=True)
        steps = {item["target"]: item for item in body["transitions"]}
        assert set(steps) == {f"entity:{run.id}", f"entity:{getter.id}", f"entity:{heavy.id}"}
        assert all(item["origin_kind"] == "synthetic" for item in steps.values())
        assert steps[f"entity:{getter.id}"]["meta"]["helper"] == "accessor"
        assert "helper" not in steps[f"entity:{heavy.id}"]["meta"]

    assert focus(cls.id)["transitions"] == []
    assert focus(run.id, entry_routines=True)["transitions"] == []
    remove()


def test_logging_and_simple_getter_calls_are_marked_as_helpers(
    client, db_session, test_project, test_team
):
    source, entity, remove = _java_unit(db_session, test_project, test_team)
    run = entity("run", "method", 5, 20)
    short = entity("getName", "method", 22, 24)
    long = entity("getReport", "method", 26, 38)

    def call(name, dst=None, **meta):
        db_session.add(
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=run.id,
                dst_entity_id=dst.id if dst else None,
                dst_name=name,
                type="CALLS",
                resolution="resolved" if dst else "unresolved",
                src_start_line=6,
                src_end_line=6,
                meta_json=meta,
            )
        )

    call("LOG.info", receiver="LOG", method_name="info", argument_count=1)
    call("Objects.requireNonNull", receiver="Objects", method_name="requireNonNull", argument_count=1)
    call("getName", short, method_name="getName", argument_count=0)
    call("getReport", long, method_name="getReport", argument_count=0)
    call("store", method_name="store", argument_count=2)
    db_session.commit()

    body = client.get(
        "/process/focus", params={"entity_id": run.id, "project_id": test_project}
    ).json()
    labels = {node["id"]: node["label"] for node in body["nodes"]}
    helpers = {labels[item["target"]]: item["meta"].get("helper") for item in body["transitions"]}
    assert helpers == {
        "LOG.info": "logging",
        "Objects.requireNonNull": "precondition",
        "getName": "accessor",
        "getReport": None,
        "store": None,
    }
    remove()


def test_process_focus_shows_where_a_routine_ends_the_run(
    client, db_session, test_project, test_team
):
    entity, _, remove_source = _cobol_program(db_session, test_project, test_team)
    guard = [{"type": "IF", "branch": "THEN", "condition": "WS-A"}]
    para = entity(
        "MAIN-PARA",
        "paragraph",
        10,
        meta={
            "exits": [
                {"statement": "STOP RUN", "line": 12, "control_path": guard},
                {"statement": "GOBACK", "line": 14},
            ]
        },
    )
    db_session.commit()

    def focus(**params):
        return client.get(
            "/process/focus",
            params={"entity_id": para.id, "project_id": test_project, **params},
        ).json()

    body = focus()
    labels = {node["id"]: node["label"] for node in body["nodes"]}
    steps = {labels[item["target"]]: item for item in body["transitions"]}
    assert set(steps) == {"STOP RUN", "GOBACK"}
    assert steps["STOP RUN"]["kind"] == "exit"
    assert steps["STOP RUN"]["locator"]["start_line"] == 12
    assert steps["STOP RUN"]["meta"]["control_path"] == guard
    assert steps["GOBACK"]["origin_kind"] == "synthetic"

    assert focus(direction="incoming")["transitions"] == []
    assert focus(kinds="call")["transitions"] == []
    remove_source()


def test_program_entry_finds_a_paragraph_inside_a_section(
    client, db_session, test_project, test_team
):
    entity, edge, remove_source = _cobol_program(db_session, test_project, test_team)
    program = entity("SIGNON", "program", 1)
    program.end_line = 100
    section = entity("MAIN-SECTION", "section", 20, program)
    first = entity("FIRST-PARA", "paragraph", 21, section)
    later = entity("LATER-PARA", "paragraph", 50, program)
    edge(first, later, "PERFORM", 22)
    db_session.commit()

    body = client.get(
        "/process/focus", params={"entity_id": program.id, "project_id": test_project}
    ).json()
    assert body["root_node_id"] == f"entity:{first.id}"
    remove_source()

