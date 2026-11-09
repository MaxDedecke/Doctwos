"""Begrenzter, lesender Git-Diff zwischen zwei Revisionen einer Git-Quelle für den Chat-Agenten.

Der Agent liest Dateien sonst nur im Zielstand des Worktrees. Für einen Commitvergleich fehlte damit das Vorher:
Geänderte Dateien und Zeilenbereiche (Änderungspaket) zeigen nicht, was entfernt oder umgebaut wurde (Katalogtest
08.11.2026, J11). Hier kommen die Diff-Abschnitte mit alten und neuen Zeilen und der umgebenden Methode aus dem
Hunk-Kopf, begrenzt auf ``max_chars``. Zeilen des Zielstands lassen sich zitieren (``pfad:zeile``).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import core.config as cfg
from doctus_models.database import KnowledgeSource
from services.change_diff import _git_commit, _git_worktree, _safe_diff_path
from sqlalchemy.orm import Session

MAX_CHARS = 14_000
MAX_FILES = 40
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")


def _source(db: Session, project_id: int, source_id: int | None):
    query = db.query(KnowledgeSource).filter(
        KnowledgeSource.project_id == project_id, KnowledgeSource.type.ilike("git")
    )
    if source_id is not None:
        query = query.filter(KnowledgeSource.id == source_id)
    sources = query.order_by(KnowledgeSource.id).limit(2).all()
    if not sources:
        return None, "No matching Git source is available in the current project."
    if source_id is None and len(sources) > 1:
        return None, "source_id is required when the project has multiple Git sources."
    return sources[0], None


# Hunk-Köpfe nennen die umgebende Methode nur mit einem Diff-Treiber je Sprache; Kundenrepositories setzen ihn
# selten. Die eingebauten Treiber und ein Muster für COBOL-Paragraphen und -Sections (ab Spalte 8) kommen deshalb
# über eine eigene Attributdatei, ohne das Repository zu verändern.
_ATTRIBUTES = (
    "*.java diff=java\n*.py diff=python\n*.css diff=css\n*.scss diff=css\n*.html diff=html\n"
    + "".join(f"*.{ext} diff=cobol\n" for ext in ("cbl", "CBL", "cob", "COB", "cpy", "CPY"))
)
_COBOL_FUNCNAME = r"^.{7}([A-Za-z0-9][A-Za-z0-9-]*( SECTION)?)\.[[:space:]]*$"


def _attributes_file() -> str:
    path = Path(tempfile.gettempdir()) / "doctus-diff-attributes"
    if not path.exists() or path.read_text() != _ATTRIBUTES:
        path.write_text(_ATTRIBUTES)
    return str(path)


def _git(worktree: Path, *args: str) -> str | None:
    config = [
        "-c",
        f"core.attributesFile={_attributes_file()}",
        "-c",
        f"diff.cobol.xfuncname={_COBOL_FUNCNAME}",
    ]
    try:
        result = subprocess.run(
            ["git", "-C", str(worktree), *config, *args],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None if result.returncode else result.stdout.decode("utf-8", errors="replace")


def _parse(diff: str) -> list[dict]:
    files: list[dict] = []
    current: dict | None = None
    hunk: dict | None = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            current = {"path": None, "old_path": None, "status": "modified", "hunks": []}
            files.append(current)
            hunk = None
        elif current is None:
            continue
        elif line.startswith("--- "):
            current["old_path"] = None if line[4:] == "/dev/null" else line[6:]
            if line[4:] == "/dev/null":
                current["status"] = "added"
        elif line.startswith("+++ "):
            current["path"] = None if line[4:] == "/dev/null" else line[6:]
            if line[4:] == "/dev/null":
                current["status"] = "deleted"
        elif line.startswith("rename from "):
            current["old_path"], current["status"] = line[12:], "renamed"
        elif line.startswith("rename to "):
            current["path"] = line[10:]
        elif match := _HUNK.match(line):
            old_start, old_count, new_start, new_count, context = match.groups()
            hunk = {
                "old_start": int(old_start),
                "old_lines": int(old_count or 1),
                "new_start": int(new_start),
                "new_lines": int(new_count or 1),
                "context": context.strip() or None,
                "text": [],
            }
            current["hunks"].append(hunk)
        elif hunk is not None and line[:1] in (" ", "+", "-", "\\"):
            hunk["text"].append(line)
    for item in files:
        item["path"] = item["path"] or item["old_path"]
    return files


def commit_diff(
    db: Session,
    *,
    project_id: int,
    base_ref: str,
    head_ref: str,
    source_id: int | None = None,
    file_path: str | None = None,
    max_chars: int = MAX_CHARS,
) -> dict:
    source, error = _source(db, project_id, source_id)
    if error:
        return {"error": error}
    worktree = _git_worktree(Path(getattr(cfg, "REPOS_ROOT", "/repos")).resolve(), source.id)
    if worktree is None:
        return {"error": "The local Git worktree for this source is unavailable."}
    base_commit, error = _git_commit(worktree, base_ref)
    if error:
        return {"error": error}
    head_commit, error = _git_commit(worktree, head_ref)
    if error:
        return {"error": error}
    if file_path is not None and not _safe_diff_path(str(file_path)):
        return {"error": "file_path must be a repository-relative path."}
    paths = ["--", file_path] if file_path else ["--"]
    stat = _git(
        worktree, "diff", "--no-ext-diff", "-M", "--numstat", base_commit, head_commit, *paths
    )
    raw = _git(worktree, "diff", "--no-ext-diff", "-M", "-U4", base_commit, head_commit, *paths)
    if stat is None or raw is None:
        return {"error": "The local Git worktree could not calculate the requested diff."}
    changes = {}
    for row in stat.splitlines():
        added, removed, path = (row.split("\t", 2) + ["", "", ""])[:3]
        changes[path.split(" => ")[-1].rstrip("}")] = (added, removed)
    files = _parse(raw)
    budget, truncated = max_chars, False
    shown = []
    for item in files[:MAX_FILES]:
        added, removed = changes.get(item["path"], ("-", "-"))
        entry = {
            "path": item["path"],
            "old_path": item["old_path"] if item["old_path"] != item["path"] else None,
            "status": item["status"],
            "added_lines": added,
            "removed_lines": removed,
            "hunks": [],
        }
        for hunk in item["hunks"]:
            text = "\n".join(hunk["text"])
            if len(text) > budget:
                truncated = True
                break
            budget -= len(text)
            entry["hunks"].append({**hunk, "text": text})
        entry["hunks_omitted"] = len(item["hunks"]) - len(entry["hunks"])
        shown.append(entry)
    return {
        "status": "ok",
        "source_id": source.id,
        "base_commit": base_commit,
        "head_commit": head_commit,
        "file_count": len(files),
        "files": shown,
        "truncated": truncated or len(files) > MAX_FILES,
        "note": (
            "Zeilen mit '-' stehen nur im Basisstand, mit '+' nur im Zielstand. Zitierbar sind Zeilen des "
            "Zielstands (path:new_start...). Fehlen Abschnitte (truncated/hunks_omitted), file_path angeben."
        ),
    }


def diff_source_ranges(result: dict) -> list[tuple[str, int, int]]:
    """Zeilenbereiche des Zielstands, die ein Diff-Ergebnis zeigt; sie gelten als gelesene Quellen."""
    ranges = []
    for item in result.get("files", [])[:20]:
        for hunk in item.get("hunks", [])[:12]:
            if item.get("path") and hunk.get("new_lines"):
                start = hunk.get("new_start", 1)
                ranges.append((item["path"], start, start + hunk["new_lines"] - 1))
    return ranges
