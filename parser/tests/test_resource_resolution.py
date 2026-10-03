"""O-250: actual parser output joined across languages with explicit uncertainty."""
from types import SimpleNamespace as Row

from core.resource_resolution import resolve_resource_edges
from java.parse import parse_java_file
from markup.jsp_html import parse_jsp_or_html
from shell.parse import parse_shell_file
from xslt.parse import parse_xslt_file


def rows(results):
    entities, edges = [], []
    for result in results:
        local = {}
        for entity in result.entities:
            row = Row(id=len(entities) + 1, file_path=result.path, variant_key="default",
                      type=entity.type, qualified_name=entity.qualified_name, meta_json=entity.meta)
            entities.append(row)
            local[entity.qualified_name] = row.id
        for edge in result.edges:
            edges.append(Row(type=edge.type, src_entity_id=local[edge.src_name],
                             dst_entity_id=None, variant_key="default", resolution=edge.resolution,
                             src_start_line=edge.src_start_line, meta_json=edge.meta))
    return entities, edges


def test_shell_java_xslt_and_jsp_html_links_retain_source_and_status():
    results = [
        parse_shell_file('java demo.Main\n', 'run.sh'),
        parse_java_file('package demo; class Main { public static void main(String[] args) {\nMain.class.getResource("/report.xsl");\nMain.class.getResource(path);\nMain.class.getResource("/view.jsp");\n}}', 'app/src/main/java/demo/Main.java'),
        parse_xslt_file('<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0"/>', 'app/src/main/resources/report.xsl'),
        parse_jsp_or_html('<a href="result.html">result</a>', 'app/src/main/resources/view.jsp'),
        parse_jsp_or_html('<html/>', 'app/src/main/resources/result.html'),
    ]
    entities, edges = rows(results)
    resolve_resource_edges(entities, edges)
    start = next(e for e in edges if e.type == 'STARTS_JAVA')
    resource = next(e for e in edges if e.type == 'USES_RESOURCE' and e.resolution == 'resolved')
    assert start.resolution == 'resolved'
    assert start.dst_entity_id == resource.src_entity_id
    jsp = next(e for e in entities if e.type == 'jsp_page')
    assert any(e.type == 'USES_RESOURCE' and e.dst_entity_id == jsp.id for e in edges)
    assert resource.meta_json['evidence']['source']['start_line'] == 2
    assert resource.src_start_line == 2
    assert resource.meta_json['source_file_path'] == 'app/src/main/java/demo/Main.java'
    assert next(e for e in edges if e.type == 'LINKS_TO').resolution == 'resolved'
    assert next(e for e in edges if e.type == 'USES_RESOURCE' and e.resolution == 'dynamic').dst_entity_id is None
    target = next(e for e in entities if e.id == resource.dst_entity_id)
    duplicate = Row(**{**vars(target), 'id': 999})
    resolve_resource_edges(entities + [duplicate], edges)
    assert resource.resolution == 'unresolved'
    assert resource.meta_json['resolution_reason'] == 'ambiguous_resource_target'
    resolve_resource_edges([e for e in entities if e.id != target.id], edges)
    assert resource.dst_entity_id is None
    assert resource.meta_json['resolution_reason'] == 'resource_target_not_found'


def test_classpath_resources_do_not_cross_modules_or_invent_method_semantics():
    java = parse_java_file('package demo; class Main { void run() {\nMain.class.getResource("/report.xsl");\nother.getResource("/report.xsl");\n}}', 'app/src/main/java/demo/Main.java')
    stylesheet = parse_xslt_file('<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0"/>', 'other/src/main/resources/report.xsl')
    entities, edges = rows([java, stylesheet])
    resolve_resource_edges(entities, edges)
    resources = [e for e in edges if e.type == 'USES_RESOURCE']
    assert len(resources) == 1
    assert resources[0].resolution == 'unresolved'


