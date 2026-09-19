from core import registry
from shell.parse import parse_shell_file


SCRIPT = '''#!/usr/bin/env bash
run() { java -cp build/classes com.example.Main; }
source "lib/common.sh"
. "scripts with spaces/helper.sh"
xsltproc styles/report.xsl input.xml
./deploy.sh \\
  --quiet
cat <<'EOF'
source ignored.sh
EOF
java "$MAIN_CLASS"
'''


def test_shell_parser_extracts_functions_literal_includes_and_tools_without_execution() -> None:
    result = parse_shell_file(SCRIPT, "bin/run.sh")

    assert result.entities[0].type == "shell_script"
    assert next(entity for entity in result.entities if entity.type == "shell_function").name == "run"
    edges = {(edge.type, edge.dst_name): edge for edge in result.edges}
    assert edges[("SOURCES", "bin/lib/common.sh")].resolution == "unresolved"
    assert edges[("SOURCES", "bin/scripts with spaces/helper.sh")].resolution == "unresolved"
    assert edges[("TRANSFORMS_WITH", "bin/styles/report.xsl")].meta["target_entity_type"] == "xslt_stylesheet"
    assert edges[("EXECUTES_SCRIPT", "bin/deploy.sh")].src_start_line == 6
    assert edges[("STARTS_JAVA", "com.example.Main")].resolution == "unresolved"
    assert next(edge for edge in result.edges if edge.type == "STARTS_JAVA" and edge.dst_name == "$MAIN_CLASS").resolution == "dynamic"
    assert all("ignored.sh" not in edge.dst_name for edge in result.edges)


def test_shell_registry_supports_extensionless_shebang_files() -> None:
    assert registry.STRUCTURE_PARSERS["shell"].root_entity_types == ("shell_script",)


def test_shell_parser_disambiguates_redefined_functions_for_persistence() -> None:
    result = parse_shell_file("run() { echo old; }\nrun() { echo new; }\n", "bin/run.sh")

    functions = [entity for entity in result.entities if entity.type == "shell_function"]
    assert [entity.qualified_name for entity in functions] == [
        "bin/run.sh::function:run",
        "bin/run.sh::function:run#2",
    ]
