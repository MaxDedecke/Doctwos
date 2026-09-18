"""Deterministic programming-language detection for repository ingestion.

File extensions are the primary signal because they are stable, cheap to
evaluate before parsing, and can therefore participate in the resumable
analysis fingerprint. The mapping deliberately contains language labels, not
parser implementations: languages without a structure parser still get
useful metadata and generic code chunking.
"""

from __future__ import annotations

import os
import re


# Keep this mapping intentionally conservative. The labels describe the
# detected source family; they do not promise that a structure parser exists.
# O-242 deliberately keeps XML-like resources discoverable as text until the
# later structure-analysis work (O-247/O-249) provides dedicated parsers.
DEFAULT_LANGUAGE_EXTENSIONS: dict[str, set[str]] = {
    "c": {".c", ".h"},
    "cpp": {".cc", ".cpp", ".cxx", ".hxx", ".hpp"},
    "csharp": {".cs"},
    "dart": {".dart"},
    "go": {".go"},
    "groovy": {".groovy", ".gradle"},
    "html": {".html", ".htm", ".xhtml"},
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
    "jsp": {".jsp", ".jspx", ".jspf", ".tag", ".tagx"},
    "properties": {".properties"},
    "xml": {".xml", ".xsd", ".wsdl", ".xjb"},
    "xslt": {".xsl", ".xslt"},
}


_SHELL_INTERPRETERS = {
    "ash",
    "bash",
    "busybox",
    "csh",
    "dash",
    "fish",
    "ksh",
    "mksh",
    "sh",
    "tcsh",
    "zsh",
}
_SHEBANG_MAX_BYTES = 4096
_SHEBANG_MAX_LINES = 8


def _looks_like_shell_shebang(content: str | bytes | None) -> bool:
    """Recognize a shell shebang without executing or fully reading a file."""
    if content is None:
        return False
    if isinstance(content, bytes):
        content = content[:_SHEBANG_MAX_BYTES].decode("ascii", errors="ignore")
    first_line = content[:_SHEBANG_MAX_BYTES].splitlines()[:_SHEBANG_MAX_LINES]
    if not first_line or not first_line[0].startswith("#!"):
        return False
    command = first_line[0][2:].strip()
    # Support both /bin/bash and /usr/bin/env -S bash -e forms. Only the
    # interpreter basename is considered; arguments cannot turn another
    # executable into a shell.
    command = re.sub(r"^/usr/bin/env(?:\s+-S)?\s+", "", command)
    interpreter = os.path.basename(command.split()[0]) if command else ""
    return interpreter in _SHELL_INTERPRETERS


def detect_language(
    path: str,
    extensions: dict[str, set[str]] | None = None,
    content: str | bytes | None = None,
) -> str:
    """Return the normalized language label for ``path``.

    ``extensions`` is the resolved source configuration. It is merged by the
    caller from these defaults, worker-level configuration and optional
    per-source overrides, so legacy custom extensions continue to work.
    Unknown extensions intentionally return ``text``. If a file has no
    extension, a bounded shebang check can identify shell scripts without
    executing them.
    """

    configured = extensions or DEFAULT_LANGUAGE_EXTENSIONS
    # Maven descriptors are XML files syntactically, but their build
    # semantics matter for the source graph. Keep them distinguishable so a
    # dedicated static parser can inspect them without executing Maven.
    if os.path.basename(path).lower() == "pom.xml":
        return "maven"
    suffix = os.path.splitext(path)[1].lower()
    for language, suffixes in configured.items():
        if suffix in suffixes:
            return language
    if not suffix and _looks_like_shell_shebang(content):
        return "shell"
    return "text"
