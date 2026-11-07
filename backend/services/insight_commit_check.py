"""Bounded, read-only comparison of finding evidence with local Git commits."""

import subprocess
from pathlib import Path
from time import monotonic

from sqlalchemy import cast, or_, and_, func
from sqlalchemy.dialects.postgresql import JSONB

import core.config as cfg
from doctus_models.database import Insight, KnowledgeSource
from doctus_models.insight_versions import capture_versions, version_state
from services.change_diff import _git_commit, _git_worktree, _safe_diff_path

MAX_PATHS = 150
MAX_OUTPUT = 64000


def _git(worktree, *args):
    try:
        result = subprocess.run(
            ["git", "--literal-pathspecs", "-C", str(worktree), *args],
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Git-Prüfung konnte nicht abgeschlossen werden") from exc
    if result.returncode:
        raise ValueError("Git-Version oder Belegdatei ist lokal nicht verfügbar")
    if len(result.stdout) > MAX_OUTPUT:
        raise ValueError("Git-Ergebnis überschreitet das Prüflimit")
    return result.stdout


def _preview(worktree, base, target, path):
    # Inspect object sizes before reading source text or a textual diff.
    try:
        for commit in (base, target):
            result = subprocess.run(
                ["git", "-C", str(worktree), "cat-file", "-s", f"{commit}:{path}"],
                capture_output=True,
                timeout=3,
                check=False,
            )
            if result.returncode == 0 and int(result.stdout) > 24000:
                return {"text": "", "truncated": True}
        content = _git(
            worktree,
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            "--unified=3",
            base,
            target,
            "--",
            path,
        ).decode("utf-8", errors="replace")
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return {"text": "", "truncated": True}
    return {"text": content[:6000], "truncated": len(content) > 6000}


def _compare(worktree, binding, target):
    base, error = _git_commit(worktree, binding.get("commit"))
    if error:
        return {"result": "unknown", "reason": "base_unavailable", "files": []}
    paths = sorted(set(binding.get("files", []) + binding.get("dependency_files", [])))
    if not paths or len(paths) > MAX_PATHS or any(not _safe_diff_path(p) for p in paths):
        return {"result": "unknown", "reason": "missing_or_unbounded_evidence", "files": []}
    try:
        raw = (
            _git(
                worktree,
                "diff",
                "--name-status",
                "-z",
                "--no-renames",
                "--no-ext-diff",
                base,
                target,
                "--",
                *paths,
            )
            .decode("utf-8", errors="replace")
            .split("\0")
        )
        # An absent path at both revisions cannot establish unchanged evidence.
        present = (
            _git(worktree, "ls-tree", "-r", "--name-only", "-z", base, "--", *binding["files"])
            .decode("utf-8", errors="replace")
            .split("\0")
        )
        if not set(binding["files"]).issubset(set(present)):
            raise ValueError("Belegdatei fehlt in der freigegebenen Revision")
    except ValueError:
        return {"result": "unknown", "reason": "evidence_unavailable", "files": []}
    changed = [
        {
            "change": raw[i],
            "file": raw[i + 1],
            "kind": "evidence" if raw[i + 1] in binding["files"] else "dependency",
        }
        for i in range(0, len(raw) - 1, 2)
    ]
    for item in changed[:3]:
        item["diff"] = _preview(worktree, base, target, item["file"])
    if not changed and binding.get("dependencies_truncated"):
        return {"result": "unknown", "reason": "dependency_limit", "base_commit": base, "files": []}
    return {
        "result": "needs_review" if changed else "evidence_unchanged",
        "reason": "files_changed" if changed else "files_unchanged",
        "base_commit": base,
        "files": changed,
        "dependencies_truncated": binding.get("dependencies_truncated", False),
    }


def check_commit(db, project_id, source_id, target_ref, *, after_id=0, limit=25):
    source = db.query(KnowledgeSource).filter_by(id=source_id, project_id=project_id).first()
    if not source or (source.type or "").lower() != "git":
        raise ValueError("Git-Quelle gehört nicht zum Projekt")
    worktree = _git_worktree(Path(cfg.REPOS_ROOT).resolve(), source_id)
    if not worktree:
        raise ValueError("Lokaler Git-Worktree ist nicht verfügbar")
    target, error = _git_commit(worktree, target_ref)
    if error:
        raise ValueError(error)
    bound_json = cast(Insight.version_bindings, JSONB)
    evidence_json = cast(Insight.evidence_json, JSONB)
    insights = (
        db.query(Insight)
        .filter(
            Insight.project_id == project_id,
            Insight.id > after_id,
            or_(
                bound_json.contains([{"source_id": source_id}]),
                evidence_json.contains([{"source_id": source_id}]),
                and_(
                    Insight.version_bindings.is_(None),
                    ~func.jsonb_path_exists(evidence_json, "$[*].source_id"),
                ),
            ),
        )
        .order_by(Insight.id)
        .limit(limit + 1)
        .all()
    )
    rows, started = [], monotonic()
    target_indexed = (
        source.sync_status == "completed"
        and (source.sync_cursor or {}).get("last_commit") == target
    )
    for insight in insights[:limit]:
        if rows and monotonic() - started > 4:
            break
        binding = next(
            (b for b in insight.version_bindings or [] if b["source_id"] == source_id), None
        )
        comparison = (
            _compare(worktree, binding, target)
            if binding and binding.get("commit")
            else {
                "result": "unknown",
                "reason": "unbound",
                "files": [],
            }
        )
        current = capture_versions(db, project_id, insight.evidence_json)
        state = version_state(db, insight, current)
        if (
            target_indexed
            and binding
            and state == "different_version"
            and comparison["result"] == "evidence_unchanged"
        ):
            comparison["reason"] = "version_changed"
        current_binding = next((b for b in current if b["source_id"] == source_id), None)
        if (
            target_indexed
            and binding
            and current_binding
            and binding.get("analysis_context") != current_binding.get("analysis_context")
        ):
            comparison["result"] = "needs_review"
            comparison["reason"] = "analysis_changed"
        rows.append(
            {
                "id": insight.id,
                "title": insight.title,
                "content": insight.content,
                "status": insight.status,
                "revision": insight.revision,
                "created_by_id": insight.created_by_id,
                "version_bindings": insight.version_bindings,
                "current_versions": current,
                "version_state": state,
                "evidence": insight.evidence_json,
                "can_verify": bool(current)
                and target_indexed
                and state != "index_unavailable"
                and insight.status != "rejected"
                and (insight.status != "verified" or state != "current"),
                **comparison,
            }
        )
    more = len(insights) > len(rows)
    return {
        "source_id": source.id,
        "source_name": source.name,
        "branch": source.branch,
        "target_commit": target,
        "target_indexed": target_indexed,
        "items": rows,
        "next_cursor": rows[-1]["id"] if more and rows else None,
        "truncated": more,
        "limitations": [
            "Evidence comparison does not establish semantic correctness.",
            "Dependency paths reflect resolved relationships at capture time.",
            "Unindexed target commits require synchronization before approval.",
        ],
    }
