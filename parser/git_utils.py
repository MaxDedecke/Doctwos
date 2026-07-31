"""
parser/git_utils.py
====================
Bare-Mirror- + Worktree-Verwaltung für den Git-Konnektor (AP-3, Plan §7).

Physisches Layout (§7.1):
    /repos/bare/<fingerprint>.git   ein Bare-Mirror je Repo-URL, geteilt über
                                     alle Wissensquellen (Branches) auf demselben Repo
    /repos/wt/ks_<source_id>/       ein Worktree je Wissensquelle (= je Branch)

Ein 100-GB-Monorepo liegt damit einmal auf Platte, egal wie viele Wissensquellen
es mit unterschiedlichen Branches einbinden (F-019). Alle Funktionen hier sind
reine Prozess-/Dateisystem-Operationen ohne DB-Zugriff — der Aufrufer
(connectors/git.py) hält währenddessen den lock:git_fetch:<fingerprint>-Lock,
da mehrere Wissensquellen denselben Bare-Mirror-Pfad teilen können.
"""

import hashlib
import os
import subprocess

# E-3 (docs/ENTSCHEIDUNGEN.md): Partial Clone spart bei der Erstindexierung
# eines Monorepos den Großteil des Transfers, braucht dafür aber dauerhaft
# eine Verbindung zum Git-Server. Deployments, in denen der Server nach der
# Erstindexierung wegfällt (NF-002, abgeschottete Umgebung), schalten auf
# vollständigen Blob-Transfer um.
PARTIAL_CLONE = os.environ.get("DOCTUS_GIT_PARTIAL_CLONE", "1") != "0"


class GitCommandError(RuntimeError):
    """Ein git-Subprozess ist mit einem Fehler zurückgekommen; message = stderr."""


