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


def test_object_creation_and_field_access_stand_under_their_condition():
    result = parse_java_file(
        """class Flow {
      int count; Object last;
      void use(boolean ok) {
        if (ok && count > 0) {
          last = new Object();
          throw new IllegalStateException();
        }
        count = 1;
      }
    }""",
        "Flow.java",
    )
    guard = [{"type": "IF", "branch": "THEN", "condition": "ok && count > 0"}]
    created = {edge.dst_name: edge for edge in result.edges if edge.type == "INSTANTIATES"}
    assert created["Object"].meta["control_path"] == guard
    assert created["IllegalStateException"].meta["control_path"] == guard

    writes = {
        edge.dst_name.rsplit(".", 1)[-1]: edge
        for edge in result.edges
        if edge.type == "WRITES" and edge.src_start_line in {5, 8}
    }
    assert writes["last"].meta["control_path"] == guard
    # Die Bedingung selbst wird vor der Verzweigung gelesen.
    read = next(edge for edge in result.edges if edge.type == "READS" and "count" in edge.dst_name)
    assert "control_path" not in read.meta or read.meta["control_path"] != guard
    assert "control_path" not in writes["count"].meta


def test_arguments_come_before_the_call_that_uses_them():
    result = parse_java_file(
        """class Flow {
      void use() {
        store(load(), new Item(name()));
      }
    }""",
        "Flow.java",
    )
    order = [edge.dst_name for edge in result.edges if edge.type in {"CALLS", "INSTANTIATES"}]
    assert order == ["load", "name", "Item", "store"]

