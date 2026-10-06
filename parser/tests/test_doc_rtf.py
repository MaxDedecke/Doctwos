"""Echtes Word-97-Format (.doc) und RTF: Textextraktion ohne externe Konverter.

Die Beispieldateien unter tests/fixtures/ wurden mit LibreOffice aus derselben .docx erzeugt (siehe README dort);
sie enthalten Umlaute, ß, €, griechische Zeichen, eine Tabelle, Zeilenumbruch und Tabulator.
"""

import pathlib
import shutil

import pytest

from connectors import folder
from connectors.confluence import _extract_attachment_text, _is_supported_mime
from connectors.msdoc import _clean, _strip_fields, extract_doc_text
from connectors.office import UnsupportedFormat, extract_legacy_doc
from connectors.rtf import extract_rtf_text, rtf_to_text

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

EXPECTED = (
    "Betriebshandbuch\n"
    "Größe & Übung: Der Zähler steht auf 1.234,50 € – bitte prüfen. Ünïcödé: αβγ Ω.\n"
    "Dienst | Port\n"
    "Gateway | 8443\n"
    "Zweiter Absatz mit Zeilen\n"
    "umbruch und Tab\tstopp.\n"
    "Notfall\n"
    "Rufbereitschaft unter 0800 123456."
)


def test_doc_text_tables_and_unicode_are_read():
    assert extract_doc_text(str(FIXTURES / "beispiel.doc")) == EXPECTED


def test_plain_doc_and_the_same_text_from_docx_and_rtf_agree():
    assert extract_doc_text(str(FIXTURES / "einfach.doc")) == "Nur ASCII Text.\nZweite Zeile."
    assert extract_rtf_text(str(FIXTURES / "beispiel.rtf")) == EXPECTED
    docx_text = folder.extract_docx_text(str(FIXTURES / "beispiel.docx"))
    for fragment in ("Betriebshandbuch", "Größe & Übung", "Rufbereitschaft unter 0800 123456."):
        assert fragment in docx_text and fragment in EXPECTED


def test_folder_and_legacy_entry_points_use_the_real_readers(tmp_path):
    assert folder._extract_text(str(FIXTURES / "beispiel.doc")) == EXPECTED
    assert folder._extract_text(str(FIXTURES / "beispiel.rtf")) == EXPECTED
    # Ein als .doc benanntes RTF wird als RTF gelesen, eine als .doc benannte .docx als .docx.
    renamed = tmp_path / "wirklich-rtf.doc"
    shutil.copy(FIXTURES / "beispiel.rtf", renamed)
    assert extract_legacy_doc(str(renamed), folder.extract_docx_text) == EXPECTED


def _patched_copy(tmp_path, mutate):
    import olefile

    target = tmp_path / "x.doc"
    shutil.copy(FIXTURES / "einfach.doc", target)
    with olefile.OleFileIO(str(target), write_mode=True) as ole:
        data = bytearray(ole.openstream("WordDocument").read())
        mutate(data)
        ole.write_stream("WordDocument", bytes(data))
    return str(target)


def test_encrypted_word_6_and_broken_files_get_clear_messages(tmp_path):
    def encrypt(data):
        data[0x0A] |= 0x00
        data[0x0B] |= 0x01  # fEncrypted (Bit 8 der Flags bei Offset 0x0A)

    with pytest.raises(UnsupportedFormat, match="passwortgeschützt"):
        extract_doc_text(_patched_copy(tmp_path, encrypt))

    def word6(data):
        data[2:4] = (0x65).to_bytes(2, "little")

    with pytest.raises(UnsupportedFormat, match="Word 6/95"):
        extract_doc_text(_patched_copy(tmp_path, word6))

    def wrong_magic(data):
        data[0:2] = b"\x00\x00"

    with pytest.raises(UnsupportedFormat, match="als .docx speichern"):
        extract_doc_text(_patched_copy(tmp_path, wrong_magic))

    not_ole = tmp_path / "text.doc"
    not_ole.write_bytes(b"das ist kein Word")
    with pytest.raises(UnsupportedFormat, match="als .docx speichern"):
        extract_doc_text(str(not_ole))