WICKET_PAGE = '''package demo;
import org.apache.wicket.markup.html.WebPage;
import org.apache.wicket.model.ResourceModel;
import org.springframework.beans.factory.annotation.Value;
public class Page extends WebPage {
    @Value("${db.url:jdbc:h2:mem}")
    private String url;
    void build() {
        add(new Label("title", new ResourceModel("page.title", "Title")));
        add(new Label("other", new ResourceModel(dynamicKey)));
        String text = getString("page.hint");
        String json = node.getString("page.hint");
    }
}
'''


def _property_rows(extra_bundles=()):
    from resources.properties import parse_properties_file
    bundles = [parse_properties_file("page.title=Hello\npage.hint=Hint\n", "app/src/main/resources/demo/Page.properties"),
               parse_properties_file("db.url=jdbc:h2\n", "app/src/main/resources/application.properties"), *extra_bundles]
    return bundles


def test_java_references_to_property_keys_resolve_to_the_property_entity():
    page = parse_java_file(WICKET_PAGE, "app/src/main/java/demo/Page.java")
    keys = [(e.meta["property_key"], e.meta["key_source"], e.meta["certainty"])
            for e in page.edges if e.type == "REFERENCES_PROPERTY_KEY"]
    assert keys == [
        ("db.url", "spring_value", "certain"),
        ("page.title", "wicket_resource_model", "certain"),
        ("page.hint", "wicket_get_string", "probable"),
    ]  # dynamicKey und node.getString(...) liefern keine Kante

    entities, edges = rows([page, *_property_rows()])
    resolve_resource_edges(entities, edges)
    by_key = {e.meta_json["property_key"]: e for e in edges if e.type == "REFERENCES_PROPERTY_KEY"}
    assert {k: e.resolution for k, e in by_key.items()} == {
        "db.url": "resolved", "page.title": "resolved", "page.hint": "resolved",
    }
    target = next(e for e in entities if e.id == by_key["page.title"].dst_entity_id)
    assert target.type == "property" and target.qualified_name.endswith("Page.properties::page.title")
    assert by_key["page.title"].meta_json["resolution_scope"] == "module"


def test_property_key_with_two_bundles_in_the_module_is_ambiguous_and_missing_key_is_reported():
    from resources.properties import parse_properties_file
    twin = parse_properties_file("page.title=Other\n", "app/src/main/resources/ui/Other.properties")
    page = parse_java_file(WICKET_PAGE, "app/src/main/java/demo/Page.java")
    far = parse_properties_file("page.title=Far\n", "app/src/main/resources/ui/Far.properties")
    entities, edges = rows([page, twin, far, *_property_rows()[1:]])
    resolve_resource_edges(entities, edges)
    by_key = {e.meta_json["property_key"]: e for e in edges if e.type == "REFERENCES_PROPERTY_KEY"}
    assert by_key["page.title"].resolution == "unresolved"
    assert by_key["page.title"].meta_json["resolution_reason"] == "ambiguous_property_key"
    assert by_key["page.title"].dst_entity_id is None

    entities, edges = rows([page])
    resolve_resource_edges(entities, edges)
    assert {e.meta_json["resolution_reason"] for e in edges if e.type == "REFERENCES_PROPERTY_KEY"} == {"property_key_not_found"}


def test_component_bundle_next_to_the_wicket_class_wins_over_other_module_bundles():
    from resources.properties import parse_properties_file
    own = parse_properties_file("page.title=Own\n", "app/src/main/resources/demo/Page.properties")
    other = parse_properties_file("page.title=Other\n", "app/src/main/resources/demo/Other.properties")
    page = parse_java_file(WICKET_PAGE, "app/src/main/java/demo/Page.java")
    entities, edges = rows([page, own, other])
    resolve_resource_edges(entities, edges)
    edge = next(e for e in edges if e.type == "REFERENCES_PROPERTY_KEY" and e.meta_json["property_key"] == "page.title")
    assert edge.resolution == "resolved" and edge.meta_json["resolution_scope"] == "component_bundle"
    assert next(e for e in entities if e.id == edge.dst_entity_id).file_path.endswith("demo/Page.properties")
