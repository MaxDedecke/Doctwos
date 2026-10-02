"""Method-level evidence used by MCP answers: annotations, returns and arguments."""

from java.parse import parse_java_file

SOURCE = '''package demo;
public class UserLogic {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public Result create(final User user, final boolean flag) {
        Result r = manager.create(user, flag, null);
        afterCreate(r);
        return r;
    }

    public Result create(final User user) {
        if (user == null) {
            return null;
        }
        return create(user, true);
    }
}
'''


def _methods():
    result = parse_java_file(SOURCE, "src/UserLogic.java")
    return {e.qualified_name: e for e in result.entities if e.type == "method"}, result


def test_return_expressions_are_captured_with_lines():
    methods, _ = _methods()
    two = methods["demo.UserLogic#create(User,boolean)"].meta["return_expressions"]
    assert [(r["expression"], r["start_line"]) for r in two] == [("r", 7)]
    one = methods["demo.UserLogic#create(User)"].meta["return_expressions"]
    assert [(r["expression"], r["start_line"]) for r in one] == [("null", 12), ("create(user, true)", 14)]


def test_transaction_annotation_is_inside_the_method_range_with_values():
    methods, _ = _methods()
    method = methods["demo.UserLogic#create(User,boolean)"]
    assert method.start_line == 3  # annotation line belongs to the method's source range
    detail = method.meta["annotation_details"][0]
    assert detail["name"] == "Transactional"
    assert detail["values"] == {"propagation": "Propagation.REQUIRES_NEW"}


def test_call_arguments_are_kept_and_overloads_stay_distinct():
    methods, result = _methods()
    assert len({q for q in methods if q.startswith("demo.UserLogic#create(")}) == 2
    args = [
        e.meta["argument_expressions"] for e in result.edges
        if e.type == "CALLS" and e.meta and e.meta.get("argument_count") == 3
    ]
    assert args == [["user", "flag", "null"]]


EXC_SOURCE = '''package demo;
public class Pay {
    public void run(Path p) throws IOException {
        try (InputStream in = open(p); Reader r = wrap(in)) {
            if (bad()) {
                throw new IllegalStateException("bad");
            }
            use(r);
        } catch (IOException | RuntimeException e) {
            log(e);
            throw wrap(e);
        } finally {
            cleanup();
        }
    }
}
'''


def test_exception_flow_records_throws_catches_finally_and_resources():
    result = parse_java_file(EXC_SOURCE, "src/Pay.java")
    method = next(e for e in result.entities if e.type == "method")
    flow = method.meta["exception_flow"]
    kinds = [item["kind"] for item in flow]
    assert kinds.count("try_resource") == 2 and all(i["implicit_close"] for i in flow if i["kind"] == "try_resource")
    throws = [i for i in flow if i["kind"] == "throw"]
    assert [(t["exception_type"], t["control_context"]) for t in throws] == [
        ("IllegalStateException", "try"), (None, "catch(IOException|RuntimeException)"),
    ]
    assert throws[1]["expression"] == "wrap(e)"
    catch = next(i for i in flow if i["kind"] == "catch")
    assert catch["exception_types"] == ["IOException", "RuntimeException"]
    assert any(i["kind"] == "finally" for i in flow)
    assert method.meta["throws_types"] == ["IOException"]


VOID_SOURCE = '''package demo;
public class Filter {
    public void run(final Request req) {
        if (req == null) {
            return;
        }
        Runnable r = () -> {
            return;
        };
        switch (req.kind()) {
            case 1:
                return;
            default:
                break;
        }
        handle(req);
    }

    public int count(final Request req) {
        if (req == null) {
            return 0;
        }
        return req.size();
    }
}
'''


def test_bare_return_does_not_abort_structure_parsing():
    result = parse_java_file(VOID_SOURCE, "src/Filter.java")
    methods = {e.qualified_name: e for e in result.entities if e.type == "method"}
    assert methods["demo.Filter#run(Request)"].meta["return_expressions"] == []
    counted = methods["demo.Filter#count(Request)"].meta["return_expressions"]
    assert [(r["expression"], r["start_line"]) for r in counted] == [("0", 21), ("req.size()", 23)]
