"""Quelltext aus Rohbytes, gleich für Import (Parser) und Anzeige (Backend).

Der Parser speichert je Datei den verwendeten Codec. Zeigt das Backend die Datei mit demselben Codec über
:func:`decode_text` an, sieht der Nutzer dieselben Zeilen, auf die sich Entitäten und Kanten beziehen.

EBCDIC (O-330): Host-Exporte kommen oft ohne Zeilenumbrüche als Folge fester 80-Byte-Sätze (RECFM=FB, LRECL=80).
Jeder Satz ist dann eine Zeile. Eine Codepage lässt sich nur an Zeichen außerhalb des gemeinsamen Grundbestands
unterscheiden (Umlaute, ``[ ] ! |``); ohne solche Zeichen gilt die konfigurierte Standard-Codepage.
"""

from __future__ import annotations

import codecs
import os

RECORD_LENGTH = 80

# Python kennt CCSID 1141 nicht; sie entspricht 273 bis auf das Euro-Zeichen (0x9F: € statt ¤).
_CODEC_ALIASES = {"cp1141": "cp273"}
_EBCDIC_CODECS = frozenset({"cp037", "cp273", "cp500", "cp1140"})
_CANDIDATES = ("cp037", "cp273", "cp500")
_SAMPLE_BYTES = 64 * 1024
_EBCDIC_SPACE = 0x40
_ASCII_SPACE = 0x20
_COBOL_PUNCTUATION = frozenset(" \n.,;:()'\"=+-*/<>$#@&%_")


def codec_name(encoding: str) -> str:
    name = codecs.lookup(_CODEC_ALIASES.get(encoding.lower(), encoding)).name
    return _CODEC_ALIASES.get(name, name)


def is_ebcdic(codec: str | None) -> bool:
    if not codec:
        return False
    try:
        return codec_name(codec) in _EBCDIC_CODECS
    except LookupError:
        return False


def decode_text(raw: bytes, codec: str, errors: str = "strict") -> str:
    """Dekodiert ``raw`` mit ``codec``; EBCDIC ohne Zeilenende wird in 80-Byte-Sätze geteilt."""
    name = codec_name(codec)
    text = raw.decode(name, errors=errors)
    if name not in _EBCDIC_CODECS:
        return text
    # EBCDIC-NL (0x15) dekodiert als U+0085, LF (0x25) als "\n".
    text = text.replace("\r\n", "\n").replace("\x85", "\n")
    if "\n" not in text and len(raw) > RECORD_LENGTH and len(raw) % RECORD_LENGTH == 0:
        text = "\n".join(
            text[start : start + RECORD_LENGTH] for start in range(0, len(text), RECORD_LENGTH)
        )
    return text


def default_ebcdic_codec() -> str:
    configured = os.environ.get("EBCDIC_DEFAULT_CODEPAGE", "cp037")
    try:
        name = codec_name(configured.replace("CCSID-", "cp").replace("IBM-", "cp"))
    except LookupError:
        return "cp037"
    return name if name in _EBCDIC_CODECS else "cp037"


def detect_ebcdic(raw: bytes) -> str | None:
    """Liefert die wahrscheinlichste EBCDIC-Codepage oder ``None``, wenn die Bytes nicht nach EBCDIC-Text aussehen.

    EBCDIC-Quelltext besteht zu einem großen Teil aus Leerzeichen (0x40, in ASCII ``@``) und enthält kaum
    ASCII-Leerzeichen; dekodiert ergibt er fast nur Buchstaben, Ziffern und COBOL-Satzzeichen."""
    sample = raw[:_SAMPLE_BYTES]
    if not sample:
        return None
    spaces = sample.count(_EBCDIC_SPACE)
    if spaces < len(sample) * 0.05 or spaces <= sample.count(_ASCII_SPACE) * 3:
        return None
    default = default_ebcdic_codec()
    best, best_score = default, _score(sample, default)
    for codec in _CANDIDATES:
        score = _score(sample, codec)
        if score > best_score:
            best, best_score = codec, score
    if best_score < len(sample) * 0.95:
        return None
    return best


def _score(sample: bytes, codec: str) -> int:
    text = decode_text(sample, codec, errors="replace")
    return sum(1 for char in text if char.isalnum() or char in _COBOL_PUNCTUATION)
