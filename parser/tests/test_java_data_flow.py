"""Datenfluss-Tabelle der Java-Routinen (`meta["data_flow"]`) und `argument_refs` (E-15, MCP-Ziel O(1))."""

from __future__ import annotations

from java.parse import parse_java_file

SOURCE = """package demo;

import java.util.List;

public class Account {
    private String owner;
    private long balance = 100L;
    private final List<String> log = new java.util.ArrayList<>();

    public Account(String owner, long start) {
        this.owner = owner;
        this.balance = start + 1;
    }

    public long deposit(long amount, Fee fee) {
        long net = amount - fee.rate();
        long checked = validate(net);
        balance += checked;
        String note = owner + ":" + checked;
        log.add(note);
        balance++;
        return balance;
    }

    private long validate(long value) {
        if (value < 0) { value = 0; }
        return value;
    }

    long shadow(long balance) {
        long local = balance;
        Runnable task = () -> { long inner = local; };
        return local;
    }
}
"""


def _flows():
    result = parse_java_file(SOURCE, "src/main/java/demo/Account.java")
    return result, {entity.qualified_name: entity.meta.get("data_flow", []) for entity in result.entities}


def _row(flow, line, operation):
    return next(item for item in flow if item["line"] == line and item["operation"] == operation)


def _sources(row):
    return [(item["kind"], item["name"], item.get("via")) for item in row["sources"]]


def test_assignments_and_initializers_name_target_and_sources_by_kind():
    _result, flows = _flows()
    constructor = flows["demo.Account#<init>(String,long)"]
    assert _row(constructor, 11, "assign")["target"]["kind"] == "field"
    assert _sources(_row(constructor, 11, "assign")) == [("parameter", "owner", None)]
    assert _sources(_row(constructor, 12, "assign")) == [("parameter", "start", None)]

    deposit = flows["demo.Account#deposit(long,Fee)"]
    net = _row(deposit, 16, "init")
    assert (net["target"]["kind"], net["target"]["name"]) == ("local_variable", "net")
    assert net["target"]["qualified_name"].endswith("@local:net:16:13")
    assert ("parameter", "amount", None) in _sources(net) and ("call", "fee.rate", None) in _sources(net)
    checked = _row(deposit, 17, "init")
    assert _sources(checked) == [("call", "validate", None), ("local_variable", "net", "call:validate")]
    assert _row(deposit, 18, "compound_assign")["target"] == {
        "kind": "field", "name": "balance", "qualified_name": "demo.Account#balance"}
    assert ("field", "owner", None) in _sources(_row(deposit, 19, "init"))
    assert _row(deposit, 21, "increment")["target"]["name"] == "balance"
    assert _sources(_row(deposit, 22, "return")) == [("field", "balance", None)]


def test_field_initializers_belong_to_the_class_and_literals_are_kept_only_alone():
    _result, flows = _flows()
    klass = flows["demo.Account"]
    assert _sources(_row(klass, 7, "init")) == [("literal", "100L", None)]
    assert _sources(_row(klass, 8, "init")) == [("new", "java.util.ArrayList<>", None)]


def test_parameters_can_be_written_and_names_resolve_by_lexical_scope():
    _result, flows = _flows()
    assert _row(flows["demo.Account#validate(long)"], 26, "assign")["target"]["kind"] == "parameter"
    shadow = flows["demo.Account#shadow(long)"]
    # `balance` ist hier der Parameter und nicht das gleichnamige Feld.
    assert _sources(_row(shadow, 31, "init")) == [("parameter", "balance", None)]
    # In der Lambda-Routine ist `local` die lokale Variable der äußeren Methode.
    lambda_flow = next(flow for name, flow in flows.items() if "@lambda:" in name)
    assert _sources(lambda_flow[0]) == [("local_variable", "local", None)]


def test_calls_carry_argument_refs_to_the_exact_data_entity():
    result, _flows_ = _flows()
    calls = {edge.dst_name: edge.meta for edge in result.edges if edge.type == "CALLS"}
    validate = calls["validate"]
    assert validate["argument_expressions"] == ["net"]
    assert validate["argument_refs"][0]["kind"] == "local_variable"
    assert validate["argument_refs"][0]["qualified_name"].endswith("@local:net:16:13")
    assert calls["log.add"]["argument_refs"][0]["name"] == "note"
    assert calls["fee.rate"]["argument_refs"] == []


def test_flow_tables_are_bounded():
    body = "\n".join(f"        x = {i};" for i in range(200))
    result = parse_java_file(f"class B {{ int x; void m() {{\n{body}\n    }} }}", "B.java")
    flow = next(entity.meta["data_flow"] for entity in result.entities if entity.name == "m")
    assert len(flow) == 80
