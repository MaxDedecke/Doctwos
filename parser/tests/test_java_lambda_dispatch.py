from java.parse import parse_java_file
from java.lambda_dispatch import derive_lambda_dispatch


def test_local_lambda_dispatch_connects_the_callsite_to_its_body_once():
    result = parse_java_file(
        """interface Task{void run();}
class C{void work(){} void use(boolean ok){Task task=()->work(); if(ok)task.run();}}""",
        "C.java",
    )
    assert not result.diagnostics
    dispatch = [edge for edge in result.edges if edge.type == "DISPATCHES_TO"]
    assert len(dispatch) == 1
    assert "@lambda:" in dispatch[0].meta["target_qualified_name"]
    assert dispatch[0].meta["control_path"] == [{"type": "IF", "branch": "THEN", "condition": "ok"}]
    assert any(
        edge.type == "CALLS" and edge.meta.get("target_qualified_name") == "Task#run()"
        for edge in result.edges
    )
    assert list(derive_lambda_dispatch([result])) == []


def test_reassignment_and_incomplete_flow_do_not_claim_initializer_dispatch():
    for body in [
        "task=()->work();task.run();",
        "\n".join(f"int n{i}={i};" for i in range(90)) + "task.run();",
    ]:
        result = parse_java_file(
            "interface Task{void run();} class C{void work(){} void use(){Task task=()->work();"
            + body
            + "}}",
            "C.java",
        )
        assert not any(edge.type == "DISPATCHES_TO" for edge in result.edges)


def test_data_flow_limit_reports_omitted_statements_without_losing_the_prefix():
    result = parse_java_file(
        "class C{void use(){int n=0;\n" + "\n".join(f"n={i};" for i in range(1, 91)) + "}}",
        "C.java",
    )
    method = next(entity for entity in result.entities if entity.type == "method")
    assert len(method.meta["data_flow"]) == 80
    assert method.meta["data_flow_truncated"] is True
    assert method.meta["data_flow_omitted"] == 11
    assert any(
        item.code == "JAVA_DATA_FLOW_TRUNCATED" and item.severity == "warning"
        for item in result.diagnostics
    )


def test_exact_data_flow_limit_does_not_report_a_truncation():
    result = parse_java_file(
        "class C{void use(){int n=0;" + "".join(f"n={i};" for i in range(1, 80)) + "}}", "C.java"
    )
    method = next(entity for entity in result.entities if entity.type == "method")
    assert len(method.meta["data_flow"]) == 80
    assert not method.meta.get("data_flow_truncated")
    assert not result.diagnostics
