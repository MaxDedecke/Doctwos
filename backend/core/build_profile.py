"""Prüfung der Quellkonfiguration für COBOL-Buildprofil und Sprachzuordnung (O-151).

Der Parser liest `spaces.build_profile` und `spaces.language_paths` tolerant und
ignoriert Ungültiges still. Diese Funktionen sind die strenge Eingangsprüfung, damit
ein Tippfehler beim Speichern auffällt statt erst als wirkungsloser Wert im Sync.
Die erlaubten Werte spiegeln `parser/cobol/profile.py` und `parser/core/model.py`
(getrennte Docker-Build-Kontexte, deshalb keine gemeinsame Importquelle).
"""

from __future__ import annotations

import codecs
import re
from typing import Any

SOURCE_FORMATS = ("fixed", "free", "variable", "extended")
LITERAL_DELIMITERS = ("both", "apostrophe", "quote")
LANGUAGE_PATH_LABELS = ("cobol", "copybook", "jcl")

_CCSID = re.compile(r"^(?:IBM|CCSID)[-_ ]?(\d+)$", re.I)
_FRAGMENT_FIELDS = (
    "compiler_family",
    "compiler_version",
    "source_format",
    "source_columns",
    "encoding",
    "debug_mode",
    "literal_delimiter",
    "defines",
    "copy_search_order",
)
_COLUMN_FIELDS = ("sequence_end", "indicator_column", "area_a_start", "area_b_start", "code_end")


class ProfileValidationError(ValueError):
    """Mit deutscher, für Anwender lesbarer Meldung."""


def _text(value: Any, name: str, limit: int = 64) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ProfileValidationError(
            f"'{name}' muss ein nicht leerer Text (max. {limit} Zeichen) sein."
        )
    return value.strip()


def _normalize_prefix(prefix: Any, name: str) -> str:
    if not isinstance(prefix, str):
        raise ProfileValidationError(f"{name}: Pfadpräfix muss Text sein.")
    cleaned = prefix.strip().strip("/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ProfileValidationError(f"{name}: ungültiger Pfadpräfix '{prefix}'.")
    return cleaned


def _validate_encoding(value: Any) -> str:
    requested = _text(value, "encoding")
    match = _CCSID.fullmatch(requested)
    candidate = f"cp{match.group(1)}" if match else requested
    try:
        codecs.lookup(candidate)
    except LookupError as error:
        raise ProfileValidationError(
            f"Unbekannte Codepage '{requested}' (Beispiele: utf-8, cp1252, CCSID-273, IBM-1141)."
        ) from error
    return requested


def _validate_columns(value: Any) -> dict[str, int | None]:
    if not isinstance(value, dict) or set(value) - set(_COLUMN_FIELDS):
        raise ProfileValidationError(f"'source_columns' erlaubt nur: {', '.join(_COLUMN_FIELDS)}.")
    columns: dict[str, int | None] = {}
    for key, raw in value.items():
        if key == "code_end" and raw is None:
            columns[key] = None
        elif isinstance(raw, int) and not isinstance(raw, bool) and raw >= 1:
            columns[key] = raw
        else:
            raise ProfileValidationError(f"'source_columns.{key}' muss eine positive Zahl sein.")
    seq = columns.get("sequence_end", 6)
    ind = columns.get("indicator_column", 7)
    a = columns.get("area_a_start", 8)
    b = columns.get("area_b_start", 12)
    end = columns.get("code_end")
    if not (seq < ind < a <= b) or (end is not None and end < b):
        raise ProfileValidationError(
            "'source_columns' muss sequence_end < indicator_column < area_a_start <= "
            "area_b_start (<= code_end) erfüllen."
        )
    return columns


def validate_fragment(raw: Any, where: str = "build_profile") -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProfileValidationError(f"'{where}' muss ein Objekt sein.")
    unknown = set(raw) - set(_FRAGMENT_FIELDS)
    if unknown:
        raise ProfileValidationError(
            f"{where}: unbekannte Felder {', '.join(sorted(map(str, unknown)))}. "
            f"Erlaubt: {', '.join(_FRAGMENT_FIELDS)}."
        )
    fragment: dict[str, Any] = {}
    for key, value in raw.items():
        if value is None:
            continue
        if key in ("compiler_family", "compiler_version"):
            fragment[key] = _text(value, key)
        elif key == "source_format":
            if value not in SOURCE_FORMATS:
                raise ProfileValidationError(
                    f"'source_format' muss eines von {', '.join(SOURCE_FORMATS)} sein."
                )
            fragment[key] = value
        elif key == "literal_delimiter":
            if value not in LITERAL_DELIMITERS:
                raise ProfileValidationError(
                    f"'literal_delimiter' muss eines von {', '.join(LITERAL_DELIMITERS)} sein."
                )
            fragment[key] = value
        elif key == "encoding":
            fragment[key] = _validate_encoding(value)
        elif key == "debug_mode":
            if not isinstance(value, bool):
                raise ProfileValidationError("'debug_mode' muss true oder false sein.")
            fragment[key] = value
        elif key == "source_columns":
            fragment[key] = _validate_columns(value)
        elif key == "defines":
            if not isinstance(value, dict) or not all(
                isinstance(k, str) and k.strip() and isinstance(v, (str, int, bool))
                for k, v in value.items()
            ):
                raise ProfileValidationError("'defines' muss Name-Wert-Paare enthalten.")
            fragment[key] = {k.strip(): str(v) for k, v in value.items()}
        elif key == "copy_search_order":
            if not isinstance(value, list) or not value:
                raise ProfileValidationError(
                    "'copy_search_order' muss eine nicht leere Liste sein."
                )
            fragment[key] = [_normalize_prefix(item, "copy_search_order") for item in value]
    return fragment


def validate_build_profile(raw: Any) -> dict[str, Any]:
    """Normalisiert auf ``{"source": Fragment, "paths": {Präfix: Fragment}}``."""
    if not isinstance(raw, dict):
        raise ProfileValidationError("'build_profile' muss ein Objekt sein.")
    if "source" in raw or "paths" in raw:
        extra = set(raw) - {"source", "paths"}
        if extra:
            raise ProfileValidationError(
                f"build_profile: unbekannte Felder {', '.join(sorted(map(str, extra)))}."
            )
        source_raw = raw.get("source") or {}
        paths_raw = raw.get("paths") or {}
    else:
        source_raw, paths_raw = raw, {}
    if not isinstance(paths_raw, dict):
        raise ProfileValidationError("'build_profile.paths' muss ein Objekt sein.")
    profile: dict[str, Any] = {"source": validate_fragment(source_raw, "build_profile.source")}
    profile["paths"] = {
        _normalize_prefix(prefix, "build_profile.paths"): validate_fragment(
            fragment, f"build_profile.paths['{prefix}']"
        )
        for prefix, fragment in paths_raw.items()
    }
    return profile


def validate_language_paths(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ProfileValidationError("'language_paths' muss ein Objekt sein.")
    result: dict[str, str] = {}
    for prefix, label in raw.items():
        if label not in LANGUAGE_PATH_LABELS:
            raise ProfileValidationError(
                f"language_paths['{prefix}']: Sprache muss eine von "
                f"{', '.join(LANGUAGE_PATH_LABELS)} sein."
            )
        result[_normalize_prefix(prefix, "language_paths")] = label
    return result
