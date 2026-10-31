"""Kennzahlen eines Git-Worktrees (Dateien, Zeilen je Sprache) für die Projektstatistik.

Das Zählen liest jede Datei, bei 44.000 Dateien kalt rund 10 s. Der Parser rechnet deshalb am
Sync-Ende und legt das Ergebnis an der Wissensquelle ab; das Backend liest es nur noch.
"""

import os

_READ_SIZE = 1 << 20

_EXT_LANG_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".hpp": "C/C++ Header",
    ".go": "Go",
    ".rs": "Rust",
    ".cs": "C#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".sh": "Shell",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".xml": "XML",
    ".md": "Markdown",
}


def _count_lines(path: str) -> int:
    """Blockweise, weil auch Binärdateien mit riesigen „Zeilen“ im Worktree liegen."""
    lines = 0
    last = b"\n"
    with open(path, "rb") as handle:
        while block := handle.read(_READ_SIZE):
            lines += block.count(b"\n")
            last = block[-1:]
    return lines + (last != b"\n")


def compute_worktree_stats(root: str) -> dict:
    total_files = 0
    total_lines = 0
    language_lines: dict[str, int] = {}
    for directory, subdirectories, files in os.walk(root):
        if ".git" in subdirectories:
            subdirectories.remove(".git")
        for file in files:
            path = os.path.join(directory, file)
            if os.path.islink(path):
                continue
            total_files += 1
            language = _EXT_LANG_MAP.get(os.path.splitext(file)[1].lower(), "Other")
            try:
                lines = _count_lines(path)
            except OSError:
                continue
            total_lines += lines
            language_lines[language] = language_lines.get(language, 0) + lines

    languages = []
    if total_lines > 0:
        for language, lines in language_lines.items():
            percentage = round((lines / total_lines) * 100, 1)
            if percentage > 0:
                languages.append({"name": language, "lines": lines, "percentage": percentage})
        languages.sort(key=lambda entry: entry["percentage"], reverse=True)
    return {"total_files": total_files, "total_lines": total_lines, "languages": languages}
