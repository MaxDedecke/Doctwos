"""Explicit AsciiDoc build attributes and a read-only, repository-bounded loader."""

import hashlib
import json
import os
from pathlib import Path


def configuration_fingerprint():
    return hashlib.sha256(os.getenv("DOCTUS_ASCIIDOC_ATTRIBUTES", "{}").encode()).hexdigest()


def prepare_asciidoc_source(root, extensions, profiles):
    attributes = json.loads(os.getenv("DOCTUS_ASCIIDOC_ATTRIBUTES", "{}"))
    if not isinstance(attributes, dict) or not all(
        isinstance(k, str) and isinstance(v, (str, int, bool)) for k, v in attributes.items()
    ):
        raise ValueError("DOCTUS_ASCIIDOC_ATTRIBUTES must be an object of scalar attributes")
    return {
        "root": str(Path(root).resolve()),
        "attributes": {
            k: str(v) if v is not True else "" for k, v in attributes.items() if v is not False
        },
    }


def load_include(prepared, path):
    if not prepared or not prepared.get("root"):
        return None
    root = Path(prepared["root"]).resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("include outside repository")
    if target.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("include exceeds 4 MiB")
    return target.read_text(encoding="utf-8-sig")
