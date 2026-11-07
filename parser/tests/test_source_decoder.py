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
        resolve_encoding("CCSID-9999")


def test_ccsid_1141_reads_like_273():
    assert resolve_encoding("CCSID-1141") == "cp273"


def test_control_character_check_happens_after_decoding():
    assert looks_like_text("COBOL\nTEXT", 0.05) is True
    assert looks_like_text("\x01\x02\x03\x04\x05" * 20, 0.05) is False


def test_legacy_decoder_keeps_utf8_and_reads_windows_ansi_as_fallback():
    utf8, utf8_codec = decode_legacy_source("* Prüfung\n".encode("utf-8"))
    ansi, ansi_codec = decode_legacy_source("* Prüfung\n".encode("cp1252"))

    assert (utf8, utf8_codec) == ("* Prüfung\n", "utf-8")
    assert (ansi, ansi_codec) == ("* Prüfung\n", "cp1252")


_FIXED = [
    "000100 IDENTIFICATION DIVISION.",
    "000200 PROGRAM-ID. GRUSS.",
    "000300* Prüfung der Überweisung für Kunden",
    "000400 PROCEDURE DIVISION.",
    "000500     DISPLAY 'Grüße aus München'.",
    "000600     STOP RUN.",
]


def _records(lines: list[str]) -> list[str]:
    return [line.ljust(80) for line in lines]


def test_legacy_decoder_detects_ebcdic_with_line_ends():
    source = "\n".join(_records(["000100 IDENTIFICATION DIVISION.", "000200 PROGRAM-ID. TEST."]))

    decoded, codec = decode_legacy_source(source.encode("cp037"))

    assert (decoded, codec) == (source, "cp037")


def test_legacy_decoder_splits_ebcdic_records_and_picks_the_german_codepage():
    records = _records(_FIXED)

    decoded, codec = decode_legacy_source("".join(records).encode("cp273"))

    assert codec == "cp273"
    assert decoded.split("\n") == records


def test_configured_ebcdic_codepage_also_splits_records():
    records = _records(_FIXED)

    decoded, codec = decode_source("".join(records).encode("cp273"), "CCSID-1141")

    assert codec == "cp273"
    assert decoded.split("\n") == records


def test_legacy_decoder_does_not_take_windows_ansi_for_ebcdic():
    source = "\n".join(_FIXED) + "\n"

    assert decode_legacy_source(source.encode("cp1252")) == (source, "cp1252")


def test_legacy_decoder_rejects_ebcdic_data_records_instead_of_reading_them_as_text():
    packed = bytes([0x00, 0x01, 0x23, 0x4C, 0x9F, 0xF1, 0xC1, 0x0C] * 40)

    with pytest.raises(ImplausibleFallbackError, match="EBCDIC") as error:
        decode_legacy_source(packed)
    assert error.value.suspected_binary is False


def test_legacy_decoder_stays_strict_when_a_codepage_is_configured():
    with pytest.raises(SourceDecodeError, match="(?i)utf-8"):
        decode_legacy_source("Prüfung".encode("cp1252"), "utf-8")
