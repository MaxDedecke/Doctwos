"""O-378: schlanke Struktur für Groovy, JavaScript und SQL (nur belegte Deklarationen)."""

from core.registry import STRUCTURE_PARSERS
from resources.groovy import parse_groovy_file
from resources.javascript import parse_javascript_file
from resources.sqlscript import MAX_DML_ENTITIES, parse_sql_file

GROOVY = '''package demo.plugins
import groovy.transform.CompileStatic

// class Commented { }
@CompileStatic
class MyCommand implements Runnable {
    String note = "def fake() { not code }"
    void run() {
        if (note) {
            println "x"
        }
    }
    private static String describe(int level) throws Exception {
        return "L" + level
    }
}

def helper(a, b) {
    a + b
}
'''

JS = '''// function commented() {}
export function load(id) {
  return fetch(`/x/${id}`)
}
const render = async (rows) => {
  for (const row of rows) { draw(row) }
}
class Panel extends Base {
  constructor(el) { super(el) }
  static create() { return new Panel(document.body) }
  show() { if (this.el) { this.el.hidden = false } }
}
'''

SQL = '''-- schema
CREATE TABLE IF NOT EXISTS users (
  id BIGINT PRIMARY KEY,
  name VARCHAR(20) DEFAULT 'a;b'
);
CREATE UNIQUE INDEX idx_users_name ON users(name);
INSERT INTO users (id, name) VALUES (1, 'x');
UPDATE users SET name = 'y' WHERE id = 1;
DELETE FROM audit_log WHERE created < now();
SELECT u.id FROM users u;
'''


def _by_qname(result):
    return {e.qualified_name: e for e in result.entities}


def test_groovy_classes_and_methods_with_lines_and_without_comment_or_string_noise():
    result = parse_groovy_file(GROOVY, "plugins/MyCommand.groovy")
    entities = _by_qname(result)
    assert result.entities[0].meta["package"] == "demo.plugins"
    cls = entities["plugins/MyCommand.groovy::MyCommand"]
    assert (cls.start_line, cls.end_line) == (6, 16)
    assert "plugins/MyCommand.groovy::Commented" not in entities
    run = entities["plugins/MyCommand.groovy::MyCommand#run"]
    assert (run.start_line, run.end_line) == (8, 12) and run.parent_name == "MyCommand"
    assert "plugins/MyCommand.groovy::MyCommand#describe" in entities
    helper = entities["plugins/MyCommand.groovy#helper"]
    assert helper.parent_name == "MyCommand.groovy" and (helper.start_line, helper.end_line) == (18, 20)
    assert not [e for e in result.entities if e.name in {"if", "fake"}]


def test_javascript_functions_classes_and_methods():
    result = parse_javascript_file(JS, "ui/panel.js")
    entities = _by_qname(result)
    assert set(entities) >= {
        "ui/panel.js::load", "ui/panel.js::render", "ui/panel.js::Panel",
        "ui/panel.js::Panel#constructor", "ui/panel.js::Panel#create", "ui/panel.js::Panel#show",
    }
    assert "ui/panel.js::commented" not in entities
    assert entities["ui/panel.js::render"].start_line == 5 and entities["ui/panel.js::render"].end_line == 7
    assert entities["ui/panel.js::Panel#show"].type == "method"


def test_sql_objects_and_statements_survive_semicolons_in_strings_and_comments():
    result = parse_sql_file(SQL, "db/init.sql")
    names = {e.qualified_name: e for e in result.entities}
    table = names["db/init.sql::table:users"]
    assert (table.start_line, table.end_line) == (2, 5)
    assert names["db/init.sql::index:idx_users_name"].type == "sql_object"
    statements = [e for e in result.entities if e.type == "sql_statement"]
    assert [(e.meta["statement_type"], e.meta["table"]) for e in statements] == [
        ("insert", "users"), ("update", "users"), ("delete", "audit_log"), ("select", "users"),
    ]


def test_sql_dump_with_many_inserts_is_capped_and_says_so():
    dump = "".join(f"INSERT INTO t VALUES ({i});\n" for i in range(MAX_DML_ENTITIES + 25))
    result = parse_sql_file(dump, "dump.sql")
    assert len([e for e in result.entities if e.type == "sql_statement"]) == MAX_DML_ENTITIES
    assert result.entities[0].meta["dml_statements_not_modelled"] == 25


def test_registry_exposes_the_new_parsers():
    for language, root in (("groovy", "groovy_file"), ("javascript", "javascript_file"), ("sql", "sql_script")):
        assert STRUCTURE_PARSERS[language].root_entity_types == (root,)
