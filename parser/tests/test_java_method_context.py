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
