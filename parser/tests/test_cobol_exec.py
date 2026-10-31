from cobol.parse import parse_program
from cobol.persistence import resolve_local_target


def test_cics_exec_has_clickable_block_operation_and_literal_resources():
    result = parse_program(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. CICSDEMO.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           EXEC CICS\n"
        "               LINK PROGRAM('PAYMENT') COMMAREA(WS-COMMAREA)\n"
        "               FILE('CUSTOMER')\n"
        "           END-EXEC.\n",
        "CICSDEMO.CBL",
    )

    block = next(entity for entity in result.entities if entity.type == "exec_block")
    assert block.name == "EXEC-CICS-BLOCK@5"
    assert block.meta["dialect"] == "CICS"
    assert block.meta["operation"] == "LINK"
    operation = next(entity for entity in result.entities if entity.type == "exec_operation")
    assert operation.name == "LINK"
    resources = [entity for entity in result.entities if entity.type == "exec_resource"]
    assert {(entity.name, entity.meta["resource_kind"]) for entity in resources} == {
        ("PAYMENT", "PROGRAM"),
        ("CUSTOMER", "FILE"),
    }
    edges = [edge for edge in result.edges if edge.src_name == block.qualified_name]
    assert [(edge.type, edge.dst_name, edge.resolution) for edge in edges] == [
        ("EXECUTES", "LINK", "resolved"),
        ("USES", "PAYMENT", "resolved"),
        ("USES", "CUSTOMER", "resolved"),
        ("CALL", "PAYMENT", "resolved"),
    ]
    call = next(edge for edge in edges if edge.type == "CALL")
    assert call.scope is None
    assert call.meta["invocation_kind"] == "cics_link"


def test_ims_and_unknown_exec_dialects_remain_visible_and_dynamic_operands_do_not_resolve():
    result = parse_program(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. IMSDEMO.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           EXEC DL/I\n"
        "               GU PCB(PCB-ORDER) SEGMENT('ORDER')\n"
        "           END-EXEC.\n"
        "           EXEC FOO\n"
        "               INVOKE QUEUE(WS-QUEUE)\n"
        "           END-EXEC.\n",
        "IMSDEMO.CBL",
    )

    blocks = [entity for entity in result.entities if entity.type == "exec_block"]
    assert [(entity.meta["dialect"], entity.meta["operation"]) for entity in blocks] == [
        ("DLI", "GU"),
        ("FOO", "INVOKE"),
    ]
    dynamic = next(edge for edge in result.edges if edge.dst_name == "WS-QUEUE")
    assert dynamic.type == "USES"
    assert dynamic.resolution == "dynamic"
    resource = next(entity for entity in result.entities if entity.name == "WS-QUEUE")
    assert resource.meta["dynamic"] is True


def test_cics_dynamic_program_and_explicit_web_resources_stay_visible_without_guessing():
    result = parse_program(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. CICSWEB.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           EXEC CICS\n"
        "               XCTL PROGRAM(WS-NEXT-PGM) URIMAP('ORDERS')\n"
        "               WEBSERVICE('ORDER-SVC') CHANNEL('REQUEST')\n"
        "           END-EXEC.\n",
        "CICSWEB.CBL",
    )

    resources = [entity for entity in result.entities if entity.type == "exec_resource"]
    assert {(entity.name, entity.meta["resource_kind"]) for entity in resources} == {
        ("WS-NEXT-PGM", "PROGRAM"),
        ("ORDERS", "URIMAP"),
        ("ORDER-SVC", "WEBSERVICE"),
        ("REQUEST", "CHANNEL"),
    }
    call = next(edge for edge in result.edges if edge.type == "CALL")
    assert (call.dst_name, call.resolution, call.meta["invocation_kind"]) == (
        "WS-NEXT-PGM",
        "dynamic",
        "cics_xctl",
    )


def test_cics_read_classifies_into_and_resp_as_written_data():
    result = parse_program(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. CICSREAD.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-RECORD PIC X(20).\n"
        "       01 WS-STATUS PIC S9(8) COMP.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           EXEC CICS READ FILE('CUSTOMER')\n"
        "               INTO(WS-RECORD) RESP(WS-STATUS)\n"
        "           END-EXEC.\n",
        "CICSREAD.CBL",
    )

    accesses = [edge for edge in result.edges if edge.type in {"READS", "WRITES"}]
    assert {(edge.type, edge.dst_name, edge.meta.get("parameter")) for edge in accesses} == {
        ("WRITES", "WS-RECORD", "INTO"),
        ("WRITES", "WS-STATUS", "RESP"),
    }
    assert all(edge.meta["dialect"] == "CICS" for edge in accesses)
    assert all(edge.meta["operation"] == "READ" for edge in accesses)
    by_qname = {entity.qualified_name: entity for entity in result.entities}
    by_name = {}
    for entity in result.entities:
        by_name.setdefault(entity.name.upper(), []).append(entity)
    assert {
        edge.dst_name: resolve_local_target(edge, by_qname, by_name).type for edge in accesses
    } == {"WS-RECORD": "data_item", "WS-STATUS": "data_item"}


