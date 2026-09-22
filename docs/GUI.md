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

The GUI walks users through the job in order:

1. **Find Jobs** - checks enabled bid sources and ranks likely JTI millwork opportunities.
2. **Start bid from selected job** - automatically creates a named project workspace under the configured JTI bid folder.
3. **Add plans/specs** - users select the files they downloaded; Auto Bid Builder copies them into the correct project folder. ZIP bid packages are unpacked automatically and safely inside the workspace.
4. **Automatic document review** - PDFs are scanned and ranked for millwork/casework/cabinetry and responsibility/exclusion evidence.
5. **Review scope evidence** - the estimator sees the pages to review first and can open the generated `bid_review.md` report.
6. **Build estimate** - the new estimator wizard seeds proposed scope lines from the document review, lets the estimator correct/add/remove scope, enter labor hours by JTI category, materials, markup, tax, manual adds, quantities, and internal evidence references.
7. **Confirm pricing gates** - the app requires explicit confirmation that scope, current labor/pricing rates, and material tax treatment were reviewed. Historical values are shown only as starter information; installation starts at zero because historical installation rates varied by project.
8. **Generate quote preview** - the app writes HTML and PDF quote previews using the same `Qty / Each / Code / Tax Each / Amount` structure seen in JTI quotations. If review gates or pricing are incomplete, the preview is visibly marked **DRAFT - NOT FOR SUBMISSION**.

The estimate is saved as `estimate/estimate_draft.json`. Quote previews are written to `output/quote_preview.html` and `output/quote_preview.pdf`.

Users can reopen an existing project from the **Current Bid** tab. They do not need to know the internal folder layout.

Provider credentials are kept outside the repository in the operating-system credential store via `keyring`; `ABB_*` environment-variable overrides also remain supported for development/managed deployments.

## Pricing behavior

The guided estimate engine currently uses the historical JTI cost-detail evidence already validated in this project as a starter profile:

- historical shop-side categories `E/M/P/A/F/H/S` begin at `$100/hr`,
- `I` (installation) begins at `$0/hr` so the estimator must deliberately set the project-specific rate if installation hours are used,
- material markup starts at the repeatedly observed historical `60%` pattern,
- material tax starts at `0%` and requires review because historical tax rates varied by job/location.

These starter values do **not** represent a claim about JTI's current rates. The app will not report the quote as ready until the estimator confirms the pricing profile and tax treatment.

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
