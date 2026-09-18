from __future__ import annotations

from maven.parse import parse_maven_pom


POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>org.example</groupId>
  <artifactId>billing-parent</artifactId>
  <version>1.2.3</version>
  <packaging>pom</packaging>
  <properties>
    <maven.compiler.source>8</maven.compiler.source>
  </properties>
  <modules>
    <module>billing-core</module>
  </modules>
  <dependencies>
    <dependency>
      <groupId>org.example</groupId>
      <artifactId>shared-model</artifactId>
      <version>${project.version}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.11.0</version>
      </plugin>
    </plugins>
  </build>
</project>
"""


def test_maven_parser_extracts_project_modules_dependencies_and_plugins() -> None:
    result = parse_maven_pom(POM, "billing/pom.xml")

    assert result.diagnostics == []
    assert result.chunks[0].meta["language"] == "maven"
    assert result.entities[0].type == "maven_project"
    assert result.entities[0].meta["group_id"] == "org.example"
    assert result.entities[0].meta["packaging"] == "pom"

    by_type = {entity.type: entity for entity in result.entities if entity.type != "maven_project"}
    assert by_type["maven_module"].meta["module_path"] == "billing-core"
    assert by_type["maven_dependency"].meta["scope"] == "test"
    assert by_type["maven_plugin"].name == "org.apache.maven.plugins:maven-compiler-plugin"
    assert {edge.type for edge in result.edges} == {
        "CONTAINS_MODULE",
        "DEPENDS_ON",
        "USES_PLUGIN",
    }


def test_maven_parser_keeps_invalid_xml_as_partial_source() -> None:
    result = parse_maven_pom("<project>", "broken/pom.xml")

    assert result.entities == []
    assert result.chunks
    assert result.diagnostics[0].code == "MAVEN_POM_XML_ERROR"
