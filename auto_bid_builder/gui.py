from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from .bid_workspace import add_documents, analyze_workspace, create_workspace, workspace_status
from .opportunities.sync import sync_opportunities
from .settings import AppSettings, ProviderSettings, SecretStore, load_settings, save_settings
from .updater import apply_update, check_for_updates


class AutoBidBuilderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Auto Bid Builder")
        self.geometry("1220x790")
        self.minsize(980, 650)
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
        for button_name in ("sync_button", "check_update_button", "install_update_button", "analyze_bid_button", "add_docs_button"):
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
            f"Something went wrong:\n\n{type(exc).__name__}: {exc}\n\nYou can keep using the app. Try the action again or open Sources & Settings to check the connection.",
        )

    def _background_done(self, result, done) -> None:
        self._set_busy(False, "Ready")
        done(result)

    def _open_path(self, path: Path) -> None:
        path = path.resolve()
        try:
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif os.uname().sysname == "Darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            webbrowser.open(path.as_uri())

    # ---------- first-run onboarding ----------
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
            text="You do not need to understand APIs, Git, or estimating software. The app will walk you from finding a job through collecting the plans and reviewing the millwork evidence.",
            wraplength=680,
        ).pack(anchor="w", pady=(6, 16))

        steps = ttk.LabelFrame(outer, text="The normal workflow", padding=12)
        steps.pack(fill="x")
        for number, title, body in (
            ("1", "Find jobs", "The app checks the bid sources you have enabled and brings likely millwork work into one list."),
            ("2", "Start a bid", "Select a project. Auto Bid Builder creates and manages the project folder for you."),
            ("3", "Add plans and specs", "Choose the downloaded bid documents. The app copies them into the right place and immediately reviews PDFs."),
            ("4", "Review the evidence", "The Current Bid tab shows the most millwork-relevant sheets and creates a review report for the estimator."),
        ):
            row = ttk.Frame(steps)
            row.pack(fill="x", pady=5)
            ttk.Label(row, text=number, font=("Segoe UI", 13, "bold"), width=3).pack(side="left", anchor="n")
            text = ttk.Frame(row)
            text.pack(side="left", fill="x", expand=True)
            ttk.Label(text, text=title, font=("Segoe UI", 11, "bold")).pack(anchor="w")
            ttk.Label(text, text=body, wraplength=590).pack(anchor="w")

        prefs = ttk.LabelFrame(outer, text="Recommended starting setup", padding=12)
        prefs.pack(fill="x", pady=(14, 0))
        ttk.Label(prefs, text="Search these states:").grid(row=0, column=0, sticky="w")
        states_var = tk.StringVar(value=",".join(self.settings.preferred_states or ["CA", "NV"]))
        ttk.Entry(prefs, textvariable=states_var, width=24).grid(row=0, column=1, sticky="w", padx=(8, 0))
        auto_updates_var = tk.BooleanVar(value=True if first_run else self.settings.auto_update)
        ttk.Checkbutton(
            prefs,
            text="Keep Auto Bid Builder updated automatically",
            variable=auto_updates_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(
            prefs,
            text=f"New bids will be stored under: {self.settings.bid_workspace_root}",
            wraplength=620,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(
            prefs,
            text="Public sources already work without a login. Paid/private bid services can be added later in Sources & Settings.",
            wraplength=620,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(18, 0))

        def finish(*, find_jobs: bool, configure_sources: bool = False) -> None:
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
            if configure_sources:
                self.notebook.select(2)
                self.status.set("Add any JTI bid-service logins here. Public sources already work without a login.")
            elif find_jobs:
                self.notebook.select(0)
                self.sync_opportunities()

        ttk.Button(buttons, text="Use recommended setup & find jobs", command=lambda: finish(find_jobs=True)).pack(side="right")
        ttk.Button(buttons, text="Add company bid-service logins first", command=lambda: finish(find_jobs=False, configure_sources=True)).pack(side="right", padx=8)
        ttk.Button(buttons, text="Close", command=lambda: finish(find_jobs=False)).pack(side="left")

        win.protocol("WM_DELETE_WINDOW", lambda: finish(find_jobs=False))
        win.update_idletasks()
        x = self.winfo_rootx() + max(20, (self.winfo_width() - win.winfo_width()) // 2)
        y = self.winfo_rooty() + max(20, (self.winfo_height() - win.winfo_height()) // 2)
        win.geometry(f"+{x}+{y}")

    # ---------- opportunities ----------
    def _build_opportunities_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text="1. Find Jobs")

        guide = ttk.LabelFrame(tab, text="What to do here", padding=8)
        guide.pack(fill="x", pady=(0, 8))
        ttk.Label(
            guide,
            text="1. Click Find jobs now   →   2. Select a promising project   →   3. Open the original listing if needed   →   4. Start the bid",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")

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
            message="Looking for jobs JTI may want to bid...",
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
            f"{payload.get('total_shown', 0)} worth reviewing / {payload.get('total_normalized', 0)} found"
            + (f" • {len(errors)} source warning(s)" if errors else "")
        )
        if errors:
            self.status.set("Some sources could not be checked. The others still worked. Open Sources & Settings if you want to fix them.")
        elif payload.get("total_shown", 0):
            self.status.set("Job search complete. Select a project to review it.")
        else:
            self.status.set("Job search complete. Nothing met the current review threshold. You can lower the minimum score in Sources & Settings.")

    def _selected_opportunity(self) -> dict | None:
        selected = self.opp_tree.selection()
        return self._opportunity_rows.get(selected[0]) if selected else None

    def open_selected_opportunity(self) -> None:
        row = self._selected_opportunity()
        if not row:
            messagebox.showinfo("Auto Bid Builder", "Select a job from the list first, then click Open original listing.")
            return
        url = row.get("opportunity", {}).get("url")
        if not url:
            messagebox.showinfo("Auto Bid Builder", "This source did not provide a public listing link. You can still keep the opportunity for review.")
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

    # ---------- guided current bid ----------
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
        ttk.Label(tab, textvariable=self.bid_path_var, wraplength=1000).pack(anchor="w", pady=(2, 10))

        steps = ttk.Frame(tab)
        steps.pack(fill="x")

        step1 = ttk.LabelFrame(steps, text="Step 1 - Project", padding=10)
        step1.pack(fill="x", pady=4)
        self.bid_step1_var = tk.StringVar(value="Waiting for a job to be selected.")
        ttk.Label(step1, textvariable=self.bid_step1_var).pack(anchor="w")

        step2 = ttk.LabelFrame(steps, text="Step 2 - Plans and specifications", padding=10)
        step2.pack(fill="x", pady=4)
        row2 = ttk.Frame(step2); row2.pack(fill="x")
        self.bid_step2_var = tk.StringVar(value="Add the plan set, specs, addenda, fixture schedules, and other bid documents.")
        ttk.Label(row2, textvariable=self.bid_step2_var).pack(side="left", fill="x", expand=True)
        self.add_docs_button = ttk.Button(row2, text="Add plans/specs", command=self.add_bid_documents)
        self.add_docs_button.pack(side="right")

        step3 = ttk.LabelFrame(steps, text="Step 3 - Automatic document review", padding=10)
        step3.pack(fill="x", pady=4)
        row3 = ttk.Frame(step3); row3.pack(fill="x")
        self.bid_step3_var = tk.StringVar(value="After PDFs are added, Auto Bid Builder will identify the pages most likely to contain JTI scope.")
        ttk.Label(row3, textvariable=self.bid_step3_var).pack(side="left", fill="x", expand=True)
        self.analyze_bid_button = ttk.Button(row3, text="Analyze documents", command=self.analyze_current_bid)
        self.analyze_bid_button.pack(side="right")

        review = ttk.LabelFrame(tab, text="Step 4 - Pages to review first", padding=8)
        review.pack(fill="both", expand=True, pady=(8, 4))
        columns = ("score", "file", "page", "sheet", "scope")
        self.bid_review_tree = ttk.Treeview(review, columns=columns, show="headings", height=9)
        headings = {"score": "Score", "file": "File", "page": "Page", "sheet": "Sheet", "scope": "Detected scope"}
        widths = {"score": 65, "file": 260, "page": 70, "sheet": 90, "scope": 470}
        for col in columns:
            self.bid_review_tree.heading(col, text=headings[col])
            self.bid_review_tree.column(col, width=widths[col], anchor="w" if col not in {"score", "page"} else "center")
        self.bid_review_tree.pack(side="left", fill="both", expand=True)
        review_scroll = ttk.Scrollbar(review, orient="vertical", command=self.bid_review_tree.yview)
        review_scroll.pack(side="right", fill="y")
        self.bid_review_tree.configure(yscrollcommand=review_scroll.set)

        bottom = ttk.Frame(tab)
        bottom.pack(fill="x", pady=(6, 0))
        self.bid_step4_var = tk.StringVar(value="The review report will appear here after analysis.")
        ttk.Label(bottom, textvariable=self.bid_step4_var).pack(side="left", fill="x", expand=True)
        ttk.Button(bottom, text="Open review report", command=self.open_bid_review).pack(side="right")
        ttk.Button(bottom, text="Open estimate folder", command=lambda: self.open_bid_subfolder("estimate")).pack(side="right", padx=6)

    def open_existing_bid(self) -> None:
        folder = filedialog.askdirectory(title="Choose an Auto Bid Builder project folder")
        if not folder:
            return
        root = Path(folder)
        if not (root / "bid_workspace.json").exists():
            messagebox.showerror("Not a bid workspace", "That folder does not contain an Auto Bid Builder bid_workspace.json file.")
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
            self.bid_step3_var.set("After PDFs are added, Auto Bid Builder will identify the pages most likely to contain JTI scope.")
            self.bid_step4_var.set("The review report will appear here after analysis.")
            return
        try:
            status = workspace_status(self.current_workspace)
        except Exception as exc:
            self.bid_path_var.set(str(exc))
            return

        self.bid_title_var.set(status["title"])
        self.bid_path_var.set(status["root"])
        self.bid_step1_var.set("✓ Job workspace created and opportunity information saved.")
        if status["file_count"]:
            self.bid_step2_var.set(f"✓ {status['file_count']} bid document(s) added, including {status['pdf_count']} PDF(s). Add more files at any time.")
        else:
            self.bid_step2_var.set("Next: add the plan set, specs, addenda, fixture schedules, and other bid documents.")

        analysis_status = status["analysis_status"]
        if analysis_status in {"complete", "partial"}:
            self.bid_step3_var.set(f"✓ Review complete. {status['relevant_page_count']} millwork-relevant page(s) were identified.")
        elif status["pdf_count"]:
            self.bid_step3_var.set("PDFs are ready. Click Analyze documents to review them.")
        else:
            self.bid_step3_var.set("Waiting for PDFs. Image-only files can still be kept in the project for manual review.")

        review_path = Path(status["review_json"])
        if review_path.exists():
            try:
                payload = json.loads(review_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            for index, row in enumerate(payload.get("pages", [])[:100]):
                scope = ", ".join(row.get("scope_terms") or [])
                self.bid_review_tree.insert(
                    "",
                    "end",
                    iid=f"review-{index}",
                    values=(row.get("relevance_score", ""), row.get("source", ""), row.get("page", ""), row.get("sheet") or "", scope),
                )
            self.bid_step4_var.set("Review the highest-scoring pages first. The full evidence report is saved with the bid.")
        elif status["pdf_count"]:
            self.bid_step4_var.set("Run the automatic review to populate this list.")
        else:
            self.bid_step4_var.set("Add plans/specs first.")

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
            self.status.set(f"Added {len(copied)} document(s). Add PDFs when available for automatic page review.")

    def analyze_current_bid(self) -> None:
        if self.current_workspace is None:
            messagebox.showinfo("Auto Bid Builder", "Start or open a bid first.")
            return
        root = self.current_workspace
        self._run_background(
            lambda: analyze_workspace(root),
            self._analysis_finished,
            message="Reviewing the bid documents for millwork scope...",
        )

    def _analysis_finished(self, payload: dict) -> None:
        self._refresh_bid_tab()
        if payload.get("pdf_count", 0) == 0:
            self.status.set("No PDFs were found. Add the plan/spec PDFs and run the review again.")
        else:
            self.status.set(f"Document review complete: {payload.get('relevant_page_count', 0)} relevant page(s) identified.")

    def open_current_bid_folder(self) -> None:
        if self.current_workspace is None:
            messagebox.showinfo("Auto Bid Builder", "No bid is open yet.")
            return
        self._open_path(self.current_workspace)

    def open_bid_subfolder(self, name: str) -> None:
        if self.current_workspace is None:
            messagebox.showinfo("Auto Bid Builder", "No bid is open yet.")
            return
        folder = self.current_workspace / name
        folder.mkdir(exist_ok=True)
        self._open_path(folder)

    def open_bid_review(self) -> None:
        if self.current_workspace is None:
            messagebox.showinfo("Auto Bid Builder", "No bid is open yet.")
            return
        report = self.current_workspace / "output" / "bid_review.md"
        if not report.exists():
            messagebox.showinfo("Auto Bid Builder", "Run Analyze documents first. The review report will be created automatically.")
            return
        self._open_path(report)

    # ---------- settings/providers ----------
    def _build_sources_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text="Sources & Settings")

        ttk.Label(
            tab,
            text="Public sources work without a login. Only add credentials for services JTI actually uses. Passwords and API keys are stored outside the project repository.",
            wraplength=900,
        ).pack(anchor="w", pady=(0, 8))

        general = ttk.LabelFrame(tab, text="Job search and bid storage", padding=10)
        general.pack(fill="x")
        self.states_var = tk.StringVar(value=",".join(self.settings.preferred_states))
        self.lookback_var = tk.StringVar(value=str(self.settings.lookback_days))
        self.min_score_var = tk.StringVar(value=f"{self.settings.minimum_score:g}")
        self.workspace_root_var = tk.StringVar(value=self.settings.bid_workspace_root)
        ttk.Label(general, text="Preferred states").grid(row=0, column=0, sticky="w")
        ttk.Entry(general, textvariable=self.states_var, width=22).grid(row=1, column=0, sticky="ew", padx=(0, 10))
        ttk.Label(general, text="Look back this many days").grid(row=0, column=1, sticky="w")
        ttk.Entry(general, textvariable=self.lookback_var, width=12).grid(row=1, column=1, sticky="w", padx=(0, 10))
        ttk.Label(general, text="Minimum review score").grid(row=0, column=2, sticky="w")
        ttk.Entry(general, textvariable=self.min_score_var, width=12).grid(row=1, column=2, sticky="w")
        ttk.Button(general, text="Save search settings", command=self.save_general_settings).grid(row=1, column=3, padx=12)
        ttk.Label(general, text="Where new bid folders are stored").grid(row=2, column=0, sticky="w", pady=(10, 0))
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
        self.status.set("Search and bid-folder settings saved.")

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
        ttk.Label(
            tab,
            text="Normal JTI users should never need to deal with Git or copy program files manually. Packaged updates download, replace the app after it closes, and reopen it automatically.",
            wraplength=850,
        ).pack(anchor="w", pady=(8, 0))

    def save_update_settings(self) -> None:
        self.settings.check_updates_on_startup = bool(self.check_updates_var.get())
        self.settings.auto_update = bool(self.auto_update_var.get())
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
        if not messagebox.askyesno("Install update", "Install the latest available update? Auto Bid Builder may close and reopen automatically."):
            return
        self._run_background(
            lambda: apply_update(self.settings.update_branch),
            self._update_finished,
            message="Installing update...",
        )

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
