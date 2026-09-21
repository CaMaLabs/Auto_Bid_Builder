# Desktop GUI

Auto Bid Builder is intended to be usable by JTI staff without requiring Git, API, or Python knowledge during normal use.

## Recommended Windows install

From PowerShell, run the included guided installer from a downloaded/cloned copy of the repository:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\install_windows.ps1
```

The installer:

1. checks for Git and Python,
2. offers to install missing prerequisites through `winget` when available,
3. installs Auto Bid Builder under `%LOCALAPPDATA%\JTI\AutoBidBuilder`,
4. installs Python dependencies,
5. creates Desktop and Start Menu shortcuts, and
6. launches the app.

The first launch opens a plain-language setup guide. Users can start with the anonymous/public sources, add JTI's paid bid-service credentials later, and optionally turn on automatic safe updates.

For development installs from the repository root:

```powershell
python -m pip install -e .
auto-bid-gui
```

## User workflow

The GUI deliberately uses a small number of actions:

- **Find jobs now** - checks all enabled bid sources and ranks likely JTI millwork opportunities.
- **Open original listing** - opens the source opportunity for human review.
- **Start bid from selected job** - creates the project workspace and tells the user where to put plans/specs.
- **Sources & Settings** - enables bid outlets and stores provider credentials outside the repository.
- **Updates** - checks for and installs safe application updates.
- **Getting started** - can be reopened at any time from the top of the application.

The first-run guide explains the normal workflow as: find jobs → review a project → start the bid.

Provider credentials are kept outside the repository in the operating-system credential store via `keyring`; `ABB_*` environment-variable overrides also remain supported.

## Update safety

The updater is deliberately conservative:

1. It checks `origin/<configured branch>` for a newer commit.
2. If the checkout contains uncommitted changes, automatic update is refused.
3. Updates use `git fetch` plus a **fast-forward-only** merge. The updater never force-resets local work.
4. After a successful update it refreshes the editable Python installation with the same Python interpreter that launched the app.
5. The running GUI should be restarted after an update so the newly installed code is loaded.

Normal JTI users should not need to touch Git. If an update cannot be installed safely, the GUI reports the problem instead of overwriting local files.

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\uninstall_windows.ps1
```

The uninstaller removes the app and shortcuts, but deliberately leaves Python, Git, and project/bid folders in place.

A later packaged Windows `.exe` should use signed/versioned release artifacts rather than editing its own executable in place. The current guided installer is the bridge to that packaging stage.