def _run(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise GitCommandError(f"`{' '.join(args)}` fehlgeschlagen: {result.stderr.strip()}")
    return result.stdout


def compute_repo_fingerprint(url: str) -> str:
    """sha1 der normalisierten Repo-URL (klein geschrieben, ohne .git-Suffix,
    ohne abschließenden Slash) — mehrere Wissensquellen mit demselben
    physischen Repo, aber unterschiedlichem Branch, teilen sich denselben
    Bare-Mirror (§7.1)."""
    normalized = (url or "").strip().lower().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def bare_path(repos_root: str, fingerprint: str) -> str:
    return os.path.join(repos_root, "bare", f"{fingerprint}.git")


def worktree_path(repos_root: str, source_id: int) -> str:
    return os.path.join(repos_root, "wt", f"ks_{source_id}")


def ensure_bare_mirror(repos_root: str, fingerprint: str, auth_url: str, log=None) -> str:
    """Legt den Bare-Mirror beim ersten Zugriff an; existiert er bereits, wird
    nur die Remote-URL nachgezogen (z. B. nach Token-Rotation)."""
    path = bare_path(repos_root, fingerprint)
    if os.path.isdir(path):
        _run(["git", "-C", path, "remote", "set-url", "origin", auth_url])
        return path

    os.makedirs(os.path.dirname(path), exist_ok=True)
    if log:
        log("Bare-Mirror wird neu angelegt (clone --bare)…")
    cmd = ["git", "clone", "--bare", "--no-tags"]
    if PARTIAL_CLONE:
        cmd.append("--filter=blob:none")
    cmd += [auth_url, path]
    _run(cmd)
    return path


def fetch_branch(bare: str, branch: str, log=None) -> None:
    """Holt den aktuellen Stand eines Branches und zieht den lokalen Branch-Ref
    refs/heads/<branch> im Bare-Mirror darauf nach (per `branch -f`, siehe
    ensure_worktree() dazu, warum das ohne Konflikt funktioniert).

    Das Plan-Pseudocode (§7.2) setzt Worktrees direkt auf FETCH_HEAD zurück —
    das funktioniert in der Praxis nicht: FETCH_HEAD ist aus einem an den
    Bare-Mirror angehängten Worktree heraus nicht auflösbar (git meldet
    "unknown revision"), auch wenn die Datei im gemeinsamen Gitdir liegt.
    Verifiziert mit einem echten lokalen Repo, keine Doku-Annahme. refs/heads/*
    dagegen sind über alle Worktrees hinweg sichtbar — daher der Umweg über
    einen benannten Ref statt FETCH_HEAD direkt zu referenzieren."""
    if log:
        log(f"Neue Änderungen für Branch '{branch}' werden abgerufen…")
    cmd = ["git", "-C", bare, "fetch"]
    if PARTIAL_CLONE:
        cmd.append("--filter=blob:none")
    cmd += ["origin", branch]
    _run(cmd)
    _run(["git", "-C", bare, "branch", "-f", branch, "FETCH_HEAD"])


def ensure_worktree(bare: str, wt: str, branch: str, sparse_paths: list[str] | None = None, log=None) -> None:
    """Legt den Worktree beim ersten Sync einer Wissensquelle an, immer mit
    losgelöstem HEAD (`--detach`) statt eines benannten Branch-Checkouts.

    Grund: git erlaubt nur EINEN nicht-losgelösten Checkout eines Branches
    gleichzeitig — zwei Wissensquellen aus verschiedenen Projekten dürfen
    denselben Branch desselben Repos referenzieren (F-019 erlaubt das
    ausdrücklich), was mit `worktree add wt <branch>` beim zweiten Worktree
    mit "already checked out" fehlschlagen würde. Zusätzlich blockiert git ein
    späteres `branch -f <branch> FETCH_HEAD` (siehe fetch_branch()), solange
    irgendein Worktree den Branch nicht-losgelöst ausgecheckt hat. Mit
    `--detach` hält kein Worktree je eine exklusive Sperre auf den Branch-Ref,
    beides ist damit über beliebig viele Wissensquellen hinweg konfliktfrei.
    Verifiziert mit einem echten lokalen Repo (zwei Worktrees, ein Branch)."""
    if os.path.isdir(wt):
        return
    os.makedirs(os.path.dirname(wt), exist_ok=True)
    _run(["git", "-C", bare, "worktree", "prune"])
    if log:
        log(f"Worktree für Branch '{branch}' wird angelegt…")
    _run(["git", "-C", bare, "worktree", "add", "--detach", wt, branch])

    if sparse_paths:
        _run(["git", "-C", wt, "sparse-checkout", "init", "--cone"])
        _run(["git", "-C", wt, "sparse-checkout", "set", *sparse_paths])


def reset_worktree_to_branch(wt: str, branch: str) -> None:
    """Delta-Sync (§7.2): der Worktree wird hart auf den zuvor per
    fetch_branch() aktualisierten Branch-Ref zurückgesetzt."""
    _run(["git", "-C", wt, "reset", "--hard", branch])


def current_commit(wt: str) -> str:
    return _run(["git", "-C", wt, "rev-parse", "HEAD"]).strip()


def diff_name_status(wt: str, old_commit: str, new_commit: str) -> list[tuple[str, str]]:
    """Geänderte Pfade zwischen zwei Commits. Umbenennungen werden zu
    Delete+Add aufgelöst, statt eine dritte Statusart durch den gesamten
    Aufrufer durchzureichen — der Inhalt landet unter dem neuen Pfad ohnehin
    frisch chunked/eingebettet."""
    out = _run(["git", "-C", wt, "diff", "--name-status", "-M", old_commit, new_commit])
    changes: list[tuple[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0][0]
        if status == "R":
            changes.append(("D", parts[1]))
            changes.append(("A", parts[2]))
        else:
            changes.append((status, parts[1]))
    return changes


def list_tracked_files(wt: str) -> dict[str, str]:
    """Alle von git verfolgten und tatsächlich materialisierten Dateien mit
    ihrem Blob-SHA (aus dem Index, kein Lesen des Dateiinhalts nötig) —
    Grundlage für den Resume-Check (NF-004). Der Existenz-Check filtert
    Pfade heraus, die zwar im Index stehen, aber außerhalb eines
    Sparse-Checkout-Kegels liegen und daher nicht auf Platte liegen."""
    out = _run(["git", "-C", wt, "ls-files", "-s"])
    result: dict[str, str] = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        sha = meta.split(" ")[1]
        if os.path.exists(os.path.join(wt, path)):
            result[path] = sha
    return result


def blob_content_hash(blob_sha: str) -> str:
    """Kürzt den 40-stelligen Git-Blob-SHA auf 32 Zeichen, damit er in
    SourceScanFile.content_hash (VARCHAR(32), an md5-Länge angelehnt) passt.
    Kein zusätzliches Hashen des Dateiinhalts nötig — git kennt den
    Content-Hash über den Blob-SHA bereits, das Auslesen des Index reicht."""
    return blob_sha[:32]
