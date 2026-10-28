from java.parse import parse_java_file


def test_modern_switch_and_ternary_branches_keep_nested_guards_and_lines():
    source = """class Flow {
  int a(){return 1;} int b(){return 2;} int selector(){return 1;}
  int use(boolean ok) {
    return switch(selector()) {
      case 1, 2 -> ok ? a() : b();
      default -> b();
    };
  }
}"""
    result = parse_java_file(source, "Flow.java")
    assert not result.diagnostics
    calls = [edge for edge in result.edges if edge.type == "CALLS"]
    selector = next(edge for edge in calls if edge.dst_name == "selector")
    assert "control_path" not in selector.meta
    a = next(edge for edge in calls if edge.dst_name == "a")
    assert a.src_start_line == 5
    assert a.meta["control_path"] == [
        {"type": "SWITCH", "branch": "CASE", "subject": "selector()", "when": "case 1, 2"},
        {"type": "IF", "branch": "THEN", "condition": "ok"},
    ]
    branches = [edge.meta["control_path"] for edge in calls if edge.dst_name == "b"]
    assert branches[0][-1] == {"type": "IF", "branch": "ELSE", "condition": "ok"}
    assert branches[1] == [
        {"type": "SWITCH", "branch": "CASE", "subject": "selector()", "when": "default"}
    ]


def test_arrow_statement_and_short_circuit_evaluation_have_guards():
    result = parse_java_file(
        """class Flow {
      boolean a(){return true;} boolean b(){return false;} void c(){}
      void use(int n, boolean flag) {
        switch(n) { case 1 -> c(); default -> {} }
        boolean x = flag && a();
        boolean y = flag || b();
      }
    }""",
        "Flow.java",
    )
    assert not result.diagnostics
    calls = {edge.dst_name: edge for edge in result.edges if edge.type == "CALLS"}
    assert calls["c"].meta["control_path"] == [
        {"type": "SWITCH", "branch": "CASE", "subject": "n", "when": "case 1"}
    ]
    assert calls["a"].meta["control_path"] == [
        {"type": "IF", "branch": "THEN", "condition": "flag"}
    ]
    assert calls["b"].meta["control_path"] == [
        {"type": "IF", "branch": "ELSE", "condition": "flag"}
    ]
