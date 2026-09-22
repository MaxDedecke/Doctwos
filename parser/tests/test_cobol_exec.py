from cobol.parse import parse_program


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
    ]


def test_ims_and_unknown_exec_dialects_remain_visible_and_dynamic_operands_do_not_resolve():
    result = parse_program(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. IMSDEMO.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           EXEC DLI\n"
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
