"""O-250 acceptance: one source-backed flow across all new languages."""

from types import SimpleNamespace as Row

from core.resource_resolution import resolve_resource_edges
from java.parse import parse_java_file
from markup.jsp_html import parse_jsp_or_html
from markup.parse import parse_xml_document
from shell.parse import parse_shell_file
from xslt.parse import parse_xslt_file


def _persisted_rows(results):
    entities, edges = [], []
    for result in results:
        local = {}
        for entity in result.entities:
            row = Row(
                id=len(entities) + 1,
                file_path=result.path,
                variant_key="default",
                type=entity.type,
                qualified_name=entity.qualified_name,
                meta_json=entity.meta,
            )
            entities.append(row)
            local[entity.qualified_name] = row.id
        for edge in result.edges:
            edges.append(
                Row(
                    type=edge.type,
                    src_entity_id=local[edge.src_name],
                    dst_entity_id=None,
                    dst_name=edge.dst_name,
                    variant_key="default",
                    resolution=edge.resolution,
                    src_start_line=edge.src_start_line,
                    src_end_line=edge.src_end_line,
                    meta_json=edge.meta,
                )
            )
    return entities, edges


def test_o250_connects_shell_java_xslt_xml_and_jsp_with_evidence():
    results = [
        parse_shell_file(
            "#!/bin/sh\njava -cp app.jar app.Main\n",
            "run.sh",
        ),
        parse_java_file(
            """package app;
public class Main {
  public static void main(String[] args) {
    Main.class.getResource("/templates/report.xsl");
    Main.class.getResource("/views/result.jsp");
    Main.class.getResource(path);
  }
}
""",
            "app/src/main/java/app/Main.java",
        ),
        parse_xslt_file(
            """<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
  <xsl:template match="/">
    <xsl:value-of select="document('input.xml')/root/value"/>
  </xsl:template>
</xsl:stylesheet>
""",
            "app/src/main/resources/templates/report.xsl",
        ),
        parse_xml_document(
            "<root><value>ok</value></root>\n",
            "app/src/main/resources/templates/input.xml",
        ),
        parse_jsp_or_html(
            '<jsp:include page="fragment.jsp" />\n',
            "app/src/main/resources/views/result.jsp",
        ),
        parse_jsp_or_html(
            "<p>fragment</p>\n",
            "app/src/main/resources/views/fragment.jsp",
        ),
    ]
    entities, edges = _persisted_rows(results)

    resolve_resource_edges(entities, edges)

    by_path = {entity.file_path: entity for entity in entities if entity.meta_json.get("is_file_root")}
    by_id = {entity.id: entity for entity in entities}
    main = next(
        entity
        for entity in entities
        if entity.file_path == "app/src/main/java/app/Main.java"
        and entity.type == "method"
        and "#main(" in entity.qualified_name
    )
    assert main.id == next(edge.dst_entity_id for edge in edges if edge.type == "STARTS_JAVA")
    assert any(
        edge.type == "USES_RESOURCE"
        and edge.resolution == "resolved"
        and by_path["app/src/main/resources/templates/report.xsl"].id == edge.dst_entity_id
        for edge in edges
    )
    assert any(
        edge.type == "READS_XML"
        and edge.resolution == "resolved"
        and by_path["app/src/main/resources/templates/input.xml"].id == edge.dst_entity_id
        for edge in edges
    )
    assert any(
        edge.type == "INCLUDES"
        and edge.resolution == "resolved"
        and by_path["app/src/main/resources/views/fragment.jsp"].id == edge.dst_entity_id
        for edge in edges
    )

    resource_edges = [
        edge
        for edge in edges
        if edge.type in {"STARTS_JAVA", "USES_RESOURCE", "READS_XML", "INCLUDES"}
    ]
    assert all(edge.meta_json["relationship_kind"] == "resource" for edge in resource_edges)
    assert all(
        edge.meta_json["evidence"]["source"]["file_path"]
        == by_id[edge.src_entity_id].file_path
        for edge in resource_edges
    )

    dynamic = next(
        edge
        for edge in edges
        if edge.type == "USES_RESOURCE" and edge.resolution == "dynamic"
    )
    assert dynamic.dst_entity_id is None
    assert dynamic.meta_json["resolution_reason"] == "dynamic_resource_expression"
