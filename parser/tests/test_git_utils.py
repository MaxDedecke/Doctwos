"""
Testet parser/git_utils.py gegen echte lokale Git-Repositories (kein Mocking,
kein DB-Zugriff — reine Dateisystem-/Subprozess-Operationen, siehe Docstring
dort). Deckt zwei Fallstricke ab, die beim Umsetzen von Plan §7.2 auffielen
und NICHT aus der Doku ersichtlich waren, sondern nur durch Ausprobieren:

  1. FETCH_HEAD ist aus einem an den Bare-Mirror angehängten Worktree heraus
     nicht auflösbar, obwohl die Datei im gemeinsamen Gitdir liegt.
  2. `git branch -f <branch> ...` schlägt fehl, solange irgendein Worktree
     <branch> nicht-losgelöst ausgecheckt hat — deshalb `--detach` in
     ensure_worktree().
"""

import os
import subprocess

import pytest

import git_utils


def _init_remote(path: str) -> None:
    subprocess.run(["git", "init", "--initial-branch=main", path], check=True, capture_output=True)
    subprocess.run(["git", "-C", path, "config", "user.email", "test@doctus.local"], check=True)
    subprocess.run(["git", "-C", path, "config", "user.name", "Doctus Test"], check=True)


def _commit_file(repo: str, rel_path: str, content: str, message: str) -> None:
    full = os.path.join(repo, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", message], check=True, capture_output=True)


@pytest.fixture
def remote(tmp_path):
    path = str(tmp_path / "remote.git")
    _init_remote(path)
    _commit_file(path, "PROG.CBL", "IDENTIFICATION DIVISION.\n", "init")
    return path


@pytest.fixture
def repos_root(tmp_path):
    return str(tmp_path / "repos")


def test_compute_repo_fingerprint_normalizes_url():
    a = git_utils.compute_repo_fingerprint("https://example.com/Repo.GIT/")
    b = git_utils.compute_repo_fingerprint("https://EXAMPLE.com/Repo")
    assert a == b
    assert len(a) == 40  # sha1 hex


def test_compute_repo_fingerprint_distinguishes_different_urls():
    a = git_utils.compute_repo_fingerprint("https://example.com/repo-a")
    b = git_utils.compute_repo_fingerprint("https://example.com/repo-b")
    assert a != b


def test_remote_default_branch(remote):
    assert git_utils.remote_default_branch(remote) == "main"


def test_partial_clone_falls_back_to_full_clone(tmp_path, monkeypatch):
    calls = []

    def fake_run(args):
        calls.append(args)
        if "--filter=blob:none" in args:
            raise git_utils.GitCommandError("server does not support filter")
        return ""

    monkeypatch.setattr(git_utils, "_run", fake_run)
    monkeypatch.setattr(git_utils, "PARTIAL_CLONE", True)

    fingerprint = git_utils.compute_repo_fingerprint("https://github.com/acme/repo.git")
    git_utils.ensure_bare_mirror(str(tmp_path), fingerprint, "https://github.com/acme/repo.git")

    assert calls[0][0:4] == ["git", "clone", "--bare", "--no-tags"]
    assert "--filter=blob:none" in calls[0]
    assert calls[1] == [
        "git", "clone", "--bare", "--no-tags", "https://github.com/acme/repo.git",
        git_utils.bare_path(str(tmp_path), fingerprint),
    ]


def test_partial_fetch_falls_back_to_unfiltered_fetch(monkeypatch):
    calls = []

    def fake_run(args):
        calls.append(args)
        if "--filter=blob:none" in args:
            raise git_utils.GitCommandError("remote does not support filter")
        return ""

    monkeypatch.setattr(git_utils, "_run", fake_run)
    monkeypatch.setattr(git_utils, "PARTIAL_CLONE", True)

    git_utils.fetch_branch("/repos/bare/repo.git", "main")

    assert calls[0] == ["git", "-C", "/repos/bare/repo.git", "fetch", "--filter=blob:none", "origin", "main"]
    assert calls[1] == ["git", "-C", "/repos/bare/repo.git", "fetch", "origin", "main"]
    assert calls[2] == ["git", "-C", "/repos/bare/repo.git", "branch", "-f", "main", "FETCH_HEAD"]


def test_ensure_bare_mirror_clone_then_reuse(remote, repos_root):
    fp = git_utils.compute_repo_fingerprint(remote)
    bare1 = git_utils.ensure_bare_mirror(repos_root, fp, remote)
    assert os.path.isdir(bare1)
    # Zweiter Aufruf mit demselben Fingerprint darf klonen NICHT wiederholen,
    # sondern nur die Remote-URL aktualisieren (idempotent, Bare-Store bleibt).
    bare2 = git_utils.ensure_bare_mirror(repos_root, fp, remote)
    assert bare1 == bare2


def test_worktree_survives_delta_sync(remote, repos_root):
    fp = git_utils.compute_repo_fingerprint(remote)
    bare = git_utils.ensure_bare_mirror(repos_root, fp, remote)
    git_utils.fetch_branch(bare, "main")
    wt = git_utils.worktree_path(repos_root, 1)
    git_utils.ensure_worktree(bare, wt, "main")

    c1 = git_utils.current_commit(wt)
    assert git_utils.list_tracked_files(wt) == {
        "PROG.CBL": subprocess.run(
            ["git", "-C", wt, "rev-parse", "HEAD:PROG.CBL"], capture_output=True, text=True
        ).stdout.strip()
    }

    _commit_file(remote, "PROG.CBL", "IDENTIFICATION DIVISION.\nMORE.\n", "update")
    git_utils.fetch_branch(bare, "main")
    git_utils.reset_worktree_to_branch(wt, "main")
    c2 = git_utils.current_commit(wt)

    assert c2 != c1
    assert git_utils.diff_name_status(wt, c1, c2) == [("M", "PROG.CBL")]


def test_rename_resolves_to_delete_plus_add(remote, repos_root):
    fp = git_utils.compute_repo_fingerprint(remote)
    bare = git_utils.ensure_bare_mirror(repos_root, fp, remote)
    git_utils.fetch_branch(bare, "main")
    wt = git_utils.worktree_path(repos_root, 1)
    git_utils.ensure_worktree(bare, wt, "main")
    c1 = git_utils.current_commit(wt)

    subprocess.run(["git", "-C", remote, "mv", "PROG.CBL", "RENAMED.CBL"], check=True, capture_output=True)
    subprocess.run(["git", "-C", remote, "commit", "-m", "rename"], check=True, capture_output=True)
    git_utils.fetch_branch(bare, "main")
    git_utils.reset_worktree_to_branch(wt, "main")
    c2 = git_utils.current_commit(wt)

    assert set(git_utils.diff_name_status(wt, c1, c2)) == {("D", "PROG.CBL"), ("A", "RENAMED.CBL")}


def test_multiple_sources_share_bare_mirror_different_branches(remote, repos_root):
    """Zwei Wissensquellen auf demselben Repo, aber verschiedenen Branches,
    teilen sich den Bare-Mirror und bleiben inhaltlich isoliert (§7.1/F-019)."""
    fp = git_utils.compute_repo_fingerprint(remote)
    bare = git_utils.ensure_bare_mirror(repos_root, fp, remote)
    git_utils.fetch_branch(bare, "main")
    wt_main = git_utils.worktree_path(repos_root, 1)
    git_utils.ensure_worktree(bare, wt_main, "main")

    subprocess.run(["git", "-C", remote, "checkout", "-b", "dev"], check=True, capture_output=True)
    _commit_file(remote, "DEV.CBL", "DEV.\n", "dev branch")

    bare2 = git_utils.ensure_bare_mirror(repos_root, fp, remote)
    assert bare2 == bare
    git_utils.fetch_branch(bare, "dev")
    wt_dev = git_utils.worktree_path(repos_root, 2)
    git_utils.ensure_worktree(bare, wt_dev, "dev")

    assert set(os.listdir(wt_main)) - {".git"} == {"PROG.CBL"}
    assert set(os.listdir(wt_dev)) - {".git"} == {"PROG.CBL", "DEV.CBL"}


def test_multiple_sources_share_same_branch(remote, repos_root):
    """Zwei Wissensquellen (z.B. verschiedene Projekte) dürfen denselben
    Branch desselben Repos referenzieren — git lässt normalerweise nur einen
    nicht-losgelösten Checkout eines Branches zu, ensure_worktree() umgeht das
    über --detach (siehe Docstring dort)."""
    fp = git_utils.compute_repo_fingerprint(remote)
    bare = git_utils.ensure_bare_mirror(repos_root, fp, remote)
    git_utils.fetch_branch(bare, "main")

    wt_a = git_utils.worktree_path(repos_root, 1)
    wt_b = git_utils.worktree_path(repos_root, 2)
    git_utils.ensure_worktree(bare, wt_a, "main")
    git_utils.ensure_worktree(bare, wt_b, "main")  # darf nicht fehlschlagen

    _commit_file(remote, "PROG.CBL", "IDENTIFICATION DIVISION.\nMORE.\n", "update")
    # branch -f (in fetch_branch) darf nicht an einem "checked out"-Konflikt
    # scheitern, obwohl zwei Worktrees denselben Branch referenzieren.
    git_utils.fetch_branch(bare, "main")
    git_utils.reset_worktree_to_branch(wt_a, "main")
    git_utils.reset_worktree_to_branch(wt_b, "main")
    assert git_utils.current_commit(wt_a) == git_utils.current_commit(wt_b)


def test_sparse_checkout_cone_mode(remote, repos_root):
    """Cone-Modus hält Top-Level-Dateien immer vor, unabhängig von
    sparse_paths — nur nicht gelistete Unterverzeichnisse werden ausgelassen."""
    subprocess.run(["git", "-C", remote, "checkout", "main"], check=True, capture_output=True)
    _commit_file(remote, "sub/X.CBL", "X.\n", "add sub/X.CBL")
    _commit_file(remote, "sub2/Y.CBL", "Y.\n", "add sub2/Y.CBL")

    fp = git_utils.compute_repo_fingerprint(remote)
    bare = git_utils.ensure_bare_mirror(repos_root, fp, remote)
    git_utils.fetch_branch(bare, "main")
    wt = git_utils.worktree_path(repos_root, 1)
    git_utils.ensure_worktree(bare, wt, "main", sparse_paths=["sub"])

    present = set(os.listdir(wt)) - {".git"}
    assert "sub" in present
    assert "sub2" not in present
    assert "PROG.CBL" in present  # Top-Level-Datei bleibt trotz sparse_paths

    tracked = git_utils.list_tracked_files(wt)
    assert "sub/X.CBL" in tracked
    assert "sub2/Y.CBL" not in tracked


def test_blob_content_hash_fits_varchar32():
    sha = "a" * 40
    hashed = git_utils.blob_content_hash(sha)
    assert len(hashed) == 32
    assert hashed == "a" * 32


def test_fetch_branch_missing_branch_raises(remote, repos_root):
    fp = git_utils.compute_repo_fingerprint(remote)
    bare = git_utils.ensure_bare_mirror(repos_root, fp, remote)
    with pytest.raises(git_utils.GitCommandError):
        git_utils.fetch_branch(bare, "does-not-exist")
