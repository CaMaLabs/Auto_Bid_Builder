# Desktop GUI

Auto Bid Builder is intended to be usable by JTI staff without requiring Git, API, or Python knowledge during normal use.

## Recommended Windows install

The normal JTI install is the versioned GitHub Release installer:

```text
JTI_Auto_Bid_Builder_Setup.exe
```

It is built automatically by the Windows release workflow. The installer is per-user, does not require Python or Git, installs under `%LOCALAPPDATA%\JTI\AutoBidBuilder`, creates Start Menu and Desktop shortcuts, and can launch Auto Bid Builder when setup finishes.

The current installer is not code-signed yet, so Windows may show a publisher/SmartScreen warning until JTI/CaMaLabs adds a signing certificate. Do not work around enterprise security policy; sign the release before broad managed deployment if JTI requires trusted-publisher installation.

A PowerShell development/fallback installer remains available at `tools/install_windows.ps1`, but normal users should receive the packaged setup EXE instead.

## First launch

The first launch opens a plain-language setup guide. Users can start with the anonymous/public sources, add JTI's paid bid-service credentials later, choose where bid folders are stored, and turn on automatic updates.

The default bid location is:

```text
%USERPROFILE%\Documents\JTI Bids
```

It can be changed in **Sources & Settings**.

## User workflow

The GUI deliberately walks users through the job in order:

1. **Find Jobs** - checks all enabled bid sources and ranks likely JTI millwork opportunities.
2. **Start bid from selected job** - automatically creates a named project workspace under the configured JTI bid folder.
3. **Add plans/specs** - users select the files they downloaded; Auto Bid Builder copies them into the correct project folder. ZIP bid packages are unpacked automatically and safely inside the workspace.
4. **Automatic document review** - PDFs are scanned and ranked for millwork/casework/cabinetry and responsibility/exclusion evidence.
5. **Current Bid** - the estimator sees the pages to review first and can open the generated `bid_review.md` evidence report.
6. **Estimate / quote** - the workspace already contains dedicated `takeoff`, `estimate`, and `output` folders so the calibrated estimating and quote-generation stages can plug into the same guided project.

Users can reopen an existing project from the **Current Bid** tab. They do not need to know the internal folder layout.

Provider credentials are kept outside the repository in the operating-system credential store via `keyring`; `ABB_*` environment-variable overrides also remain supported for development/managed deployments.

## Updates

Packaged Windows builds check the latest versioned GitHub Release. When automatic update is enabled, Auto Bid Builder downloads the portable release package to a temporary folder, closes itself, replaces the executable after the process exits, and reopens automatically. Because the application installs under the current user's Local AppData folder, this does not require administrator access.

Developer Git checkouts keep the existing conservative update path:

1. check `origin/<configured branch>`,
2. refuse to overwrite uncommitted local changes,
3. use a fast-forward-only merge,
4. refresh the editable Python installation, and
5. require a restart to load the new code.

## Release build

`.github/workflows/windows-release.yml` runs the test suite on Windows, builds `AutoBidBuilder.exe` with PyInstaller, creates `AutoBidBuilder-portable.zip` for in-app updates, builds `JTI_Auto_Bid_Builder_Setup.exe` with Inno Setup, uploads the build artifact, and publishes the versioned release assets.

The package version in `pyproject.toml` and `auto_bid_builder/__init__.py` must remain synchronized. A version bump is what tells already-installed packaged clients that a new release is available.

## Development install

From the repository root:

```powershell
python -m pip install -e .
auto-bid-gui
```

The legacy PowerShell uninstall helper is still available for the development-style install. Packaged users should uninstall **JTI Auto Bid Builder** through Windows Installed Apps / Apps & Features.
