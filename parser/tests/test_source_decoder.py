import pytest

from core.source_decoder import (
    ImplausibleFallbackError,
    SourceDecodeError,
    decode_legacy_source,
    decode_source,
    looks_like_text,
    resolve_encoding,
)


def test_decodes_confirmed_ebcdic_ccsid_without_losing_characters():
    source = "IDENTIFICATION DIVISION.\nPROGRAM-ID. GRÜSSE.\nDISPLAY 'ÄÖÜß'.\n"

    decoded, codec = decode_source(source.encode("cp273"), "CCSID-273")

    assert decoded == source
    assert codec == "cp273"


def test_default_decoder_is_strict_utf8():
    with pytest.raises(SourceDecodeError, match="UTF-8"):
        decode_source(bytes([0xF0, 0xF1]))


def test_unknown_codepage_is_an_explicit_error_not_a_lossy_fallback():
    with pytest.raises(SourceDecodeError, match="Codepage"):
        resolve_encoding("CCSID-1141")


def test_control_character_check_happens_after_decoding():
    assert looks_like_text("COBOL\nTEXT", 0.05) is True
    assert looks_like_text("\x01\x02\x03\x04\x05" * 20, 0.05) is False


def test_legacy_decoder_keeps_utf8_and_reads_windows_ansi_as_fallback():
    utf8, utf8_codec = decode_legacy_source("* Prüfung\n".encode("utf-8"))
    ansi, ansi_codec = decode_legacy_source("* Prüfung\n".encode("cp1252"))

    assert (utf8, utf8_codec) == ("* Prüfung\n", "utf-8")
    assert (ansi, ansi_codec) == ("* Prüfung\n", "cp1252")


def test_legacy_decoder_rejects_ebcdic_instead_of_reading_it_as_text():
    ebcdic = "IDENTIFICATION DIVISION.\nPROGRAM-ID. TEST.\n".encode("cp273")

    with pytest.raises(ImplausibleFallbackError, match="EBCDIC") as error:
        decode_legacy_source(ebcdic)
    assert error.value.suspected_binary is False


def test_legacy_decoder_stays_strict_when_a_codepage_is_configured():
    with pytest.raises(SourceDecodeError, match="(?i)utf-8"):
        decode_legacy_source("Prüfung".encode("cp1252"), "utf-8")
