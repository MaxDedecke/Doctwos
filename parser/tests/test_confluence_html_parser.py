"""
O-082: Section-Tracking von _html_to_text()/_ConfluenceHTMLParser.

Reine Unit-Tests ohne DB/Netzwerk -- _html_to_text() ist eine freie Funktion.
Prüft, dass die zurückgegebene line_sections-Liste exakt 1:1 mit den Zeilen
des zurückgegebenen Texts indiziert ist (Voraussetzung dafür, dass
base.py::_process_document per chunk["start_line"] die richtige Section
nachschlagen kann), und dass die alte Text-Ausgabe unverändert bleibt (Block-
Tags trennen weiterhin mit genau einer Leerzeile).
"""

from connectors.confluence import _html_to_text


def test_no_headings_all_sections_none():
    html = "<p>Erster Absatz.</p><p>Zweiter Absatz.</p>"
    text, sections = _html_to_text(html)
    assert text == "Erster Absatz.\n\nZweiter Absatz."
    assert sections == [None, None, None]


def test_heading_applies_to_itself_and_following_lines():
    html = "<h1>Übersicht</h1><p>Text unter der Überschrift.</p>"
    text, sections = _html_to_text(html)
    lines = text.split("\n")
    assert lines == ["Übersicht", "", "Text unter der Überschrift."]
    assert sections == ["Übersicht", "Übersicht", "Übersicht"]


def test_second_heading_changes_section_for_following_lines():
    html = "<h1>Setup</h1><p>Schritt 1.</p><h2>Betrieb</h2><p>Schritt 2.</p><p>Schritt 3.</p>"
    text, sections = _html_to_text(html)
    lines = text.split("\n")
    assert len(lines) == len(sections)
    betrieb_idx = lines.index("Betrieb")
    # Vor der zweiten Überschrift gehört jede Zeile noch zu "Setup" ...
    assert all(s == "Setup" for s in sections[:betrieb_idx])
    # ... ab ihr (inklusive der Überschriftenzeile selbst) zu "Betrieb".
    assert all(s == "Betrieb" for s in sections[betrieb_idx:])


def test_heading_with_inline_markup_captured_fully():
    html = "<h2>Teil <strong>Eins</strong> und Zwei</h2><p>Inhalt.</p>"
    text, sections = _html_to_text(html)
    lines = text.split("\n")
    assert lines[0] == "Teil Eins und Zwei"
    assert lines[-1] == "Inhalt."
    assert all(s == "Teil Eins und Zwei" for s in sections)


def test_text_before_first_heading_has_no_section():
    html = "<p>Einleitung ohne Überschrift.</p><h1>Details</h1><p>Mehr Text.</p>"
    text, sections = _html_to_text(html)
    lines = text.split("\n")
    einleitung_idx = lines.index("Einleitung ohne Überschrift.")
    details_idx = lines.index("Details")
    assert sections[einleitung_idx] is None
    assert sections[details_idx] == "Details"
    assert sections[lines.index("Mehr Text.")] == "Details"


def test_blank_line_collapse_keeps_sections_aligned():
    # Mehrere <div>/<p> hintereinander ohne Text erzeugen Leerzeilen im Buffer,
    # die auf höchstens eine Leerzeile kollabiert werden -- die Section-Liste
    # muss dabei Schritt halten (kein Off-by-one nach dem Kollabieren).
    html = "<h1>A</h1><div></div><div></div><div></div><p>Nach den Leerzeilen.</p>"
    text, sections = _html_to_text(html)
    lines = text.split("\n")
    assert len(lines) == len(sections)
    assert lines[0] == "A"
    assert lines[-1] == "Nach den Leerzeilen."
    assert all(s == "A" for s in sections)
    # Kollabiert auf höchstens eine Leerzeile am Stück.
    assert "".join("x" if line else "-" for line in lines).count("--") == 0


def test_pre_block_between_headings_keeps_section():
    html = "<h1>Beispiel</h1><pre>code_line_1\ncode_line_2</pre><h2>Ende</h2><p>Fertig.</p>"
    text, sections = _html_to_text(html)
    lines = text.split("\n")
    assert len(lines) == len(sections)
    assert sections[lines.index("code_line_1")] == "Beispiel"
    assert sections[lines.index("code_line_2")] == "Beispiel"
    end_idx = lines.index("Ende")
    assert sections[end_idx] == "Ende"
    assert sections[lines.index("Fertig.")] == "Ende"


def test_empty_heading_does_not_overwrite_current_section():
    html = "<h1>Titel</h1><h2></h2><p>Text.</p>"
    text, sections = _html_to_text(html)
    lines = text.split("\n")
    # Eine leere Überschrift liefert keinen Section-Namen -- die vorherige
    # Section bleibt gültig statt auf None zu fallen.
    assert sections[lines.index("Text.")] == "Titel"
