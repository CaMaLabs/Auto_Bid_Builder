# Desktop GUI

Install or refresh the local editable installation from the repository root:

```powershell
python -m pip install -e .
```

Launch the desktop application:

```powershell
auto-bid-gui
```

The GUI currently includes:

- **Opportunities** - sync all enabled bid sources, review JTI-fit score/tier, open the source listing, and create a local bid workspace.
- **Sources & Settings** - configure preferred states, lookback period, triage threshold, public feeds, and credentials/API keys for commercial bid outlets.
- **Updates** - check GitHub for a newer `main` revision, install a fast-forward update, and configure startup checks or automatic updates.

Provider credentials are kept outside the repository in the operating-system credential store via `keyring`; `ABB_*` environment-variable overrides also remain supported.

## Update safety

The updater is deliberately conservative:

1. It checks `origin/<configured branch>` for a newer commit.
2. If the checkout contains uncommitted changes, automatic update is refused.
3. Updates use `git fetch` plus a **fast-forward-only** merge. The updater never force-resets local work.
4. After a successful update it refreshes the editable Python installation with the same Python interpreter that launched the app.
5. The running GUI should be restarted after an update so the newly installed code is loaded.

This updater targets the current Git checkout/developer-style installation. A future packaged Windows `.exe` should use signed versioned release artifacts rather than editing its own executable in place.
