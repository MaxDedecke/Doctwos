"""O-378: .properties werden strukturiert (Schlüssel mit Zeilen), Übersetzungen nur als Wurzel."""

from core.model import classify_completeness
from core.registry import STRUCTURE_PARSERS
from resources.properties import parse_properties_file, split_bundle_locale

SOURCE = """# Kommentar
! auch ein Kommentar

greeting=Hallo Welt
path : C:\\\\temp\\\\x
multi = erste Zeile \\
        zweite Zeile
spaced\\ key=with blank
db.password=geheim
empty
greeting=zweiter Wert
"""


def _by_key(result):
    return {e.qualified_name.split("::", 1)[1]: e for e in result.entities if e.type == "property"}


def test_keys_values_lines_and_continuations_of_a_base_bundle():
    result = parse_properties_file(SOURCE, "core/src/main/resources/messages.properties")
    assert result.entities[0].type == "properties_file"
    props = _by_key(result)
    assert (props["greeting"].start_line, props["greeting"].end_line) == (4, 4)
    assert props["greeting"].meta["value_preview"] == "Hallo Welt"
    assert props["path"].meta["value_preview"] == "C:\\\\temp\\\\x"
    assert (props["multi"].start_line, props["multi"].end_line) == (6, 7)
    assert props["multi"].meta["value_preview"] == "erste Zeile zweite Zeile"
    assert props["spaced key"].meta["value_preview"] == "with blank"
    assert props["empty"].meta["value_preview"] == ""


def test_duplicate_keys_get_distinct_qualified_names_and_secrets_are_redacted():
    result = parse_properties_file(SOURCE, "messages.properties")
    names = [e.qualified_name for e in result.entities if e.name == "greeting"]
    assert names == ["messages.properties::greeting", "messages.properties::greeting#2"]
    secret = _by_key(result)["db.password"]
    assert secret.meta["value_redacted"] is True
    assert "value_preview" not in secret.meta


def test_translation_files_only_get_a_root_with_bundle_and_locale():
    result = parse_properties_file(SOURCE, "core/messages_de_CH.properties")
    assert [e.type for e in result.entities] == ["properties_file"]
    root = result.entities[0]
    assert (root.meta["bundle"], root.meta["locale"]) == ("core/messages", "de_CH")
    assert root.meta["property_count"] == 7


def test_bundle_locale_split_ignores_non_locale_suffixes():
    assert split_bundle_locale("a/b/Messages_en.properties") == ("a/b/Messages", "en")
    assert split_bundle_locale("a/application.properties") == ("a/application", None)
    assert split_bundle_locale("a/log_config.properties") == ("a/log_config", None)


def test_registry_parses_properties_as_complete_structure():
    entry = STRUCTURE_PARSERS["properties"]
    result = entry.parse(SOURCE, "x/messages.properties")
    assert classify_completeness(result) == ("complete", [])
    assert result.chunks and all(c.meta["language"] == "properties" for c in result.chunks)