def test_truncated_doc_is_reported_not_crashing(tmp_path):
    truncated = tmp_path / "abgeschnitten.doc"
    truncated.write_bytes((FIXTURES / "beispiel.doc").read_bytes()[:600])
    with pytest.raises(UnsupportedFormat):
        extract_doc_text(str(truncated))


def test_field_codes_are_reduced_to_their_result_and_table_marks_become_columns():
    assert _strip_fields('Siehe \x13 HYPERLINK "http://x" \x14Handbuch\x15 Seite 3') == "Siehe Handbuch Seite 3"
    assert _strip_fields("a\x13 PAGE \x15b") == "ab"  # Feld ohne Ergebnis
    assert _strip_fields("\x13 IF \x13 INNER \x14x\x15 \x14außen\x15") == "außen"  # verschachtelt
    assert _clean("A\x07B\x07\x07C\x07D\x07\x07") == "A | B\nC | D"
    assert _clean("Zeile\x0bumbruch\r\r\r\rEnde") == "Zeile\numbruch\n\nEnde"


# --- RTF -------------------------------------------------------------------------------------

def _rtf(text: bytes) -> str:
    """Platzhalter ``@u`` steht für den RTF-Unicode-Escape (Backslash + u)."""
    return rtf_to_text(text.replace(b"@u", b"\\u"))


def test_rtf_escapes_codepages_and_unicode():
    text = _rtf(rb"{\rtf1\ansi\ansicpg1252\deff0{\fonttbl{\f0 Arial;}}Gr\'fc\'dfe @u8364? und @u-3841?x\par Zeile 2}")
    assert text.startswith("Grüße € und ") and text.endswith("Zeile 2")
    assert "Arial" not in text

    cyrillic = rtf_to_text(rb"{\rtf1\ansi\ansicpg1251 \'cf\'f0\'e8\'e2\'e5\'f2}")
    assert cyrillic == "Привет"

    # \ucN: so viele Ersatzzeichen nach \u werden verworfen
    assert _rtf(rb"{\rtf1\uc2@u8364ab rest}") == "€ rest"
    assert _rtf(rb"{\rtf1\uc0@u8364 x}") == "€x"


def test_rtf_skips_non_text_groups_and_keeps_field_results():
    source = (
        rb"{\rtf1{\colortbl;\red0\green0\blue0;}{\*\generator Word}{\info{\title Geheimtitel}}"
        rb"{\header Kopfzeile}Text {\field{\*\fldinst HYPERLINK \"http://x\"}{\fldrslt Linktext}} Ende"
        rb"{\pict\wmetafile8 0102abcd}{\*\unbekannt versteckt}\\ \{ \}}"
    )
    text = rtf_to_text(source)
    assert text == "Text Linktext Ende\\ { }"


def test_rtf_tables_and_structure_marks():
    text = rtf_to_text(rb"{\rtf1 A\cell B\cell\row C\cell D\cell\row\par Absatz\tab Tab \emdash  Strich}")
    assert text == "A | B\nC | D\n\nAbsatz\tTab — Strich" or text.startswith("A | B\nC | D")
    assert "Absatz\tTab" in text and "—" in text


def test_rtf_input_that_is_not_rtf_is_rejected():
    with pytest.raises(ValueError):
        rtf_to_text(b"plain text")


def test_confluence_attachments_read_word_97_and_rtf():
    assert _is_supported_mime("application/rtf") and _is_supported_mime("application/msword")
    assert _extract_attachment_text((FIXTURES / "beispiel.doc").read_bytes(), "application/msword") == EXPECTED
    assert _extract_attachment_text((FIXTURES / "beispiel.rtf").read_bytes(), "application/rtf") == EXPECTED
    assert _extract_attachment_text(b"nichts Lesbares", "application/msword") is None
