from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import shutil
import subprocess
import sys


DEFAULT_REMOTE = "origin"


@dataclass(frozen=True)
class UpdateStatus:
    supported: bool
    update_available: bool
    current_commit: str | None = None
    remote_commit: str | None = None
    branch: str = "main"
    repo_root: str | None = None
    dirty: bool = False
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def repository_root(start: Path | None = None) -> Path | None:
    start = (start or Path(__file__).resolve()).resolve()
    candidates = [start] + list(start.parents)
    for path in candidates:
        base = path if path.is_dir() else path.parent
        if (base / ".git").exists() and (base / "pyproject.toml").exists():
            return base
    return None


def _run(repo: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def check_for_updates(branch: str = "main", *, repo: Path | None = None) -> UpdateStatus:
    repo = repo or repository_root()
    if repo is None:
        return UpdateStatus(False, False, branch=branch, message="This installation is not a Git checkout.")
    if not shutil.which("git"):
        return UpdateStatus(False, False, branch=branch, repo_root=str(repo), message="Git is not installed or not on PATH.")

    current = _run(repo, "git", "rev-parse", "HEAD")
    if current.returncode != 0:
        return UpdateStatus(False, False, branch=branch, repo_root=str(repo), message=current.stderr.strip() or "Unable to read current revision.")
    current_sha = current.stdout.strip()

    dirty_result = _run(repo, "git", "status", "--porcelain")
    dirty = bool(dirty_result.stdout.strip()) if dirty_result.returncode == 0 else True

    remote = _run(repo, "git", "ls-remote", DEFAULT_REMOTE, f"refs/heads/{branch}")
    if remote.returncode != 0 or not remote.stdout.strip():
        return UpdateStatus(
            True,
            False,
            current_commit=current_sha,
            branch=branch,
            repo_root=str(repo),
            dirty=dirty,
            message=remote.stderr.strip() or f"Unable to find {DEFAULT_REMOTE}/{branch}.",
        )
    remote_sha = remote.stdout.split()[0]
    available = current_sha != remote_sha
    message = "Update available." if available else "Auto Bid Builder is up to date."
    if dirty:
        message += " Local uncommitted changes are present; automatic update is disabled until they are saved or reverted."
    return UpdateStatus(
        True,
        available,
        current_commit=current_sha,
        remote_commit=remote_sha,
        branch=branch,
        repo_root=str(repo),
        dirty=dirty,
        message=message,
    )


def apply_update(branch: str = "main", *, repo: Path | None = None, reinstall: bool = True) -> UpdateStatus:
    status = check_for_updates(branch, repo=repo)
    if not status.supported:
        raise RuntimeError(status.message)
    repo_path = Path(status.repo_root or "")
    if status.dirty:
        raise RuntimeError("Automatic update refused because the repository has uncommitted local changes.")
    if not status.update_available:
        return status

    fetch = _run(repo_path, "git", "fetch", DEFAULT_REMOTE, branch, timeout=90)
    if fetch.returncode != 0:
        raise RuntimeError(fetch.stderr.strip() or "git fetch failed")
    merge = _run(repo_path, "git", "merge", "--ff-only", f"{DEFAULT_REMOTE}/{branch}", timeout=90)
    if merge.returncode != 0:
        raise RuntimeError(merge.stderr.strip() or "Fast-forward update failed")

    if reinstall:
        install = _run(repo_path, sys.executable, "-m", "pip", "install", "-e", ".", timeout=180)
        if install.returncode != 0:
            raise RuntimeError(install.stderr.strip() or "Package refresh failed after update")

    updated = check_for_updates(branch, repo=repo_path)
    return UpdateStatus(
        supported=updated.supported,
        update_available=updated.update_available,
        current_commit=updated.current_commit,
        remote_commit=updated.remote_commit,
        branch=updated.branch,
        repo_root=updated.repo_root,
        dirty=updated.dirty,
        message="Update installed. Restart Auto Bid Builder to load the new version.",
    )
