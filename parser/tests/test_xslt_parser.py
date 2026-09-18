from __future__ import annotations

from markup.parse import parse_xml_document
from xslt.parse import parse_xslt_file


STYLESHEET = """<?xml version="1.0"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
  <xsl:import href="base.xsl"/>
  <xsl:include href="parts/common.xsl"/>
  <xsl:template name="main">
    <xsl:param name="kind" select="'book'"/>
    <xsl:apply-templates select="book"/>
    <xsl:call-template name="footer"/>
    <xsl:value-of select="document('input.xml')/root/title"/>
  </xsl:template>
  <xsl:template name="footer" match="footer"/>
</xsl:stylesheet>
"""


def test_xslt_parser_extracts_templates_parameters_chunks_and_relationships() -> None:
    result = parse_xslt_file(STYLESHEET, "web/main.xsl")

    assert result.diagnostics == []
    assert result.entities[0].type == "xslt_stylesheet"
    assert result.entities[0].meta["namespaces"]["xsl"] == (
        "http://www.w3.org/1999/XSL/Transform"
    )
    assert {entity.type for entity in result.entities} >= {
        "xslt_stylesheet",
        "xslt_template",
        "xslt_parameter",
    }
    template = next(entity for entity in result.entities if entity.name == "main")
    assert template.start_line == 5
    assert template.meta["template_name"] == "main"
    assert any(
        chunk.meta.get("symbol_qualified_name") == template.qualified_name
        for chunk in result.chunks
    )

    edge_types = {edge.type for edge in result.edges}
    assert {"IMPORTS", "INCLUDES", "CALLS_TEMPLATE", "APPLIES_TEMPLATES", "READS_XML"} <= edge_types
    call = next(edge for edge in result.edges if edge.type == "CALLS_TEMPLATE")
    assert call.resolution == "resolved"
    assert call.meta["target_qualified_name"].endswith("::template:footer")
    assert next(edge for edge in result.edges if edge.type == "READS_XML").dst_name == "web/input.xml"


def test_xslt_parser_keeps_ambiguous_apply_templates_unresolved() -> None:
    source = """<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
      <xsl:template match="item" mode="m"/>
      <xsl:template match="item" mode="m"/>
      <xsl:template name="run"><xsl:apply-templates select="item" mode="m"/></xsl:template>
    </xsl:stylesheet>"""

    result = parse_xslt_file(source, "run.xsl")
    edge = next(edge for edge in result.edges if edge.type == "APPLIES_TEMPLATES")
    assert edge.resolution == "unresolved"
    assert edge.meta["resolution_reason"] == "ambiguous_match"
    assert len(edge.meta["candidate_qualified_names"]) == 2


def test_xslt_parser_marks_dynamic_template_and_document_selection_dynamic() -> None:
    source = """<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
      <xsl:template name="run">
        <xsl:call-template name="{$name}"/>
        <xsl:value-of select="document($uri)/root"/>
      </xsl:template>
    </xsl:stylesheet>"""

    result = parse_xslt_file(source, "run.xsl")
    assert next(edge for edge in result.edges if edge.type == "CALLS_TEMPLATE").resolution == "dynamic"
    document_edge = next(edge for edge in result.edges if edge.type == "READS_XML")
    assert document_edge.resolution == "dynamic"
    assert document_edge.meta["document_expression"] == "$uri"


def test_xslt_parser_blocks_doctype_without_fetching_external_resources() -> None:
    result = parse_xslt_file(
        '<!DOCTYPE xsl:stylesheet SYSTEM "https://example.invalid/style.dtd">\n'
        '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"/>',
        "unsafe.xsl",
    )

    assert result.entities == []
    assert result.diagnostics[0].code == "XSLT_EXTERNAL_DECLARATION_BLOCKED"
    assert result.chunks[0].meta["fallback"] is True


def test_xml_root_parser_provides_a_target_for_xslt_resource_edges() -> None:
    result = parse_xml_document("<?xml version=\"1.0\"?>\n<root/>", "web/input.xml")

    assert result.diagnostics == []
    assert result.entities[0].type == "xml_document"
    assert result.entities[0].qualified_name == "web/input.xml"
    assert result.entities[0].start_line == 2
