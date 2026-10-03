"""O-379: DOCTYPE mit externer ID wird gelesen (ohne DTD zu laden); interne Subsets bleiben gesperrt."""

from markup.parse import parse_xml_document

PUBLIC = (
    '<?xml version="1.0"?>\n'
    '<!DOCTYPE module PUBLIC "-//Puppy Crawl//DTD Check Configuration 1.3//EN"\n'
    '    "https://checkstyle.org/dtds/configuration_1_3.dtd">\n'
    "<module name=\"Checker\"/>\n"
)


def test_doctype_with_external_id_is_parsed_and_line_numbers_stay_true():
    result = parse_xml_document(PUBLIC, "checkstyle.xml")
    assert result.diagnostics == []
    root = result.entities[0]
    assert (root.type, root.name, root.start_line, root.end_line) == ("xml_document", "module", 4, 4)
    assert "PUBLIC" in "".join(chunk.content for chunk in result.chunks)  # Originaltext bleibt


def test_system_doctype_without_subset_is_parsed():
    result = parse_xml_document('<!DOCTYPE a SYSTEM "a.dtd">\n<a/>', "a.xml")
    assert result.diagnostics == [] and result.entities[0].name == "a"


def test_doctype_with_internal_entity_subset_stays_blocked():
    source = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>\n'
        "<lolz>&lol2;</lolz>\n"
    )
    result = parse_xml_document(source, "lolz.xml")
    assert result.entities == []
    assert result.diagnostics[0].code == "XML_EXTERNAL_DECLARATION_BLOCKED"
    assert result.diagnostics[0].line == 2


def test_external_doctype_next_to_entity_declaration_stays_blocked():
    source = '<!DOCTYPE a SYSTEM "a.dtd">\n<!-- <!ENTITY x "y"> -->\n<a/>'
    assert parse_xml_document(source, "a.xml").diagnostics[0].code == "XML_EXTERNAL_DECLARATION_BLOCKED"


def test_html_named_entities_without_dtd_do_not_abort_the_file():
    """Syncope `src/site/xdoc/docs/index.xml` enthält `&nbsp;` ohne DTD."""
    source = '<?xml version="1.0"?>\n<document>\n  <p>a&nbsp;b &amp; c</p>\n</document>\n'
    result = parse_xml_document(source, "index.xml")
    assert result.diagnostics == []
    assert result.entities[0].name == "document"


def test_unknown_named_entities_stay_a_parse_error():
    result = parse_xml_document("<a>&bogus;</a>", "a.xml")
    assert [d.code for d in result.diagnostics] == ["XML_PARSE_ERROR"]
