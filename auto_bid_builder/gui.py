from __future__ import annotations

import json
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from .opportunities.sync import sync_opportunities
from .settings import AppSettings, ProviderSettings, SecretStore, load_settings, save_settings
from .updater import apply_update, check_for_updates


class AutoBidBuilderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Auto Bid Builder")
        self.geometry("1180x760")
        self.minsize(960, 620)
        self.settings: AppSettings = load_settings()
        self.secrets = SecretStore()
        self._opportunity_rows: dict[str, dict] = {}
        self._selected_provider: ProviderSettings | None = None
        self._provider_secret_vars: dict[str, tk.StringVar] = {}
        self._busy = False

        self._build_ui()
        self.after(250, self._startup_update_check)

    # ---------- shared UI ----------
    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(14, 12, 14, 4))
        header.pack(fill="x")
        ttk.Label(header, text="Auto Bid Builder", font=("Segoe UI", 18, "bold")).pack(side="left")
        self.header_status = tk.StringVar(value="Ready")
        ttk.Label(header, textvariable=self.header_status).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=10)
        self._build_opportunities_tab()
        self._build_sources_tab()
        self._build_updates_tab()

        footer = ttk.Frame(self, padding=(12, 0, 12, 10))
        footer.pack(fill="x")
        self.status = tk.StringVar(value="Ready")
        ttk.Label(footer, textvariable=self.status).pack(side="left")

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        self._busy = busy
        if message:
            self.status.set(message)
            self.header_status.set(message)
        self.sync_button.configure(state="disabled" if busy else "normal")
        self.check_update_button.configure(state="disabled" if busy else "normal")
        self.install_update_button.configure(state="disabled" if busy else "normal")

    def _run_background(self, work, done, *, message: str) -> None:
        if self._busy:
            return
        self._set_busy(True, message)

        def runner() -> None:
            try:
                result = work()
            except Exception as exc:
                self.after(0, lambda: self._background_error(exc))
                return
            self.after(0, lambda: self._background_done(result, done))

        threading.Thread(target=runner, daemon=True).start()

    def _background_error(self, exc: Exception) -> None:
        self._set_busy(False, "Ready")
        messagebox.showerror("Auto Bid Builder", f"{type(exc).__name__}: {exc}")

    def _background_done(self, result, done) -> None:
        self._set_busy(False, "Ready")
        done(result)

    # ---------- opportunities ----------
    def _build_opportunities_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text="Opportunities")

        toolbar = ttk.Frame(tab)
        toolbar.pack(fill="x", pady=(0, 8))
        self.sync_button = ttk.Button(toolbar, text="Sync opportunities", command=self.sync_opportunities)
        self.sync_button.pack(side="left")
        ttk.Button(toolbar, text="Open listing", command=self.open_selected_opportunity).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Start bid", command=self.start_bid).pack(side="left")
        self.opportunity_summary = tk.StringVar(value="No opportunity sync run yet.")
        ttk.Label(toolbar, textvariable=self.opportunity_summary).pack(side="right")

        columns = ("score", "tier", "title", "source", "location", "due")
        self.opp_tree = ttk.Treeview(tab, columns=columns, show="headings", selectmode="browse")
        widths = {"score": 70, "tier": 120, "title": 390, "source": 220, "location": 120, "due": 140}
        headings = {"score": "Score", "tier": "Review", "title": "Project", "source": "Source", "location": "Location", "due": "Bid due"}
        for col in columns:
            self.opp_tree.heading(col, text=headings[col])
            self.opp_tree.column(col, width=widths[col], anchor="w" if col not in {"score"} else "center")
        self.opp_tree.pack(fill="both", expand=True, side="left")
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.opp_tree.yview)
        scroll.pack(fill="y", side="right")
        self.opp_tree.configure(yscrollcommand=scroll.set)
        self.opp_tree.bind("<Double-1>", lambda _e: self.open_selected_opportunity())

    def sync_opportunities(self) -> None:
        self.settings = load_settings()
        self._run_background(
            lambda: sync_opportunities(self.settings, self.secrets),
            self._render_opportunities,
            message="Checking bid sources...",
        )

    def _render_opportunities(self, payload: dict) -> None:
        self.opp_tree.delete(*self.opp_tree.get_children())
        self._opportunity_rows.clear()
        for idx, row in enumerate(payload.get("opportunities", [])):
            opp = row.get("opportunity", {})
            location = ", ".join(x for x in (opp.get("city"), opp.get("state")) if x)
            iid = f"opp-{idx}"
            self._opportunity_rows[iid] = row
            self.opp_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    f"{row.get('score', 0):g}",
                    str(row.get("tier", "")).replace("_", " ").title(),
                    opp.get("title", ""),
                    opp.get("source", ""),
                    location,
                    opp.get("bid_due_date") or "",
                ),
            )
        errors = payload.get("errors", [])
        self.opportunity_summary.set(
            f"{payload.get('total_shown', 0)} shown / {payload.get('total_normalized', 0)} found"
            + (f" • {len(errors)} source warning(s)" if errors else "")
        )
        if errors:
            self.status.set("; ".join(f"{x.get('source')}: {x.get('error')}" for x in errors[:3]))
        else:
            self.status.set("Opportunity sync complete.")

    def _selected_opportunity(self) -> dict | None:
        selected = self.opp_tree.selection()
        return self._opportunity_rows.get(selected[0]) if selected else None

    def open_selected_opportunity(self) -> None:
        row = self._selected_opportunity()
        if not row:
            messagebox.showinfo("Auto Bid Builder", "Select an opportunity first.")
            return
        url = row.get("opportunity", {}).get("url")
        if not url:
            messagebox.showinfo("Auto Bid Builder", "This source did not provide a public listing URL.")
            return
        webbrowser.open(url)

    def start_bid(self) -> None:
        row = self._selected_opportunity()
        if not row:
            messagebox.showinfo("Auto Bid Builder", "Select an opportunity first.")
            return
        folder = filedialog.askdirectory(title="Choose or create a folder for this bid")
        if not folder:
            return
        root = Path(folder)
        root.mkdir(parents=True, exist_ok=True)
        (root / "opportunity.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
        for name in ("bid_docs", "takeoff", "estimate", "output"):
            (root / name).mkdir(exist_ok=True)
        messagebox.showinfo("Auto Bid Builder", f"Bid workspace created at:\n{root}")

    # ---------- settings/providers ----------
    def _build_sources_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text="Sources & Settings")

        general = ttk.LabelFrame(tab, text="Opportunity search", padding=10)
        general.pack(fill="x")
        self.states_var = tk.StringVar(value=",".join(self.settings.preferred_states))
        self.lookback_var = tk.StringVar(value=str(self.settings.lookback_days))
        self.min_score_var = tk.StringVar(value=f"{self.settings.minimum_score:g}")
        ttk.Label(general, text="Preferred states").grid(row=0, column=0, sticky="w")
        ttk.Entry(general, textvariable=self.states_var, width=22).grid(row=1, column=0, sticky="ew", padx=(0, 10))
        ttk.Label(general, text="Lookback days").grid(row=0, column=1, sticky="w")
        ttk.Entry(general, textvariable=self.lookback_var, width=12).grid(row=1, column=1, sticky="w", padx=(0, 10))
        ttk.Label(general, text="Minimum score").grid(row=0, column=2, sticky="w")
        ttk.Entry(general, textvariable=self.min_score_var, width=12).grid(row=1, column=2, sticky="w")
        ttk.Button(general, text="Save", command=self.save_general_settings).grid(row=1, column=3, padx=12)
        general.columnconfigure(0, weight=1)

        area = ttk.Frame(tab)
        area.pack(fill="both", expand=True, pady=(12, 0))
        left = ttk.LabelFrame(area, text="Bid outlets", padding=8)
        left.pack(side="left", fill="y")
        self.provider_list = tk.Listbox(left, width=42, exportselection=False)
        self.provider_list.pack(fill="y", expand=True)
        for provider in self.settings.providers:
            self.provider_list.insert("end", provider.label)
        self.provider_list.bind("<<ListboxSelect>>", self._provider_selected)

        right = ttk.LabelFrame(area, text="Selected outlet", padding=12)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.provider_title = tk.StringVar(value="Select an outlet")
        ttk.Label(right, textvariable=self.provider_title, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        self.provider_notes = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.provider_notes, wraplength=650).pack(anchor="w", pady=(2, 10))
        self.provider_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(right, text="Enabled", variable=self.provider_enabled_var).pack(anchor="w")

        self.provider_base_label = ttk.Label(right, text="Base URL")
        self.provider_base_var = tk.StringVar()
        self.provider_base_entry = ttk.Entry(right, textvariable=self.provider_base_var)
        self.provider_feed_label = ttk.Label(right, text="Feed URL")
        self.provider_feed_var = tk.StringVar()
        self.provider_feed_entry = ttk.Entry(right, textvariable=self.provider_feed_var)
        self.provider_secret_frame = ttk.Frame(right)
        self.provider_secret_frame.pack(fill="x", pady=(8, 0))
        ttk.Button(right, text="Save outlet", command=self.save_provider).pack(anchor="e", pady=(12, 0))

        if self.settings.providers:
            self.provider_list.selection_set(0)
            self._provider_selected()

    def save_general_settings(self) -> None:
        try:
            self.settings.preferred_states = [x.strip().upper() for x in self.states_var.get().split(",") if x.strip()]
            self.settings.lookback_days = max(1, int(self.lookback_var.get()))
            self.settings.minimum_score = float(self.min_score_var.get())
        except ValueError:
            messagebox.showerror("Auto Bid Builder", "Lookback days and minimum score must be numeric.")
            return
        save_settings(self.settings)
        self.status.set("Search settings saved.")

    def _provider_selected(self, _event=None) -> None:
        selection = self.provider_list.curselection()
        if not selection:
            return
        provider = self.settings.providers[selection[0]]
        self._selected_provider = provider
        self.provider_title.set(provider.label)
        self.provider_notes.set(provider.notes)
        self.provider_enabled_var.set(provider.enabled)
        self.provider_base_var.set(provider.base_url)
        self.provider_feed_var.set(provider.feed_url)

        self.provider_base_label.pack_forget(); self.provider_base_entry.pack_forget()
        self.provider_feed_label.pack_forget(); self.provider_feed_entry.pack_forget()
        if provider.kind == "rss":
            self.provider_feed_label.pack(anchor="w", pady=(10, 0)); self.provider_feed_entry.pack(fill="x")
        elif provider.base_url or provider.kind not in {"sam"}:
            self.provider_base_label.pack(anchor="w", pady=(10, 0)); self.provider_base_entry.pack(fill="x")

        for child in self.provider_secret_frame.winfo_children():
            child.destroy()
        self._provider_secret_vars.clear()
        for field_name in provider.credential_fields:
            var = tk.StringVar()
            self._provider_secret_vars[field_name] = var
            configured = "configured" if self.secrets.has(provider.id, field_name) else "not set"
            ttk.Label(self.provider_secret_frame, text=f"{field_name.replace('_', ' ').title()} ({configured})").pack(anchor="w", pady=(6, 0))
            ttk.Entry(self.provider_secret_frame, textvariable=var, show="*").pack(fill="x")

    def save_provider(self) -> None:
        provider = self._selected_provider
        if provider is None:
            return
        provider.enabled = bool(self.provider_enabled_var.get())
        provider.base_url = self.provider_base_var.get().strip()
        provider.feed_url = self.provider_feed_var.get().strip()
        try:
            for field_name, var in self._provider_secret_vars.items():
                value = var.get().strip()
                if value:
                    self.secrets.set(provider.id, field_name, value)
                    var.set("")
        except RuntimeError as exc:
            messagebox.showerror("Credential store", str(exc))
            return
        save_settings(self.settings)
        self._provider_selected()
        self.status.set(f"Saved {provider.label}.")

    # ---------- updates ----------
    def _build_updates_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=16)
        self.notebook.add(tab, text="Updates")

        self.check_updates_var = tk.BooleanVar(value=self.settings.check_updates_on_startup)
        self.auto_update_var = tk.BooleanVar(value=self.settings.auto_update)
        self.update_branch_var = tk.StringVar(value=self.settings.update_branch)
        ttk.Checkbutton(tab, text="Check for updates when Auto Bid Builder starts", variable=self.check_updates_var, command=self.save_update_settings).pack(anchor="w")
        ttk.Checkbutton(tab, text="Automatically install clean fast-forward updates", variable=self.auto_update_var, command=self.save_update_settings).pack(anchor="w", pady=(6, 0))
        row = ttk.Frame(tab); row.pack(fill="x", pady=(12, 0))
        ttk.Label(row, text="Update branch:").pack(side="left")
        ttk.Entry(row, textvariable=self.update_branch_var, width=18).pack(side="left", padx=8)
        ttk.Button(row, text="Save", command=self.save_update_settings).pack(side="left")

        ttk.Separator(tab).pack(fill="x", pady=16)
        self.update_status = tk.StringVar(value="Update status has not been checked yet.")
        ttk.Label(tab, textvariable=self.update_status, wraplength=850).pack(anchor="w")
        buttons = ttk.Frame(tab); buttons.pack(anchor="w", pady=12)
        self.check_update_button = ttk.Button(buttons, text="Check now", command=self.check_updates)
        self.check_update_button.pack(side="left")
        self.install_update_button = ttk.Button(buttons, text="Install update", command=self.install_update)
        self.install_update_button.pack(side="left", padx=8)
        ttk.Label(
            tab,
            text="Automatic updates are intentionally fast-forward only. If local source files have uncommitted changes, the updater refuses to overwrite them.",
            wraplength=850,
        ).pack(anchor="w", pady=(8, 0))

    def save_update_settings(self) -> None:
        self.settings.check_updates_on_startup = bool(self.check_updates_var.get())
        self.settings.auto_update = bool(self.auto_update_var.get())
        self.settings.update_branch = self.update_branch_var.get().strip() or "main"
        save_settings(self.settings)
        self.status.set("Update settings saved.")

    def _startup_update_check(self) -> None:
        if not self.settings.check_updates_on_startup:
            return
        if self.settings.auto_update:
            self._run_background(
                lambda: apply_update(self.settings.update_branch),
                self._update_finished,
                message="Checking for updates...",
            )
        else:
            self.check_updates(silent=True)

    def check_updates(self, silent: bool = False) -> None:
        def done(result) -> None:
            self.update_status.set(result.message)
            if result.update_available and not silent:
                messagebox.showinfo("Update available", result.message)
        self._run_background(
            lambda: check_for_updates(self.settings.update_branch),
            done,
            message="Checking for updates...",
        )

    def install_update(self) -> None:
        if not messagebox.askyesno("Install update", "Install the latest fast-forward update from GitHub? The app will need to restart afterward."):
            return
        self._run_background(
            lambda: apply_update(self.settings.update_branch),
            self._update_finished,
            message="Installing update...",
        )

    def _update_finished(self, result) -> None:
        self.update_status.set(result.message)
        if "installed" in result.message.lower():
            messagebox.showinfo("Update installed", result.message)


def main() -> None:
    app = AutoBidBuilderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