def test_ims_isrt_classifies_from_buffer_as_read_data():
    result = parse_program(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. IMSISRT.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-ORDER PIC X(20).\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           EXEC DLI ISRT PCB(PCB-ORDER) SEGMENT('ORDER')\n"
        "               FROM(WS-ORDER)\n"
        "           END-EXEC.\n",
        "IMSISRT.CBL",
    )

    access = next(edge for edge in result.edges if edge.type == "READS")
    assert access.dst_name == "WS-ORDER"
    assert access.meta["dialect"] == "DLI"
    assert access.meta["operation"] == "ISRT"
    assert access.meta["parameter"] == "FROM"
    by_qname = {entity.qualified_name: entity for entity in result.entities}
    by_name = {}
    for entity in result.entities:
        by_name.setdefault(entity.name.upper(), []).append(entity)
    target = resolve_local_target(access, by_qname, by_name)
    assert target is not None and target.type == "data_item" and target.name == "WS-ORDER"


CONTROL_FLOW_PROGRAM = (
    "       IDENTIFICATION DIVISION.\n"
    "       PROGRAM-ID. SIGNON.\n"
    "       DATA DIVISION.\n"
    "       WORKING-STORAGE SECTION.\n"
    "       01 WS-ADMIN PIC X.\n"
    "       01 WS-USER PIC X(8).\n"
    "       PROCEDURE DIVISION.\n"
    "       LOGIN-PARA.\n"
    "           IF WS-ADMIN = 'Y'\n"
    "               MOVE 'A' TO WS-USER\n"
    "               EXEC CICS XCTL\n"
    "                   PROGRAM('COADM01C')\n"
    "               END-EXEC\n"
    "           ELSE\n"
    "               EXEC CICS XCTL\n"
    "                   PROGRAM('COMEN01C')\n"
    "               END-EXEC\n"
    "           END-IF.\n"
    "           EXEC CICS RETURN\n"
    "           END-EXEC.\n"
)


def _block_edges():
    result = parse_program(CONTROL_FLOW_PROGRAM, "SIGNON.CBL")
    return result, {
        edge.dst_name: edge for edge in result.edges if edge.type == "CONTAINS"
    }


def test_a_paragraph_contains_its_exec_blocks_under_their_condition():
    _, edges = _block_edges()

    admin = edges["EXEC-CICS-BLOCK@11"]
    assert admin.src_name == "LOGIN-PARA"
    assert admin.meta["target_qualified_name"] == "SIGNON.EXEC-CICS-BLOCK@11"
    assert admin.meta["control_path"] == [
        {"type": "IF", "branch": "THEN", "condition": "WS-ADMIN = 'Y'"}
    ]
    assert edges["EXEC-CICS-BLOCK@15"].meta["control_path"] == [
        {"type": "IF", "branch": "ELSE", "condition": "WS-ADMIN = 'Y'"}
    ]
    # Der Punkt hat die Bedingung beendet.
    assert "control_path" not in edges["EXEC-CICS-BLOCK@19"].meta


def test_data_access_knows_its_condition_but_the_condition_itself_stands_before_it():
    result, _ = _block_edges()
    edges = {
        (edge.type, edge.dst_name): edge
        for edge in result.edges
        if edge.dst_name in {"WS-ADMIN", "WS-USER"} and edge.type in {"READS", "WRITES"}
    }

    assert edges[("WRITES", "WS-USER")].meta["control_path"] == [
        {"type": "IF", "branch": "THEN", "condition": "WS-ADMIN = 'Y'"}
    ]
    assert "control_path" not in edges[("READS", "WS-ADMIN")].meta


def test_exec_block_names_its_resources_for_the_process_view():
    result, _ = _block_edges()
    block = next(e for e in result.entities if e.name == "EXEC-CICS-BLOCK@11")
    assert block.meta["resources"] == ["COADM01C"]


def test_a_condition_ends_before_the_exec_block_that_follows_it():
    result = parse_program(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. SIGNON.\n"
        "       PROCEDURE DIVISION.\n"
        "       LOGIN-PARA.\n"
        "           IF WS-ADMIN\n"
        "               EXEC CICS RETURN\n"
        "               END-EXEC\n"
        "           END-IF.\n",
        "SIGNON.CBL",
    )
    edge = next(item for item in result.edges if item.type == "CONTAINS")
    assert edge.meta["control_path"][0]["condition"] == "WS-ADMIN"

