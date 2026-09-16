"""Deterministic programming-language detection for repository ingestion.

File extensions are the primary signal because they are stable, cheap to
evaluate before parsing, and can therefore participate in the resumable
analysis fingerprint. The mapping deliberately contains language labels, not
parser implementations: languages without a structure parser still get
useful metadata and generic code chunking.
"""

from __future__ import annotations

import os


# Keep this mapping intentionally conservative. Formats such as Markdown,
# XML, YAML and properties remain ordinary text documents.
DEFAULT_LANGUAGE_EXTENSIONS: dict[str, set[str]] = {
    "c": {".c", ".h"},
    "cpp": {".cc", ".cpp", ".cxx", ".hxx", ".hpp"},
    "csharp": {".cs"},
    "dart": {".dart"},
    "go": {".go"},
    "groovy": {".groovy", ".gradle"},
    "java": {".java"},
    "javascript": {".js", ".jsx", ".mjs", ".cjs"},
    "kotlin": {".kt", ".kts"},
    "lua": {".lua"},
    "perl": {".pl", ".pm"},
    "php": {".php"},
    "powershell": {".ps1", ".psm1", ".psd1"},
    "python": {".py", ".pyw"},
    "r": {".r", ".rmd"},
    "ruby": {".rb", ".rake", ".gemspec"},
    "rust": {".rs"},
    "scala": {".scala", ".sc"},
    "shell": {".sh", ".bash", ".zsh", ".fish"},
    "swift": {".swift"},
    "typescript": {".ts", ".tsx", ".mts", ".cts"},
    "sql": {".sql"},
    "terraform": {".tf", ".tfvars"},
}


def detect_language(path: str, extensions: dict[str, set[str]] | None = None) -> str:
    """Return the normalized language label for ``path``.

    ``extensions`` is the resolved source configuration. It is merged by the
    caller from these defaults, worker-level configuration and optional
    per-source overrides, so legacy custom extensions continue to work.
    Unknown extensions intentionally return ``text``.
    """

    configured = extensions or DEFAULT_LANGUAGE_EXTENSIONS
    suffix = os.path.splitext(path)[1].lower()
    for language, suffixes in configured.items():
        if suffix in suffixes:
            return language
    return "text"
