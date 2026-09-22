from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from . import __version__


DEFAULT_REMOTE = "origin"
GITHUB_REPOSITORY = "CaMaLabs/Auto_Bid_Builder"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
PORTABLE_ASSET_NAME = "AutoBidBuilder-portable.zip"
INSTALLER_ASSET_NAME = "JTI_Auto_Bid_Builder_Setup.exe"


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
    mode: str = "git"
    current_version: str | None = None
    remote_version: str | None = None
    download_url: str | None = None
    release_url: str | None = None
    restart_required: bool = False
    relaunch_scheduled: bool = False
    package_kind: str | None = None

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


def _version_tuple(value: str | None) -> tuple[int, ...]:
    if not value:
        return (0,)
    match = re.search(r"(\d+(?:\.\d+){0,3})", value)
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))


def _release_status_from_payload(payload: dict, current_version: str = __version__) -> UpdateStatus:
    tag = str(payload.get("tag_name") or "").lstrip("vV")
    release_url = str(payload.get("html_url") or "") or None
    installer_url = None
    portable_url = None
    for asset in payload.get("assets") or []:
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "") or None
        if name.lower() == INSTALLER_ASSET_NAME.lower():
            installer_url = url
        elif name.lower() == PORTABLE_ASSET_NAME.lower():
            portable_url = url
    if portable_url is None:
        for asset in payload.get("assets") or []:
            name = str(asset.get("name") or "").lower()
            if "portable" in name and name.endswith(".zip"):
                portable_url = str(asset.get("browser_download_url") or "") or None
                break

    # Prefer the normal installer for packaged Windows updates. Inno Setup handles
    # replacing the installed executable much more reliably than trying to overwrite
    # a just-closed PyInstaller one-file executable directly. Portable ZIP remains a
    # fallback for older releases.
    download_url = installer_url or portable_url
    package_kind = "installer" if installer_url else ("portable" if portable_url else None)

    available = _version_tuple(tag) > _version_tuple(current_version)
    if available and download_url:
        message = f"Auto Bid Builder {tag} is available."
    elif available:
        message = f"Auto Bid Builder {tag} is available, but this release does not include an automatic-update package."
    else:
        message = f"Auto Bid Builder {current_version} is up to date."
    return UpdateStatus(
        supported=True,
        update_available=available,
        message=message,
        mode="release",
        current_version=current_version,
        remote_version=tag or None,
        download_url=download_url,
        release_url=release_url,
        package_kind=package_kind,
    )


def _check_release_updates(timeout: int = 20) -> UpdateStatus:
    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={"User-Agent": f"AutoBidBuilder/{__version__}", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return _release_status_from_payload(payload)
    except Exception as exc:
        return UpdateStatus(
            supported=False,
            update_available=False,
            message=f"Could not check the published Auto Bid Builder release: {type(exc).__name__}: {exc}",
            mode="release",
            current_version=__version__,
        )


def _check_git_updates(branch: str = "main", *, repo: Path | None = None) -> UpdateStatus:
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
        mode="git",
        current_version=__version__,
    )


def check_for_updates(branch: str = "main", *, repo: Path | None = None) -> UpdateStatus:
    # Explicit repo is primarily used by tests/development tools and always means
    # Git mode. A frozen Windows build uses published GitHub Release artifacts.
    if repo is not None or not getattr(sys, "frozen", False):
        git_root = repo or repository_root()
        if git_root is not None:
            return _check_git_updates(branch, repo=git_root)
    return _check_release_updates()


def _apply_git_update(branch: str = "main", *, repo: Path | None = None, reinstall: bool = True) -> UpdateStatus:
    status = _check_git_updates(branch, repo=repo)
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

    updated = _check_git_updates(branch, repo=repo_path)
    return UpdateStatus(
        supported=updated.supported,
        update_available=updated.update_available,
        current_commit=updated.current_commit,
        remote_commit=updated.remote_commit,
        branch=updated.branch,
        repo_root=updated.repo_root,
        dirty=updated.dirty,
        message="Update installed. Restart Auto Bid Builder to load the new version.",
        mode="git",
        current_version=__version__,
        restart_required=True,
    )


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _update_log_path() -> Path:
    local = os.getenv("LOCALAPPDATA")
    root = Path(local) / "JTI" / "AutoBidBuilder" if local else Path(tempfile.gettempdir()) / "JTI-AutoBidBuilder"
    root.mkdir(parents=True, exist_ok=True)
    return root / "update.log"


