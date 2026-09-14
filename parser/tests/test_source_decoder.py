import pytest

from core.source_decoder import SourceDecodeError, decode_source, looks_like_text, resolve_encoding


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
