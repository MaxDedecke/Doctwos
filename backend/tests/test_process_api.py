from models.database import CodeEdge, CodeEntity, KnowledgeSource


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
        resolved = next(item for item in payload["transitions"] if item["code_edge_types"] == ["CALLS"] and item["certainty"] == "certain")
        assert {key: resolved["locator"][key] for key in ("source_id", "file_path", "start_line", "end_line")} == {
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
                meta_json={"thru": "PROCESS-EXIT"},
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
        perform = next(item for item in payload["transitions"] if item["code_edge_types"] == ["PERFORM"])
        assert perform["kind"] == "call"
        assert perform["meta"] == {"thru": "PROCESS-EXIT"}
        dynamic_call = next(item for item in payload["transitions"] if item["resolution"] == "dynamic")
        assert dynamic_call["kind"] == "external_call"
        assert dynamic_call["certainty"] == "possible"
        assert next(item for item in payload["transitions"] if item["code_edge_types"] == ["GOTO"])["kind"] == "jump"
        assert any(node["id"] == f"entity:{sql_block.id}" and node["kind"] == "data_access" for node in payload["nodes"])
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
                project_id=test_project, source_id=source.id,
                src_entity_id=caller.id, dst_entity_id=declared_target.id,
                dst_name=declared_target.qualified_name, type="CALLS", resolution="resolved",
                src_start_line=14, src_end_line=14,
                meta_json={"language": "java", "invocation_kind": "virtual", "dispatch_scope": "static_declaration_only"},
            ),
            CodeEdge(
                project_id=test_project, source_id=source.id,
                src_entity_id=caller.id, dst_entity_id=constructor.id,
                dst_name=constructor.qualified_name, type="INSTANTIATES", resolution="resolved",
                src_start_line=16, src_end_line=16,
                meta_json={"language": "java", "invocation_kind": "constructor"},
            ),
            CodeEdge(
                project_id=test_project, source_id=source.id,
                src_entity_id=caller.id, dst_name="remoteAudit", type="CALLS", resolution="unresolved",
                src_start_line=18, src_end_line=18,
                meta_json={"language": "java", "invocation_kind": "virtual"},
            ),
            CodeEdge(
                project_id=test_project, source_id=source.id,
                src_entity_id=parent_type.id, dst_entity_id=declared_target.id,
                dst_name=declared_target.qualified_name, type="EXTENDS", resolution="resolved",
                src_start_line=1, src_end_line=1,
            ),
            CodeEdge(
                project_id=test_project, source_id=source.id,
                src_entity_id=caller.id, dst_entity_id=declared_target.id,
                dst_name=declared_target.qualified_name, type="USES_TYPE", resolution="resolved",
                src_start_line=12, src_end_line=12,
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
        virtual_call = next(item for item in payload["transitions"] if item["code_edge_types"] == ["CALLS"] and item["resolution"] == "resolved")
        assert virtual_call["kind"] == "call"
        assert virtual_call["certainty"] == "possible"
        assert virtual_call["meta"]["dispatch_scope"] == "static_declaration_only"
        constructor_call = next(item for item in payload["transitions"] if item["code_edge_types"] == ["INSTANTIATES"])
        assert constructor_call["kind"] == "call"
        assert constructor_call["certainty"] == "certain"
        external_call = next(item for item in payload["transitions"] if item["resolution"] == "unresolved")
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
        project_id=test_project, source_id=source.id, file_path="FLOW.CBL",
        name="MAIN", qualified_name="FLOW.MAIN", type="paragraph",
        start_line=10, end_line=20, meta_json={"language": "cobol"},
    )
    left = CodeEntity(
        project_id=test_project, source_id=source.id, file_path="FLOW.CBL",
        name="LEFT", qualified_name="FLOW.LEFT", type="paragraph",
        start_line=30, end_line=35, meta_json={"language": "cobol"},
    )
    right = CodeEntity(
        project_id=test_project, source_id=source.id, file_path="FLOW.CBL",
        name="RIGHT", qualified_name="FLOW.RIGHT", type="paragraph",
        start_line=40, end_line=45, meta_json={"language": "cobol"},
    )
    db_session.add_all([root, left, right])
    db_session.flush()
    db_session.add_all(
        [
            CodeEdge(
                project_id=test_project, source_id=source.id, src_entity_id=root.id,
                dst_entity_id=left.id, dst_name=left.name, type="GOTO", resolution="resolved",
                src_start_line=14, src_end_line=14,
            ),
            CodeEdge(
                project_id=test_project, source_id=source.id, src_entity_id=root.id,
                dst_entity_id=right.id, dst_name=right.name, type="GOTO", resolution="resolved",
                src_start_line=14, src_end_line=14,
            ),
            CodeEdge(
                project_id=test_project, source_id=source.id, src_entity_id=left.id,
                dst_entity_id=left.id, dst_name=left.name, type="PERFORM", resolution="resolved",
                src_start_line=32, src_end_line=32, meta_json={"sequence": 4, "condition": "UNTIL EOF"},
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
        assert all(item["kind"] == "branch" and item["certainty"] == "possible" for item in branches)
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
