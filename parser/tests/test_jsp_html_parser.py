from core import registry
from core import config
from markup.jsp_html import parse_jsp_or_html


JSP = '''<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<%@ include file="/WEB-INF/jspf/nav.jspf" %>
<jsp:include page="footer.jsp" />
<a href="help.html">Help</a><img src="/images/logo.svg">
<form action="/orders/save" method="post"><input value="${order.id}"></form>
<% request.setAttribute("x", 1); %>'''


def test_jsp_parser_preserves_mixed_content_and_static_edges() -> None:
    result = parse_jsp_or_html(JSP, "web/views/order.jsp")

    assert result.entities[0].type == "jsp_page"
    assert {entity.type for entity in result.entities} >= {"jsp_taglib", "jsp_el_expression", "jsp_scriptlet", "html_form"}
    includes = [edge for edge in result.edges if edge.type == "INCLUDES"]
    assert {edge.meta["target_file_path"] for edge in includes} == {"WEB-INF/jspf/nav.jspf", "web/views/footer.jsp"}
    edges = {edge.type: edge for edge in result.edges}
    assert edges["SUBMITS_TO"].resolution == "dynamic"
    assert edges["SUBMITS_TO"].meta["http_method"] == "post"
    assert edges["LINKS_TO"].meta["target_file_path"] == "web/views/help.html"


def test_html_parser_keeps_external_and_template_urls_dynamic() -> None:
    result = parse_jsp_or_html('<a href="https://example.test/x">x</a><img src="${asset}">', "web/a.html")

    assert {edge.resolution for edge in result.edges} == {"dynamic"}
    assert registry.STRUCTURE_PARSERS["jsp"].root_entity_types == ("jsp_page",)
    assert registry.STRUCTURE_PARSERS["html"].root_entity_types == ("html_document",)


def test_html_parser_splits_large_markup_into_embedding_sized_chunks() -> None:
    lines = [f"<p id=\"part-{index}\">{'x' * 300}</p>" for index in range(5)]
    result = parse_jsp_or_html("\n".join(lines), "web/large.html")

    assert len(result.chunks) > 1
    assert all(len(chunk.content) <= config.CHUNK_SIZE for chunk in result.chunks)
    assert result.chunks[0].start_line == 1
    assert result.chunks[-1].end_line == len(lines)
    assert all(chunk.meta == {"language": "html", "symbol_type": "source"} for chunk in result.chunks)
