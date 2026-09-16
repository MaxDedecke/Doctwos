"""Bezeichnervergleich ohne verlustbehaftete Unicode-Faltung (O-126)."""

from __future__ import annotations

import unicodedata

# Die Bestandsfixtures und der bisherige Lexer unterstützen diese deutschen
# Zeichen bereits. Weitere Unicode-Buchstaben werden nicht stillschweigend
# normalisiert: Sie bleiben sichtbar, bis ein bestätigtes Kundenprofil ihren
# Dialekt/Zeichensatz freigibt (O-127).
_SUPPORTED_NON_ASCII = frozenset("ÄÖÜäöüß")


def canonical_identifier(value: str) -> str:
    """Vergleichsschlüssel für COBOL-Namen, Originalschreibweise bleibt außen.

    COBOL-Schlüsselwörter und klassische Bezeichner sind ASCII-unabhängig von
    Groß-/Kleinschreibung. Nicht-ASCII-Zeichen bleiben dagegen unverändert.
    Insbesondere darf ``ß`` nicht zu ``S`` (ANTLRs reiner Parse-Surrogat) oder
    ``SS`` gefaltet werden und so mit einem anderen Namen kollidieren.
    """
    normalized = unicodedata.normalize("NFC", value)
    return "".join(char.upper() if "a" <= char <= "z" else char for char in normalized)


def unsupported_identifier_characters(value: str) -> tuple[str, ...]:
    """Nicht bestätigte Zeichen, in stabiler Fundreihenfolge dedupliziert."""
    return tuple(
        dict.fromkeys(
            char for char in value if ord(char) > 127 and char not in _SUPPORTED_NON_ASCII
        )
    )
