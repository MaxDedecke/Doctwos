"""Gemeinsamer, JSON-kompatibler Evidenzvertrag für Strukturartefakte (O-150)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .analysis_fingerprint import profile_payload

SCHEMA_VERSION = 1
DEFAULT_VARIANT_KEY = "default"


def variant_key(profile: object | None) -> str:
    """Stabile Kennung der effektiven Buildvariante, ohne Secrets zu speichern."""
    if profile is None:
        return DEFAULT_VARIANT_KEY
    encoded = json.dumps(profile_payload(profile), sort_keys=True, separators=(",", ":")).encode()
    return f"profile:{hashlib.sha256(encoded).hexdigest()[:16]}"


def variant_evidence(profile: object | None) -> dict[str, Any]:
    """Darstellbare, nicht geheime Beschreibung der effektiven Variante."""
    return {
        "key": variant_key(profile),
        "compiler_family": getattr(profile, "compiler_family", None),
        "compiler_version": getattr(profile, "compiler_version", None),
        "source_format": getattr(profile, "source_format", None),
        "resolved_from": dict(getattr(profile, "resolved_from", {})),
    }


def source_evidence(
    *, path: str, start_line: int, end_line: int, profile: object | None
) -> dict[str, Any]:
    """Herkunft eines Artefakts in der unveränderten Originalquelle."""
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "source",
        "source": {"file_path": path, "start_line": start_line, "end_line": end_line},
        "variant": variant_evidence(profile),
        "condition": None,
    }
