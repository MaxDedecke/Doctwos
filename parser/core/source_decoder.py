"""Strikte, profilierte Textdekodierung für importierte Quellartefakte."""

from __future__ import annotations

import codecs
import re

_CCSID = re.compile(r"^(?:IBM|CCSID)[-_ ]?(\d+)$", re.I)


class SourceDecodeError(ValueError):
    """Dekodierung ist nicht sicher möglich und darf nicht erraten werden."""

    # Der Connector hängt bei Verdacht auf Binärdaten einen entsprechenden Hinweis an.
    suspected_binary = True


class ImplausibleFallbackError(SourceDecodeError):
    """Der Rückfall-Codec dekodiert zwar, ergibt aber überwiegend Nicht-ASCII-Zeichen."""

    suspected_binary = False


# Mainframe-Quellen (COBOL, Copybook, JCL) liegen in deutschen Beständen oft als
# Windows-ANSI vor. Ein einzelnes Umlaut-Byte macht die Datei sonst für striktes
# UTF-8 unlesbar.
LEGACY_FALLBACK_ENCODING = "cp1252"
_MAX_FALLBACK_NON_ASCII_RATIO = 0.1


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


def decode_source(
    raw: bytes,
    encoding: str | None = None,
    *,
    fallback_encoding: str | None = None,
) -> tuple[str, str]:
    """Dekodiert strikt und gibt Text plus tatsächlich verwendeten Codec zurück.

    Ein optionaler Fallback wird ausschließlich nach einem ungültigen Byte für
    den primären Codec versucht. Fehlerhafte Codec-Konfigurationen bleiben
    sichtbar und werden nicht durch den Fallback verdeckt.
    """
    codec = resolve_encoding(encoding)
    try:
        return raw.decode(codec, errors="strict"), codec
    except UnicodeDecodeError as error:
        if fallback_encoding is not None:
            fallback_codec = resolve_encoding(fallback_encoding)
            try:
                return raw.decode(fallback_codec, errors="strict"), fallback_codec
            except UnicodeDecodeError:
                # Keep the primary error: it explains why the selected source
                # encoding failed, while the caller may report it as a skip.
                pass
        label = encoding or "UTF-8"
        raise SourceDecodeError(f"kein {label}-Text: Byte {error.start} ist ungültig") from error


def decode_legacy_source(raw: bytes, encoding: str | None = None) -> tuple[str, str]:
    """Wie :func:`decode_source`, mit sichtbarem cp1252-Rückfall für ältere Quellen.

    Ein ausdrücklich konfigurierter Codec bleibt strikt. Ohne Konfiguration gilt
    UTF-8 und erst bei ungültigen Bytes ``LEGACY_FALLBACK_ENCODING``. Ein
    Fallback-Ergebnis mit überwiegend Nicht-ASCII-Zeichen (typisch für EBCDIC) wird
    abgelehnt, statt Datenmüll als Quelltext zu behandeln.
    """
    fallback = None if encoding else LEGACY_FALLBACK_ENCODING
    content, codec = decode_source(raw, encoding, fallback_encoding=fallback)
    if fallback is not None and codec == resolve_encoding(fallback) and content:
        non_ascii = sum(1 for char in content if ord(char) > 127)
        if non_ascii / len(content) > _MAX_FALLBACK_NON_ASCII_RATIO:
            raise ImplausibleFallbackError(
                f"weder UTF-8 noch plausibler {codec}-Text (überwiegend Nicht-ASCII-Zeichen, "
                "möglicherweise EBCDIC; Codepage im Buildprofil (encoding) angeben)"
            )
    return content, codec


def looks_like_text(content: str, max_control_char_ratio: float) -> bool:
    """Lehnt Steuerzeichen-Datenmüll nach erfolgreicher Dekodierung ab."""
    if not content:
        return True
    control_chars = sum(
        1 for char in content if char not in "\t\r\n" and (ord(char) < 32 or ord(char) == 127)
    )
    return control_chars / len(content) <= max_control_char_ratio
