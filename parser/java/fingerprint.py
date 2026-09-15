"""Version fingerprint for the checked-in Java grammar inputs."""

from __future__ import annotations

import hashlib
from pathlib import Path


def grammar_fingerprint() -> str:
    grammar_dir = Path(__file__).resolve().parent / "grammar"
    digest = hashlib.sha256()
    for grammar in sorted(grammar_dir.glob("*.g4")):
        digest.update(grammar.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(grammar.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