def _build_update_script(*, package: Path, package_kind: str, exe_path: Path, install_dir: Path, pid: int, log_path: Path) -> str:
    common = [
        "$ErrorActionPreference = 'Stop'",
        f"$PidToWait = {pid}",
        f"$Package = {_powershell_quote(str(package))}",
        f"$InstallDir = {_powershell_quote(str(install_dir))}",
        f"$Exe = {_powershell_quote(str(exe_path))}",
        f"$Log = {_powershell_quote(str(log_path))}",
        "function Write-UpdateLog([string]$Message) { Add-Content -LiteralPath $Log -Value ((Get-Date -Format o) + ' ' + $Message) -Encoding UTF8 }",
        "Write-UpdateLog 'Updater helper started.'",
        "try {",
        "  Write-UpdateLog ('Waiting for process ' + $PidToWait + ' to exit.')",
        "  while (Get-Process -Id $PidToWait -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 400 }",
        "  Start-Sleep -Milliseconds 800",
    ]
    if package_kind == "installer":
        common.extend(
            [
                "  Write-UpdateLog 'Launching silent installer.'",
                "  $Args = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CLOSEAPPLICATIONS')",
                "  $Installer = Start-Process -FilePath $Package -ArgumentList $Args -Wait -PassThru",
                "  Write-UpdateLog ('Installer exit code: ' + $Installer.ExitCode)",
                "  if ($Installer.ExitCode -ne 0) { throw ('Installer failed with exit code ' + $Installer.ExitCode) }",
            ]
        )
    else:
        common.extend(
            [
                "  Write-UpdateLog 'Applying portable update package.'",
                "  $Stage = Join-Path ([System.IO.Path]::GetDirectoryName($Package)) 'stage'",
                "  if (Test-Path $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }",
                "  New-Item -ItemType Directory -Path $Stage | Out-Null",
                "  Expand-Archive -LiteralPath $Package -DestinationPath $Stage -Force",
                "  $SourceExe = Join-Path $Stage 'AutoBidBuilder.exe'",
                "  if (-not (Test-Path $SourceExe)) { throw 'Portable package did not contain AutoBidBuilder.exe.' }",
                "  $Copied = $false",
                "  for ($i = 0; $i -lt 20; $i++) {",
                "    try { Copy-Item -LiteralPath $SourceExe -Destination $Exe -Force; $Copied = $true; break }",
                "    catch { Start-Sleep -Milliseconds 500 }",
                "  }",
                "  if (-not $Copied) { throw 'Could not replace AutoBidBuilder.exe after repeated attempts.' }",
            ]
        )
    common.extend(
        [
            "  if (-not (Test-Path $Exe)) { throw 'Installed executable was not found after update.' }",
            "  Write-UpdateLog 'Relaunching Auto Bid Builder.'",
            "  Start-Process -FilePath $Exe",
            "  Write-UpdateLog 'Update completed successfully.'",
            "}",
            "catch {",
            "  Write-UpdateLog ('UPDATE FAILED: ' + $_.Exception.Message)",
            "  if (Test-Path $Exe) {",
            "    try { Start-Process -FilePath $Exe; Write-UpdateLog 'Relaunched existing executable after failure.' } catch { Write-UpdateLog ('Relaunch after failure also failed: ' + $_.Exception.Message) }",
            "  }",
            "}",
            "finally {",
            "  Start-Sleep -Milliseconds 500",
            "  Remove-Item -LiteralPath $Package -Force -ErrorAction SilentlyContinue",
            "}",
        ]
    )
    return "\n".join(common)


def _apply_release_update() -> UpdateStatus:
    status = _check_release_updates()
    if not status.supported:
        raise RuntimeError(status.message)
    if not status.update_available:
        return status
    if not status.download_url:
        raise RuntimeError(status.message + " Open the release page and install it manually.")
    if os.name != "nt":
        raise RuntimeError("Packaged automatic updates are currently supported on Windows only.")

    install_dir = Path(sys.executable).resolve().parent
    exe_path = Path(sys.executable).resolve()
    temp_root = Path(tempfile.mkdtemp(prefix="AutoBidBuilderUpdate-"))
    package_kind = status.package_kind or ("installer" if status.download_url.lower().endswith(".exe") else "portable")
    package_name = INSTALLER_ASSET_NAME if package_kind == "installer" else PORTABLE_ASSET_NAME
    package = temp_root / package_name
    request = urllib.request.Request(status.download_url, headers={"User-Agent": f"AutoBidBuilder/{__version__}"})
    with urllib.request.urlopen(request, timeout=180) as response, package.open("wb") as out:
        shutil.copyfileobj(response, out)
    if package.stat().st_size < 100_000:
        raise RuntimeError("The downloaded update package is unexpectedly small and was not installed.")

    log_path = _update_log_path()
    try:
        log_path.write_text(
            f"Auto Bid Builder {__version__} -> {status.remote_version}\nPackage: {package_kind}\n",
            encoding="utf-8",
        )
    except OSError:
        pass

    script = temp_root / "finish_update.ps1"
    script.write_text(
        _build_update_script(
            package=package,
            package_kind=package_kind,
            exe_path=exe_path,
            install_dir=install_dir,
            pid=os.getpid(),
            log_path=log_path,
        ),
        encoding="utf-8-sig",
    )

    flags = (
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(script),
        ],
        cwd=temp_root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )
    return UpdateStatus(
        supported=True,
        update_available=False,
        message=(
            f"Auto Bid Builder {status.remote_version} is downloaded. The app will close, run the updater, and reopen automatically. "
            f"If Windows blocks the update, details are saved to {log_path}."
        ),
        mode="release",
        current_version=__version__,
        remote_version=status.remote_version,
        release_url=status.release_url,
        restart_required=True,
        relaunch_scheduled=True,
        package_kind=package_kind,
    )


def apply_update(branch: str = "main", *, repo: Path | None = None, reinstall: bool = True) -> UpdateStatus:
    if repo is not None or not getattr(sys, "frozen", False):
        git_root = repo or repository_root()
        if git_root is not None:
            return _apply_git_update(branch, repo=git_root, reinstall=reinstall)
    return _apply_release_update()
