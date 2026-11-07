"""Werkzeuge des Chat-Agenten auf dem Repository-Worktree: Dateien listen, lesen, durchsuchen, Entitäten."""

import logging
import os
from sqlalchemy import func
from typing import Optional
from doctus_models.database import CodeEntity


logger = logging.getLogger(__name__)


# Securely locate the repository path
def get_repo_root(repo_id: int) -> str:
    """Return the active worktree, with support for repositories from before AP-3."""
    candidates = (
        os.path.abspath(f"/repos/wt/ks_{repo_id}"),
        os.path.abspath(f"/repos/{repo_id}"),
    )
    return next((path for path in candidates if os.path.isdir(path)), candidates[0])


def get_repo_path(repo_id: int, file_path: str = "") -> str:
    base_path = get_repo_root(repo_id)
    if not file_path:
        return base_path
    # Prevent directory traversal.
    target_path = os.path.abspath(os.path.join(base_path, file_path.lstrip("/")))
    if os.path.commonpath((base_path, target_path)) != base_path:
        raise ValueError("Directory traversal attempt detected")
    return target_path


# Local repository tools implementation
_REPOSITORY_IGNORED_DIRS = frozenset(
    {".git", "node_modules", "__pycache__", ".next", "dist", "build"}
)


def _repository_file_paths(repo_id: int, directory: str = "") -> list[str]:
    """Return every visible file below a repository path in stable order."""
    base_dir = get_repo_path(repo_id)
    target_dir = get_repo_path(repo_id, directory)
    if not os.path.isdir(target_dir):
        return []
    paths = []
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [name for name in dirs if name not in _REPOSITORY_IGNORED_DIRS]
        paths.extend(
            os.path.relpath(os.path.join(root, name), base_dir).replace(os.sep, "/")
            for name in files
        )
    return sorted(paths)


def list_repo_files(repo_id: int, directory: str = "") -> dict:
    """Lists files inside the repository recursively or in a subdirectory."""
    try:
        target_dir = get_repo_path(repo_id, directory)
        if not os.path.exists(target_dir):
            return {"error": f"Directory '{directory}' does not exist"}

        binary_or_archive_suffixes = (
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".pdf",
            ".zip",
            ".tar",
            ".gz",
            ".db",
            ".sqlite",
            ".exe",
            ".dll",
            ".so",
        )
        files_list = [
            path
            for path in _repository_file_paths(repo_id, directory)
            if not path.lower().endswith(binary_or_archive_suffixes)
        ]

        truncated = len(files_list) > 250
        return {"files": files_list[:250], "total_files": len(files_list), "truncated": truncated}
    except Exception as e:
        return {"error": str(e)}


def find_repo_files(repo_id: int, target: str) -> list[str]:
    """Find repository files by exact basename/path, independent of directory.

    Eval questions frequently name a file without its full repository path.  A
    directory-local listing can miss it (especially in the COBOL trees), so the
    bootstrap uses this bounded, source-wide lookup first.
    """
    target = str(target or "").replace("\\", "/").lstrip("./")
    basename = os.path.basename(target).lower()
    suffix = target.lower()
    return [
        path
        for path in _repository_file_paths(repo_id)
        if os.path.basename(path).lower() == basename
        and ("/" not in target or path.lower().endswith(suffix))
    ][:40]


def view_repo_file(repo_id: int, file_path: str, start_line: int = 1, end_line: int = 150) -> dict:
    """Reads lines from a file in the repository (1-indexed, inclusive)."""
    try:
        full_path = get_repo_path(repo_id, file_path)
        if not os.path.exists(full_path):
            return {"error": f"File '{file_path}' does not exist"}
        if os.path.isdir(full_path):
            return {"error": f"'{file_path}' is a directory, not a file"}

        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        total_lines = len(lines)
        if total_lines == 0:
            return {
                "file_path": file_path,
                "start_line": 0,
                "end_line": 0,
                "total_lines": 0,
                "content": "",
            }

        start = max(1, min(start_line, total_lines))
        end = max(start, min(end_line, total_lines))

        # Limit to maximum 300 lines to avoid blowing up the context window
        if end - start > 300:
            end = start + 300

        content_lines = lines[start - 1 : end]
        numbered_content = "".join([f"{i + start}: {line}" for i, line in enumerate(content_lines)])

        return {
            "file_path": file_path,
            "start_line": start,
            "end_line": end,
            "total_lines": total_lines,
            "content": numbered_content,
        }
    except Exception as e:
        return {"error": str(e)}


def search_repo_code(repo_id: int, query: str) -> dict:
    """Searches for a string (case-insensitive) inside text files in the repository."""
    try:
        base_dir = get_repo_path(repo_id)
        results = []
        query_lower = query.lower()
        count = 0

        for root, dirs, files in os.walk(base_dir):
            for d in list(dirs):
                if d in (".git", "node_modules", "__pycache__", ".next", "dist", "build"):
                    dirs.remove(d)
            for f in files:
                # Skip binaries
                if f.endswith(
                    (
                        ".png",
                        ".jpg",
                        ".jpeg",
                        ".gif",
                        ".pdf",
                        ".zip",
                        ".tar",
                        ".gz",
                        ".db",
                        ".sqlite",
                        ".exe",
                        ".dll",
                        ".so",
                        ".woff",
                        ".woff2",
                        ".ttf",
                        ".eot",
                    )
                ):
                    continue
                full_file_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_file_path, base_dir)

                try:
                    with open(full_file_path, "r", encoding="utf-8", errors="ignore") as file_obj:
                        for idx, line in enumerate(file_obj):
                            if query_lower in line.lower():
                                results.append(
                                    {"file": rel_path, "line": idx + 1, "match": line.strip()}
                                )
                                count += 1
                                if count >= 80:  # Limit to 80 matches
                                    break
                except Exception:
                    pass
                if count >= 80:
                    break
            if count >= 80:
                break

        return {
            "query": query,
            "matches": results,
            "total_matches": len(results),
            "truncated": count >= 80,
        }
    except Exception as e:
        return {"error": str(e)}


def get_repo_entities(
    project_id: int,
    db_session,
    query: str = "",
    limit: int = 80,
    file_paths: Optional[list[str]] = None,
    entity_names: Optional[list[str]] = None,
) -> dict:
    """Retrieves parsed program symbols/code entities (like classes, functions, etc.) from the DB."""
    try:
        try:
            limit = max(1, min(int(limit), 80))
        except (TypeError, ValueError):
            limit = 80
        db_query = db_session.query(CodeEntity).filter(CodeEntity.project_id == project_id)
        if file_paths:
            db_query = db_query.filter(
                func.lower(CodeEntity.file_path).in_([path.lower() for path in file_paths])
            )
        if entity_names:
            db_query = db_query.filter(
                func.lower(CodeEntity.name).in_([name.lower() for name in entity_names])
            )
        if query:
            db_query = db_query.filter(CodeEntity.name.ilike(f"%{query}%"))

        entities = db_query.limit(limit).all()
        entities_list = [
            {
                "id": e.id,
                "name": e.name,
                "qualified_name": e.qualified_name,
                "type": e.type,
                "file_path": e.file_path,
                "start_line": e.start_line,
                "end_line": e.end_line,
            }
            for e in entities
        ]

        return {"entities": entities_list, "total_entities": len(entities_list)}
    except Exception as e:
        return {"error": str(e)}
