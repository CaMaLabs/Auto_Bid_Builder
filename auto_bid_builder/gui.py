from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from .bid_workspace import add_documents, analyze_workspace, create_workspace, workspace_status
from .estimate.draft import load_estimate
from .estimate.wizard import launch_estimator
from .opportunities.sync import sync_opportunities
from .settings import AppSettings, ProviderSettings, SecretStore, load_settings, save_settings
from .updater import apply_update, check_for_updates


class AutoBidBuilderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Auto Bid Builder")
        self.geometry("1240x820")
        self.minsize(1000, 680)
        self.settings: AppSettings = load_settings()
        self.secrets = SecretStore()
        self._opportunity_rows: dict[str, dict] = {}
        self._selected_provider: ProviderSettings | None = None
        self._provider_secret_vars: dict[str, tk.StringVar] = {}
        self._busy = False
        self.current_workspace: Path | None = None

        self._build_ui()
        self.after(350, self._maybe_show_onboarding)
        self.after(900, self._startup_update_check)

    # ---------- shared UI ----------
    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(14, 12, 14, 4))
        header.pack(fill="x")
        ttk.Label(header, text="Auto Bid Builder", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Button(header, text="Getting started", command=self.show_onboarding).pack(side="right", padx=(8, 0))
        self.header_status = tk.StringVar(value="Ready")
        ttk.Label(header, textvariable=self.header_status).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=10)
        self._build_opportunities_tab()
        self._build_current_bid_tab()
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
        for button_name in (
            "sync_button",
            "check_update_button",
            "install_update_button",
            "analyze_bid_button",
            "add_docs_button",
            "estimate_button",
        ):
            button = getattr(self, button_name, None)
            if button is not None:
                button.configure(state="disabled" if busy else "normal")

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
        messagebox.showerror(
            "Auto Bid Builder",
            f"Something went wrong:\n\n{type(exc).__name__}: {exc}\n\nYou can keep using the app. Try again or check Sources & Settings.",
        )

    def _background_done(self, result, done) -> None:
        self._set_busy(False, "Ready")
        done(result)

    def _open_path(self, path: Path) -> None:
        path = path.resolve()
        try:
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            webbrowser.open(path.as_uri())

    # ---------- onboarding ----------
    def _maybe_show_onboarding(self) -> None:
        if not self.settings.onboarding_complete:
            self.show_onboarding(first_run=True)

    def show_onboarding(self, first_run: bool = False) -> None:
        win = tk.Toplevel(self)
        win.title("Welcome to Auto Bid Builder")
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)
        outer = ttk.Frame(win, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Welcome to Auto Bid Builder", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="The app walks JTI staff from finding work through document review, estimate review, and a quote preview. Public job sources work without a login; company bid-service accounts can be added later.",
            wraplength=700,
        ).pack(anchor="w", pady=(6, 14))

        steps = ttk.LabelFrame(outer, text="Normal workflow", padding=12)
        steps.pack(fill="x")
        for number, title, body in (
            ("1", "Find jobs", "Check enabled bid sources and rank likely JTI millwork opportunities."),
            ("2", "Start a bid", "The app creates and manages a project folder automatically."),
            ("3", "Add plans/specs", "Choose the bid documents and let the app review PDFs for likely scope."),
            ("4", "Review scope", "Open the highest-priority drawing/spec pages and correct the proposed scope."),
            ("5", "Build estimate", "Enter labor/materials, confirm current pricing and tax treatment, then generate a JTI-style quote preview."),
        ):
            row = ttk.Frame(steps)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=number, font=("Segoe UI", 12, "bold"), width=3).pack(side="left", anchor="n")
            text = ttk.Frame(row)
            text.pack(side="left", fill="x", expand=True)
            ttk.Label(text, text=title, font=("Segoe UI", 10, "bold")).pack(anchor="w")
            ttk.Label(text, text=body, wraplength=610).pack(anchor="w")

        prefs = ttk.LabelFrame(outer, text="Recommended starting setup", padding=12)
        prefs.pack(fill="x", pady=(12, 0))
        states_var = tk.StringVar(value=",".join(self.settings.preferred_states or ["CA", "NV"]))
        auto_updates_var = tk.BooleanVar(value=True if first_run else self.settings.auto_update)
        ttk.Label(prefs, text="Search states").grid(row=0, column=0, sticky="w")
        ttk.Entry(prefs, textvariable=states_var, width=24).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Checkbutton(prefs, text="Keep Auto Bid Builder updated automatically", variable=auto_updates_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(prefs, text=f"New bids: {self.settings.bid_workspace_root}", wraplength=620).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(16, 0))

        def finish(find_jobs: bool = False, configure: bool = False) -> None:
            self.settings.preferred_states = [x.strip().upper() for x in states_var.get().split(",") if x.strip()]
            self.settings.check_updates_on_startup = True
            self.settings.auto_update = bool(auto_updates_var.get())
            self.settings.onboarding_complete = True
            for provider in self.settings.providers:
                if provider.kind in {"cca_public", "ca_dgs_resd"}:
                    provider.enabled = True
            save_settings(self.settings)
            self.states_var.set(",".join(self.settings.preferred_states))
            self.check_updates_var.set(self.settings.check_updates_on_startup)
            self.auto_update_var.set(self.settings.auto_update)
            win.destroy()
            if configure:
                self.notebook.select(2)
            elif find_jobs:
                self.notebook.select(0)
                self.sync_opportunities()

        ttk.Button(buttons, text="Use recommended setup & find jobs", command=lambda: finish(True, False)).pack(side="right")
        ttk.Button(buttons, text="Add company logins first", command=lambda: finish(False, True)).pack(side="right", padx=8)
        ttk.Button(buttons, text="Close", command=lambda: finish(False, False)).pack(side="left")
        win.protocol("WM_DELETE_WINDOW", lambda: finish(False, False))

    # ---------- opportunities ----------
    def _build_opportunities_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text="1. Find Jobs")
        guide = ttk.LabelFrame(tab, text="What to do here", padding=8)
        guide.pack(fill="x", pady=(0, 8))
        ttk.Label(guide, text="Find jobs → select one → open the original listing if needed → Start bid", font=("Segoe UI", 10, "bold")).pack(anchor="w")

        toolbar = ttk.Frame(tab)
        toolbar.pack(fill="x", pady=(0, 8))
        self.sync_button = ttk.Button(toolbar, text="Find jobs now", command=self.sync_opportunities)
        self.sync_button.pack(side="left")
        ttk.Button(toolbar, text="Open original listing", command=self.open_selected_opportunity).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Start bid from selected job", command=self.start_bid).pack(side="left")
        self.opportunity_summary = tk.StringVar(value="No job search run yet.")
        ttk.Label(toolbar, textvariable=self.opportunity_summary).pack(side="right")

        columns = ("score", "tier", "title", "source", "location", "due")
        self.opp_tree = ttk.Treeview(tab, columns=columns, show="headings", selectmode="browse")
        headings = {"score": "Score", "tier": "Review", "title": "Project", "source": "Source", "location": "Location", "due": "Bid due"}
        widths = {"score": 70, "tier": 120, "title": 400, "source": 220, "location": 130, "due": 140}
        for col in columns:
            self.opp_tree.heading(col, text=headings[col])
            self.opp_tree.column(col, width=widths[col], anchor="center" if col == "score" else "w")
        self.opp_tree.pack(fill="both", expand=True, side="left")
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.opp_tree.yview)
        scroll.pack(fill="y", side="right")
        self.opp_tree.configure(yscrollcommand=scroll.set)
        self.opp_tree.bind("<Double-1>", lambda _event: self.open_selected_opportunity())

    def sync_opportunities(self) -> None:
        self.settings = load_settings()
        self._run_background(
            lambda: sync_opportunities(self.settings, self.secrets),
            self._render_opportunities,
            message="Looking for jobs JTI may want to bid...",
        )

    def _render_opportunities(self, payload: dict) -> None:
        self.opp_tree.delete(*self.opp_tree.get_children())
        self._opportunity_rows.clear()
        for idx, row in enumerate(payload.get("opportunities", [])):
            opp = row.get("opportunity", {})
            iid = f"opp-{idx}"
            self._opportunity_rows[iid] = row
            location = ", ".join(x for x in (opp.get("city"), opp.get("state")) if x)
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
            f"{payload.get('total_shown', 0)} worth reviewing / {payload.get('total_normalized', 0)} found"
            + (f" • {len(errors)} source warning(s)" if errors else "")
        )
        if errors:
            self.status.set("Some sources could not be checked; the other sources still ran.")
        elif payload.get("total_shown", 0):
            self.status.set("Job search complete. Select a project to review it.")
        else:
            self.status.set("Nothing met the current review threshold. You can lower the minimum score in Settings.")

    def _selected_opportunity(self) -> dict | None:
        selected = self.opp_tree.selection()
        return self._opportunity_rows.get(selected[0]) if selected else None

    def open_selected_opportunity(self) -> None:
        row = self._selected_opportunity()
        if not row:
            messagebox.showinfo("Auto Bid Builder", "Select a job first.")
            return
        url = row.get("opportunity", {}).get("url")
        if not url:
            messagebox.showinfo("Auto Bid Builder", "This source did not provide a public listing link.")
            return
        webbrowser.open(url)

    def start_bid(self) -> None:
        row = self._selected_opportunity()
        if not row:
            messagebox.showinfo("Auto Bid Builder", "Select the job you want to bid first.")
            return
        try:
            root = create_workspace(self.settings.bid_workspace_root, row)
        except Exception as exc:
            messagebox.showerror("Could not create bid", str(exc))
            return
        self.current_workspace = root
        self._refresh_bid_tab()
        self.notebook.select(1)
        self.status.set("Bid created. Next, add the plans and specifications.")
        self.after(150, self.add_bid_documents)

    # ---------- current bid ----------
    def _build_current_bid_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text="2. Current Bid")

        top = ttk.Frame(tab)
        top.pack(fill="x")
        self.bid_title_var = tk.StringVar(value="No bid is open yet")
        ttk.Label(top, textvariable=self.bid_title_var, font=("Segoe UI", 15, "bold")).pack(side="left")
        ttk.Button(top, text="Open existing bid", command=self.open_existing_bid).pack(side="right")
        ttk.Button(top, text="Open bid folder", command=self.open_current_bid_folder).pack(side="right", padx=6)
        self.bid_path_var = tk.StringVar(value="Find a job and click Start bid, or open an existing Auto Bid Builder project.")
        ttk.Label(tab, textvariable=self.bid_path_var, wraplength=1050).pack(anchor="w", pady=(2, 8))

        steps = ttk.Frame(tab)
        steps.pack(fill="x")

        step1 = ttk.LabelFrame(steps, text="Step 1 - Project", padding=8)
        step1.pack(fill="x", pady=3)
        self.bid_step1_var = tk.StringVar(value="Waiting for a job to be selected.")
        ttk.Label(step1, textvariable=self.bid_step1_var).pack(anchor="w")

        step2 = ttk.LabelFrame(steps, text="Step 2 - Plans and specifications", padding=8)
        step2.pack(fill="x", pady=3)
        row2 = ttk.Frame(step2); row2.pack(fill="x")
        self.bid_step2_var = tk.StringVar(value="Add the plan set, specs, addenda, fixture schedules, and other bid documents.")
        ttk.Label(row2, textvariable=self.bid_step2_var).pack(side="left", fill="x", expand=True)
        self.add_docs_button = ttk.Button(row2, text="Add plans/specs", command=self.add_bid_documents)
        self.add_docs_button.pack(side="right")

        step3 = ttk.LabelFrame(steps, text="Step 3 - Automatic document review", padding=8)
        step3.pack(fill="x", pady=3)
        row3 = ttk.Frame(step3); row3.pack(fill="x")
        self.bid_step3_var = tk.StringVar(value="The app will identify pages most likely to contain JTI scope.")
        ttk.Label(row3, textvariable=self.bid_step3_var).pack(side="left", fill="x", expand=True)
        self.analyze_bid_button = ttk.Button(row3, text="Analyze documents", command=self.analyze_current_bid)
        self.analyze_bid_button.pack(side="right")

        review = ttk.LabelFrame(tab, text="Step 4 - Pages to review first", padding=8)
        review.pack(fill="both", expand=True, pady=(7, 4))
        columns = ("score", "file", "page", "sheet", "scope")
        self.bid_review_tree = ttk.Treeview(review, columns=columns, show="headings", height=7)
        headings = {"score": "Score", "file": "File", "page": "Page", "sheet": "Sheet", "scope": "Detected scope"}
        widths = {"score": 65, "file": 250, "page": 70, "sheet": 90, "scope": 500}
        for col in columns:
            self.bid_review_tree.heading(col, text=headings[col])
            self.bid_review_tree.column(col, width=widths[col], anchor="center" if col in {"score", "page"} else "w")
        self.bid_review_tree.pack(side="left", fill="both", expand=True)
        review_scroll = ttk.Scrollbar(review, orient="vertical", command=self.bid_review_tree.yview)
        review_scroll.pack(side="right", fill="y")
        self.bid_review_tree.configure(yscrollcommand=review_scroll.set)

        step5 = ttk.LabelFrame(tab, text="Step 5 - Estimate and quote preview", padding=8)
        step5.pack(fill="x", pady=(4, 0))
        row5 = ttk.Frame(step5); row5.pack(fill="x")
        self.bid_step5_var = tk.StringVar(value="After document review, build the estimate and confirm scope/pricing before a quote is treated as ready.")
        ttk.Label(row5, textvariable=self.bid_step5_var, wraplength=800).pack(side="left", fill="x", expand=True)
        ttk.Button(row5, text="Open review report", command=self.open_bid_review).pack(side="right")
        ttk.Button(row5, text="Open quote preview", command=self.open_quote_preview).pack(side="right", padx=6)
        self.estimate_button = ttk.Button(row5, text="Build estimate", command=self.open_estimator)
        self.estimate_button.pack(side="right")

    def open_existing_bid(self) -> None:
        folder = filedialog.askdirectory(title="Choose an Auto Bid Builder project folder")
        if not folder:
            return
        root = Path(folder)
        if not (root / "bid_workspace.json").exists():
            messagebox.showerror("Not a bid workspace", "That folder does not contain bid_workspace.json.")
            return
        self.current_workspace = root
        self._refresh_bid_tab()
        self.status.set("Bid opened.")

    def _refresh_bid_tab(self) -> None:
        self.bid_review_tree.delete(*self.bid_review_tree.get_children())
        if self.current_workspace is None:
            self.bid_title_var.set("No bid is open yet")
            self.bid_path_var.set("Find a job and click Start bid, or open an existing Auto Bid Builder project.")
            self.bid_step1_var.set("Waiting for a job to be selected.")
            self.bid_step2_var.set("Add the plan set, specs, addenda, fixture schedules, and other bid documents.")
            self.bid_step3_var.set("Waiting for bid documents.")
            self.bid_step5_var.set("Build the estimate after scope evidence is available.")
            return
        try:
            status = workspace_status(self.current_workspace)
        except Exception as exc:
            self.bid_path_var.set(str(exc))
            return

        self.bid_title_var.set(status["title"])
        self.bid_path_var.set(status["root"])
        self.bid_step1_var.set("✓ Project workspace created and opportunity information saved.")
        if status["file_count"]:
            self.bid_step2_var.set(f"✓ {status['file_count']} bid document(s) added, including {status['pdf_count']} PDF(s).")
        else:
            self.bid_step2_var.set("Next: add the plan set, specs, addenda, schedules, and other bid documents.")

        if status["analysis_status"] in {"complete", "partial"}:
            self.bid_step3_var.set(f"✓ Document review complete. {status['relevant_page_count']} millwork-relevant page(s) identified.")
        elif status["pdf_count"]:
            self.bid_step3_var.set("PDFs are ready. Click Analyze documents.")
        else:
            self.bid_step3_var.set("Waiting for PDFs. Other files can still be kept for manual review.")

        review_path = Path(status["review_json"])
        if review_path.exists():
            try:
                payload = json.loads(review_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            for index, row in enumerate(payload.get("pages", [])[:100]):
                self.bid_review_tree.insert(
                    "",
                    "end",
                    iid=f"review-{index}",
                    values=(
                        row.get("relevance_score", ""),
                        row.get("source", ""),
                        row.get("page", ""),
                        row.get("sheet") or "",
                        ", ".join(row.get("scope_terms") or []),
                    ),
                )

        draft = load_estimate(self.current_workspace)
        if draft is None:
            if review_path.exists():
                self.bid_step5_var.set("Next: click Build estimate. Auto Bid Builder will seed scope lines from the evidence review for the estimator to correct and price.")
            else:
                self.bid_step5_var.set("Run document review first, then build the estimate.")
        else:
            warnings = draft.warnings()
            if warnings:
                self.bid_step5_var.set(f"Estimate: ${draft.total:,.2f}. {len(warnings)} review item(s) remain before the quote preview is ready.")
            else:
                self.bid_step5_var.set(f"✓ Estimate: ${draft.total:,.2f}. Current review gates are complete; quote preview can be generated for final estimator review.")

    def add_bid_documents(self) -> None:
        if self.current_workspace is None:
            messagebox.showinfo("Auto Bid Builder", "Start or open a bid first.")
            return
        files = filedialog.askopenfilenames(
            title="Select plans, specs, addenda, schedules, or other bid documents",
            filetypes=[
                ("Bid documents", "*.pdf *.zip *.dwg *.dxf *.xlsx *.xls *.docx *.doc"),
                ("PDF files", "*.pdf"),
                ("All files", "*.*"),
            ],
        )
        if not files:
            return
        try:
            copied = add_documents(self.current_workspace, files)
        except Exception as exc:
            messagebox.showerror("Could not add documents", str(exc))
            return
        self._refresh_bid_tab()
        if any(path.suffix.lower() == ".pdf" for path in copied):
            self.analyze_current_bid()
        else:
            self.status.set(f"Added {len(copied)} document(s). Add PDFs for automatic page review.")

    def analyze_current_bid(self) -> None:
        if self.current_workspace is None:
            messagebox.showinfo("Auto Bid Builder", "Start or open a bid first.")
            return
        root = self.current_workspace
        self._run_background(
            lambda: analyze_workspace(root),
            self._analysis_finished,
            message="Reviewing bid documents for millwork scope...",
        )

    def _analysis_finished(self, payload: dict) -> None:
        self._refresh_bid_tab()
        if payload.get("pdf_count", 0) == 0:
            self.status.set("No PDFs found. Add plan/spec PDFs and run review again.")
        else:
            self.status.set(f"Document review complete: {payload.get('relevant_page_count', 0)} relevant page(s) identified.")

    def open_estimator(self) -> None:
        if self.current_workspace is None:
            messagebox.showinfo("Auto Bid Builder", "Start or open a bid first.")
            return
        wizard = launch_estimator(self, self.current_workspace, open_path=self._open_path)
        wizard.bind("<Destroy>", lambda _event: self.after(100, self._refresh_bid_tab), add="+")

    def open_current_bid_folder(self) -> None:
        if self.current_workspace is None:
            messagebox.showinfo("Auto Bid Builder", "No bid is open yet.")
            return
        self._open_path(self.current_workspace)

    def open_bid_review(self) -> None:
        if self.current_workspace is None:
            return
        report = self.current_workspace / "output" / "bid_review.md"
        if not report.exists():
            messagebox.showinfo("Auto Bid Builder", "Run Analyze documents first.")
            return
        self._open_path(report)

    def open_quote_preview(self) -> None:
        if self.current_workspace is None:
            return
        pdf = self.current_workspace / "output" / "quote_preview.pdf"
        html = self.current_workspace / "output" / "quote_preview.html"
        target = pdf if pdf.exists() else html if html.exists() else None
        if target is None:
            messagebox.showinfo("Auto Bid Builder", "Open Build estimate and click Generate quote preview first.")
            return
        self._open_path(target)

    # ---------- settings/providers ----------
    def _build_sources_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text="Sources & Settings")
        ttk.Label(
            tab,
            text="Public sources work without a login. Add credentials only for services JTI actually uses. Passwords and API keys are kept outside the repository.",
            wraplength=920,
        ).pack(anchor="w", pady=(0, 8))

        general = ttk.LabelFrame(tab, text="Job search and bid storage", padding=10)
        general.pack(fill="x")
        self.states_var = tk.StringVar(value=",".join(self.settings.preferred_states))
        self.lookback_var = tk.StringVar(value=str(self.settings.lookback_days))
        self.min_score_var = tk.StringVar(value=f"{self.settings.minimum_score:g}")
        self.workspace_root_var = tk.StringVar(value=self.settings.bid_workspace_root)
        ttk.Label(general, text="Preferred states").grid(row=0, column=0, sticky="w")
        ttk.Entry(general, textvariable=self.states_var, width=22).grid(row=1, column=0, sticky="ew", padx=(0, 10))
        ttk.Label(general, text="Lookback days").grid(row=0, column=1, sticky="w")
        ttk.Entry(general, textvariable=self.lookback_var, width=12).grid(row=1, column=1, sticky="w", padx=(0, 10))
        ttk.Label(general, text="Minimum review score").grid(row=0, column=2, sticky="w")
        ttk.Entry(general, textvariable=self.min_score_var, width=12).grid(row=1, column=2, sticky="w")
        ttk.Button(general, text="Save", command=self.save_general_settings).grid(row=1, column=3, padx=12)
        ttk.Label(general, text="New bid folder location").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(general, textvariable=self.workspace_root_var).grid(row=3, column=0, columnspan=3, sticky="ew", padx=(0, 10))
        ttk.Button(general, text="Choose folder", command=self.choose_workspace_root).grid(row=3, column=3, sticky="w")
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
        ttk.Checkbutton(right, text="Use this source when finding jobs", variable=self.provider_enabled_var).pack(anchor="w")

        self.provider_base_label = ttk.Label(right, text="Base URL")
        self.provider_base_var = tk.StringVar()
        self.provider_base_entry = ttk.Entry(right, textvariable=self.provider_base_var)
        self.provider_feed_label = ttk.Label(right, text="Feed URL")
        self.provider_feed_var = tk.StringVar()
        self.provider_feed_entry = ttk.Entry(right, textvariable=self.provider_feed_var)
        self.provider_secret_frame = ttk.Frame(right)
        self.provider_secret_frame.pack(fill="x", pady=(8, 0))
        ttk.Button(right, text="Save this source", command=self.save_provider).pack(anchor="e", pady=(12, 0))
        if self.settings.providers:
            self.provider_list.selection_set(0)
            self._provider_selected()

    def choose_workspace_root(self) -> None:
        folder = filedialog.askdirectory(title="Choose where JTI bid folders should be stored", initialdir=self.workspace_root_var.get() or None)
        if folder:
            self.workspace_root_var.set(folder)
            self.save_general_settings()

    def save_general_settings(self) -> None:
        try:
            self.settings.preferred_states = [x.strip().upper() for x in self.states_var.get().split(",") if x.strip()]
            self.settings.lookback_days = max(1, int(self.lookback_var.get()))
            self.settings.minimum_score = float(self.min_score_var.get())
        except ValueError:
            messagebox.showerror("Auto Bid Builder", "Lookback days and minimum score must be numbers.")
            return
        root = self.workspace_root_var.get().strip()
        if root:
            self.settings.bid_workspace_root = root
        save_settings(self.settings)
        self.status.set("Settings saved.")

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
            configured = "already saved" if self.secrets.has(provider.id, field_name) else "not set"
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
        ttk.Label(
            tab,
            text="Recommended: leave update checks on. Installed Windows builds update from published releases; developer checkouts use safe Git fast-forward updates.",
            wraplength=850,
        ).pack(anchor="w", pady=(0, 10))
        self.check_updates_var = tk.BooleanVar(value=self.settings.check_updates_on_startup)
        self.auto_update_var = tk.BooleanVar(value=self.settings.auto_update)
        ttk.Checkbutton(tab, text="Check for updates when Auto Bid Builder starts", variable=self.check_updates_var, command=self.save_update_settings).pack(anchor="w")
        ttk.Checkbutton(tab, text="Install available updates automatically", variable=self.auto_update_var, command=self.save_update_settings).pack(anchor="w", pady=(6, 0))
        ttk.Separator(tab).pack(fill="x", pady=16)
        self.update_status = tk.StringVar(value="Update status has not been checked yet.")
        ttk.Label(tab, textvariable=self.update_status, wraplength=850).pack(anchor="w")
        buttons = ttk.Frame(tab); buttons.pack(anchor="w", pady=12)
        self.check_update_button = ttk.Button(buttons, text="Check for updates now", command=self.check_updates)
        self.check_update_button.pack(side="left")
        self.install_update_button = ttk.Button(buttons, text="Install available update", command=self.install_update)
        self.install_update_button.pack(side="left", padx=8)
        ttk.Label(tab, text="Packaged updates download, replace the app after it closes, and reopen automatically. Normal JTI users should not need Git.", wraplength=850).pack(anchor="w", pady=(8, 0))

    def save_update_settings(self) -> None:
        self.settings.check_updates_on_startup = bool(self.check_updates_var.get())
        self.settings.auto_update = bool(self.auto_update_var.get())
        save_settings(self.settings)
        self.status.set("Update settings saved.")

    def _startup_update_check(self) -> None:
        if not self.settings.check_updates_on_startup:
            return
        if self.settings.auto_update:
            self._run_background(lambda: apply_update(self.settings.update_branch), self._update_finished, message="Checking for updates...")
        else:
            self.check_updates(silent=True)

    def check_updates(self, silent: bool = False) -> None:
        def done(result) -> None:
            self.update_status.set(result.message)
            if result.update_available and not silent:
                messagebox.showinfo("Update available", result.message)
        self._run_background(lambda: check_for_updates(self.settings.update_branch), done, message="Checking for updates...")

    def install_update(self) -> None:
        if not messagebox.askyesno("Install update", "Install the latest available update? Auto Bid Builder may close and reopen automatically."):
            return
        self._run_background(lambda: apply_update(self.settings.update_branch), self._update_finished, message="Installing update...")

    def _update_finished(self, result) -> None:
        self.update_status.set(result.message)
        if getattr(result, "relaunch_scheduled", False):
            self.status.set(result.message)
            self.after(900, self.destroy)
        elif getattr(result, "restart_required", False):
            messagebox.showinfo("Update installed", f"{result.message}\n\nClose and reopen Auto Bid Builder to use the new version.")


def main() -> None:
    app = AutoBidBuilderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
