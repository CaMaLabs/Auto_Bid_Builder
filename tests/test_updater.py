from pathlib import Path
import subprocess

from auto_bid_builder.updater import apply_update, check_for_updates


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def test_check_and_apply_update(tmp_path: Path):
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    app = tmp_path / "app"
    _git(tmp_path, "init", "--bare", str(remote))
    _git(tmp_path, "clone", str(remote), str(seed))
    _git(seed, "config", "user.email", "test@example.com")
    _git(seed, "config", "user.name", "Test")
    (seed / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.1'\n", encoding="utf-8")
    (seed / "value.txt").write_text("one", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "initial")
    branch = _git(seed, "branch", "--show-current")
    _git(seed, "push", "-u", "origin", branch)
    _git(tmp_path, "clone", str(remote), str(app))

    initial = check_for_updates(branch, repo=app)
    assert initial.supported is True
    assert initial.update_available is False

    (seed / "value.txt").write_text("two", encoding="utf-8")
    _git(seed, "add", "value.txt")
    _git(seed, "commit", "-m", "update")
    _git(seed, "push")

    available = check_for_updates(branch, repo=app)
    assert available.update_available is True
    installed = apply_update(branch, repo=app, reinstall=False)
    assert installed.update_available is False
    assert (app / "value.txt").read_text(encoding="utf-8") == "two"


def test_update_refuses_dirty_checkout(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.1'\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    (repo / "dirty.txt").write_text("dirty", encoding="utf-8")
    status = check_for_updates("main", repo=repo)
    # No origin means no update can be installed, but dirty state must still be preserved.
    assert status.dirty is True
