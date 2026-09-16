"""Strikte, profilierte Textdekodierung für importierte Quellartefakte."""

from __future__ import annotations

import codecs
import re

_CCSID = re.compile(r"^(?:IBM|CCSID)[-_ ]?(\d+)$", re.I)


class SourceDecodeError(ValueError):
    """Dekodierung ist nicht sicher möglich und darf nicht erraten werden."""


def resolve_encoding(encoding: str | None) -> str:
    """Löst Profilnamen wie ``CCSID-273`` auf einen Python-Codec auf."""
    requested = (encoding or "utf-8").strip()
    match = _CCSID.fullmatch(requested)
    candidate = f"cp{match.group(1)}" if match else requested
    try:
        return codecs.lookup(candidate).name
    except LookupError as error:
        raise SourceDecodeError(
            f"unbekannte oder nicht verfügbare Codepage '{requested}'"
        ) from error


def decode_source(raw: bytes, encoding: str | None = None) -> tuple[str, str]:
    """Dekodiert strikt und gibt Text plus tatsächlich verwendeten Codec zurück."""
    codec = resolve_encoding(encoding)
    try:
        return raw.decode(codec, errors="strict"), codec
    except UnicodeDecodeError as error:
        label = encoding or "UTF-8"
        raise SourceDecodeError(f"kein {label}-Text: Byte {error.start} ist ungültig") from error


def looks_like_text(content: str, max_control_char_ratio: float) -> bool:
    """Lehnt Steuerzeichen-Datenmüll nach erfolgreicher Dekodierung ab."""
    if not content:
        return True
    control_chars = sum(
        1 for char in content if char not in "\t\r\n" and (ord(char) < 32 or ord(char) == 127)
    )
    return control_chars / len(content) <= max_control_char_ratio
