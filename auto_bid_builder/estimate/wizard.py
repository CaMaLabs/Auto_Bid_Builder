from __future__ import annotations

from pathlib import Path
from statistics import median
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from .autoprice import apply_auto_pricing, import_cost_detail_pdf, load_historical_examples
from .draft import (
    HISTORICAL_STARTER_MATERIAL_MARKUP,
    LABOR_CATEGORIES,
    EstimateDraft,
    EstimateLine,
    create_estimate_from_workspace,
    load_estimate,
    save_estimate,
    write_quote_preview,
)


class EstimateWizard(tk.Toplevel):
    """Guided estimator review for one Auto Bid Builder workspace.

    The app can make provisional pricing suggestions, but estimator review remains a
    hard gate. Historical calibration files live locally and are never committed to
    the public repository.
    """

    def __init__(self, parent: tk.Misc, workspace: str | Path, open_path=None) -> None:
        super().__init__(parent)
        self.workspace = Path(workspace)
        self.open_path = open_path
        self.draft = load_estimate(self.workspace) or create_estimate_from_workspace(self.workspace)
        self._slider_base_rates: dict[str, float] = {}
        self._slider_base_materials: dict[int, float] = {}
        self._reset_tuning_baseline()
        self.title("Build Estimate - Auto Bid Builder")
        self.geometry("1260x840")
        self.minsize(1040, 700)
        self.transient(parent)
        self._build_ui()
        self._load_fields()
        self._refresh_lines()

    def _reset_tuning_baseline(self) -> None:
        self._slider_base_rates = {code: float(self.draft.labor_rates.get(code, 0.0) or 0.0) for code in LABOR_CATEGORIES}
        self._slider_base_materials = {line.item: float(line.material_cost or 0.0) for line in self.draft.lines}

    def _current_markup_percent(self) -> float:
        values = [line.material_markup_rate * 100.0 for line in self.draft.lines if line.material_cost > 0]
        return median(values) if values else HISTORICAL_STARTER_MATERIAL_MARKUP * 100.0

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(14, 12, 14, 6))
        header.pack(fill="x")
        ttk.Label(header, text="Build the JTI estimate", font=("Segoe UI", 17, "bold")).pack(side="left")
        self.total_var = tk.StringVar(value="$0.00")
        ttk.Label(header, textvariable=self.total_var, font=("Segoe UI", 15, "bold")).pack(side="right")

        info = ttk.LabelFrame(self, text="1. Quote information", padding=10)
        info.pack(fill="x", padx=12, pady=(0, 8))
        self.project_var = tk.StringVar()
        self.quote_var = tk.StringVar()
        self.date_var = tk.StringVar()
        self.terms_var = tk.StringVar()
        self.rep_var = tk.StringVar()
        labels = (("Project", self.project_var, 0, 0, 42), ("Quote #", self.quote_var, 0, 1, 16), ("Date", self.date_var, 0, 2, 16), ("Terms", self.terms_var, 0, 3, 16), ("Rep", self.rep_var, 0, 4, 10))
        for label, var, row, col, width in labels:
            cell = ttk.Frame(info)
            cell.grid(row=row, column=col, sticky="ew", padx=(0, 8))
            ttk.Label(cell, text=label).pack(anchor="w")
            ttk.Entry(cell, textvariable=var, width=width).pack(fill="x")
        info.columnconfigure(0, weight=3)
        for col in range(1, 5):
            info.columnconfigure(col, weight=1)

        pricing = ttk.LabelFrame(self, text="2. Pricing profile", padding=10)
        pricing.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(
            pricing,
            text="Auto Bid Builder can prefill a best-effort estimate from private local JTI cost-detail history. When history is unavailable it uses clearly marked low-confidence allowances. All generated values remain estimator-review items.",
            wraplength=1160,
        ).grid(row=0, column=0, columnspan=10, sticky="w", pady=(0, 8))
        self.rate_vars: dict[str, tk.StringVar] = {}
        for col, category in enumerate(LABOR_CATEGORIES):
            ttk.Label(pricing, text=category).grid(row=1, column=col, sticky="w")
            var = tk.StringVar()
            self.rate_vars[category] = var
            ttk.Entry(pricing, textvariable=var, width=10).grid(row=2, column=col, padx=(0, 6), sticky="w")
        self.scope_confirm_var = tk.BooleanVar()
        self.pricing_confirm_var = tk.BooleanVar()
        self.tax_confirm_var = tk.BooleanVar()
        checks = ttk.Frame(pricing)
        checks.grid(row=3, column=0, columnspan=10, sticky="w", pady=(9, 0))
        ttk.Checkbutton(checks, text="Estimator reviewed the scope", variable=self.scope_confirm_var).pack(side="left")
        ttk.Checkbutton(checks, text="Current labor/pricing rates confirmed", variable=self.pricing_confirm_var).pack(side="left", padx=14)
        ttk.Checkbutton(checks, text="Material tax treatment confirmed", variable=self.tax_confirm_var).pack(side="left")

        tuning = ttk.LabelFrame(pricing, text="Live bid tuning", padding=8)
        tuning.grid(row=4, column=0, columnspan=10, sticky="ew", pady=(10, 0))
        ttk.Label(
            tuning,
            text="Use these as quick what-if controls. The estimate total and every affected line update immediately. Moving a slider clears the pricing confirmation so somebody must review the result.",
            wraplength=1130,
        ).grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 6))

        self.labor_adjust_var = tk.DoubleVar(value=100.0)
        self.material_adjust_var = tk.DoubleVar(value=100.0)
        self.markup_adjust_var = tk.DoubleVar(value=self._current_markup_percent())
        self.install_rate_var = tk.DoubleVar(value=float(self.draft.labor_rates.get("I", 0.0) or 0.0))
        self.labor_adjust_label = tk.StringVar(value="100%")
        self.material_adjust_label = tk.StringVar(value="100%")
        self.markup_adjust_label = tk.StringVar(value=f"{self.markup_adjust_var.get():.0f}%")
        self.install_rate_label = tk.StringVar(value=f"${self.install_rate_var.get():.0f}/hr")

        controls = (
            ("Shop labor", self.labor_adjust_var, self.labor_adjust_label, 70.0, 160.0),
            ("Materials", self.material_adjust_var, self.material_adjust_label, 70.0, 160.0),
            ("Material markup", self.markup_adjust_var, self.markup_adjust_label, 0.0, 100.0),
            ("Installation rate", self.install_rate_var, self.install_rate_label, 0.0, 250.0),
        )
        for col, (label, variable, value_label, lo, hi) in enumerate(controls):
            frame = ttk.Frame(tuning)
            frame.grid(row=1, column=col, sticky="ew", padx=(0, 12))
            top = ttk.Frame(frame); top.pack(fill="x")
            ttk.Label(top, text=label).pack(side="left")
            ttk.Label(top, textvariable=value_label, font=("Segoe UI", 9, "bold")).pack(side="right")
            ttk.Scale(frame, from_=lo, to=hi, variable=variable, command=lambda _v: self._apply_live_tuning()).pack(fill="x")
            tuning.columnconfigure(col, weight=1)

        actions = ttk.Frame(pricing)
        actions.grid(row=5, column=0, columnspan=10, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="Auto-fill best effort", command=self.auto_fill).pack(side="left")
        ttk.Button(actions, text="Import JTI cost-detail history", command=self.import_history).pack(side="left", padx=6)
        self.history_status_var = tk.StringVar(value="")
        ttk.Label(actions, textvariable=self.history_status_var).pack(side="left", padx=10)

        lines_frame = ttk.LabelFrame(self, text="3. Scope and pricing lines", padding=8)
        lines_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        toolbar = ttk.Frame(lines_frame)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(toolbar, text="Add scope item", command=self.add_line).pack(side="left")
        ttk.Button(toolbar, text="Edit selected", command=self.edit_selected).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Remove selected", command=self.remove_selected).pack(side="left")
        ttk.Label(toolbar, text="Double-click a row to edit it. Auto-filled lines remain suggestions until an estimator accepts them.").pack(side="right")

        columns = ("item", "included", "description", "qty", "labor", "material", "markup", "tax", "amount")
        self.tree = ttk.Treeview(lines_frame, columns=columns, show="headings", selectmode="browse", height=12)
        headings = {
            "item": "#", "included": "In?", "description": "Description", "qty": "Qty", "labor": "Labor",
            "material": "Material", "markup": "Markup", "tax": "Tax", "amount": "Amount",
        }
        widths = {"item": 42, "included": 45, "description": 480, "qty": 60, "labor": 95, "material": 95, "markup": 90, "tax": 80, "amount": 105}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="w" if col == "description" else "e")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(lines_frame, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", lambda _event: self.edit_selected())

        bottom = ttk.Frame(self, padding=(12, 0, 12, 12))
        bottom.pack(fill="x")
        self.warning_var = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.warning_var, wraplength=760).pack(side="left", fill="x", expand=True)
        ttk.Button(bottom, text="Save", command=self.save).pack(side="right")
        ttk.Button(bottom, text="Generate JTI quote", command=self.generate_preview).pack(side="right", padx=8)

    def _load_fields(self) -> None:
        self.project_var.set(self.draft.project_title)
        self.quote_var.set(self.draft.quote_number)
        self.date_var.set(self.draft.quote_date)
        self.terms_var.set(self.draft.terms)
        self.rep_var.set(self.draft.rep)
        for category in LABOR_CATEGORIES:
            self.rate_vars[category].set(f"{float(self.draft.labor_rates.get(category, 0.0) or 0.0):g}")
        self.scope_confirm_var.set(self.draft.scope_review_confirmed)
        self.pricing_confirm_var.set(self.draft.pricing_profile_confirmed)
        self.tax_confirm_var.set(self.draft.tax_rate_confirmed)
        count = len(load_historical_examples())
        self.history_status_var.set(f"{count} local historical pricing line(s) available" if count else "No private history imported yet; best effort uses provisional allowances")

    def _sync_fields(self) -> bool:
        try:
            rates = {category: float(self.rate_vars[category].get().strip() or 0.0) for category in LABOR_CATEGORIES}
        except ValueError:
            messagebox.showerror("Pricing profile", "Labor rates must be numbers.", parent=self)
            return False
        self.draft.project_title = self.project_var.get().strip() or self.draft.project_title
        self.draft.quote_number = self.quote_var.get().strip() or "DRAFT"
        self.draft.quote_date = self.date_var.get().strip()
        self.draft.terms = self.terms_var.get().strip()
        self.draft.rep = self.rep_var.get().strip()
        self.draft.labor_rates = rates
        self.draft.scope_review_confirmed = bool(self.scope_confirm_var.get())
        self.draft.pricing_profile_confirmed = bool(self.pricing_confirm_var.get())
        self.draft.tax_rate_confirmed = bool(self.tax_confirm_var.get())
        return True

    def _refresh_lines(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, line in enumerate(self.draft.lines):
            labor = line.labor_total(self.draft.labor_rates)
            self.tree.insert(
                "", "end", iid=f"line-{index}",
                values=(
                    line.item,
                    "Yes" if line.included else "No",
                    line.description,
                    f"{line.quantity:g}",
                    f"${labor:,.2f}",
                    f"${line.material_cost:,.2f}",
                    f"${line.material_markup:,.2f}",
                    f"${line.material_tax:,.2f}",
                    f"${line.sell_total(self.draft.labor_rates):,.2f}",
                ),
            )
        self.total_var.set(f"Estimate total: ${self.draft.total:,.2f}")
        warnings = self.draft.warnings()
        if warnings:
            self.warning_var.set(f"Needs attention: {warnings[0]}" + (f"  (+{len(warnings)-1} more)" if len(warnings) > 1 else ""))
        else:
            self.warning_var.set("✓ Scope, pricing, and tax gates are complete. JTI-formatted quote is ready for estimator final review.")

    def _apply_live_tuning(self) -> None:
        if not hasattr(self, "labor_adjust_var"):
            return
        labor_factor = float(self.labor_adjust_var.get()) / 100.0
        material_factor = float(self.material_adjust_var.get()) / 100.0
        markup = float(self.markup_adjust_var.get()) / 100.0
        install_rate = float(self.install_rate_var.get())

        for code in LABOR_CATEGORIES:
            if code == "I":
                self.draft.labor_rates[code] = round(install_rate, 2)
            else:
                self.draft.labor_rates[code] = round(self._slider_base_rates.get(code, 0.0) * labor_factor, 2)
            if hasattr(self, "rate_vars") and code in self.rate_vars:
                self.rate_vars[code].set(f"{self.draft.labor_rates[code]:g}")
        for line in self.draft.lines:
            if line.item in self._slider_base_materials:
                line.material_cost = round(self._slider_base_materials[line.item] * material_factor, 2)
            if line.material_cost > 0:
                line.material_markup_rate = markup

        self.labor_adjust_label.set(f"{self.labor_adjust_var.get():.0f}%")
        self.material_adjust_label.set(f"{self.material_adjust_var.get():.0f}%")
        self.markup_adjust_label.set(f"{self.markup_adjust_var.get():.0f}%")
        self.install_rate_label.set(f"${self.install_rate_var.get():.0f}/hr")
        self.pricing_confirm_var.set(False)
        self.draft.pricing_profile_confirmed = False
        self._refresh_lines()

    def auto_fill(self) -> None:
        if not self._sync_fields():
            return
        unpriced = sum(
            1 for line in self.draft.lines
            if line.included and line.material_cost == 0 and line.manual_add == 0 and sum(line.normalized_hours().values()) == 0
        )
        overwrite = False
        if unpriced == 0 and self.draft.lines:
            overwrite = messagebox.askyesno(
                "Rebuild provisional pricing",
                "Every included line already has pricing. Rebuild all lines from local history / best effort?\n\nChoose No to leave the current estimate unchanged.",
                parent=self,
            )
            if not overwrite:
                return
        summary = apply_auto_pricing(self.draft, overwrite=overwrite, collapse_generated=True)
        self.scope_confirm_var.set(False)
        self.pricing_confirm_var.set(False)
        self.tax_confirm_var.set(False)
        self._reset_tuning_baseline()
        self.labor_adjust_var.set(100.0)
        self.material_adjust_var.set(100.0)
        self.markup_adjust_var.set(self._current_markup_percent())
        self.install_rate_var.set(float(self.draft.labor_rates.get("I", 0.0) or 0.0))
        self._load_fields()
        self._refresh_lines()
        save_estimate(self.workspace, self.draft)
        messagebox.showinfo(
            "Best-effort pricing filled",
            f"Filled {summary.filled_lines} line(s).\n\n"
            f"From private local history: {summary.historical_lines}\n"
            f"From low-confidence fallback allowances: {summary.heuristic_lines}\n"
            f"Page-by-page review rows consolidated: {summary.collapsed_lines}\n\n"
            "These are provisional values. Review the scope, quantities, rates, tax, and finishes before confirming the bid.",
            parent=self,
        )

    def import_history(self) -> None:
        files = filedialog.askopenfilenames(
            parent=self,
            title="Choose historical JTI cost-detail PDFs",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not files:
            return
        imported = 0
        errors: list[str] = []
        for filename in files:
            try:
                import_cost_detail_pdf(filename)
                imported += 1
            except Exception as exc:
                errors.append(f"{Path(filename).name}: {exc}")
        count = len(load_historical_examples())
        self.history_status_var.set(f"{count} local historical pricing line(s) available")
        if errors:
            messagebox.showwarning(
                "Historical pricing import",
                f"Imported {imported} file(s). {len(errors)} could not be parsed.\n\n" + "\n".join(errors[:5]),
                parent=self,
            )
        else:
            messagebox.showinfo(
                "Historical pricing imported",
                f"Imported {imported} private cost-detail file(s). Auto-fill can now match new scope against {count} historical line(s).\n\nThe calibration files stay on this computer and are not committed to GitHub.",
                parent=self,
            )

    def _selected_index(self) -> int | None:
        selected = self.tree.selection()
        if not selected:
            return None
        try:
            return int(selected[0].split("-", 1)[1])
        except (IndexError, ValueError):
            return None

    def add_line(self) -> None:
        item = max((line.item for line in self.draft.lines), default=0) + 1
        line = EstimateLine(item=item, description="New scope item")
        self._edit_line_dialog(line, is_new=True)

    def edit_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("Estimate", "Select a scope item first.", parent=self)
            return
        self._edit_line_dialog(self.draft.lines[index], is_new=False)

    def remove_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        line = self.draft.lines[index]
        if not messagebox.askyesno("Remove scope item", f"Remove item {line.item}?\n\n{line.description}", parent=self):
            return
        del self.draft.lines[index]
        for number, row in enumerate(self.draft.lines, start=1):
            row.item = number
        self._reset_tuning_baseline()
        self._refresh_lines()

    def _edit_line_dialog(self, line: EstimateLine, *, is_new: bool) -> None:
        win = tk.Toplevel(self)
        win.title("Scope item")
        win.transient(self)
        win.grab_set()
        win.geometry("760x610")
        outer = ttk.Frame(win, padding=14)
        outer.pack(fill="both", expand=True)

        included_var = tk.BooleanVar(value=line.included)
        ttk.Checkbutton(outer, text="Include this item in the base quote", variable=included_var).pack(anchor="w")
        ttk.Label(outer, text="Description").pack(anchor="w", pady=(8, 2))
        desc = tk.Text(outer, height=5, wrap="word")
        desc.insert("1.0", line.description)
        desc.pack(fill="x")

        row = ttk.Frame(outer); row.pack(fill="x", pady=(8, 0))
        qty_var = tk.StringVar(value=f"{line.quantity:g}")
        material_var = tk.StringVar(value=f"{line.material_cost:g}")
        markup_var = tk.StringVar(value=f"{line.material_markup_rate * 100:g}")
        tax_var = tk.StringVar(value=f"{line.material_tax_rate * 100:g}")
        add_var = tk.StringVar(value=f"{line.manual_add:g}")
        code_var = tk.StringVar(value=line.code)
        for label, var, width in (("Qty", qty_var, 8), ("Material $", material_var, 12), ("Markup %", markup_var, 10), ("Material tax %", tax_var, 11), ("Manual add $", add_var, 11), ("Code", code_var, 9)):
            cell = ttk.Frame(row); cell.pack(side="left", padx=(0, 8))
            ttk.Label(cell, text=label).pack(anchor="w")
            ttk.Entry(cell, textvariable=var, width=width).pack()

        labor = ttk.LabelFrame(outer, text="Labor hours by JTI category", padding=8)
        labor.pack(fill="x", pady=(10, 0))
        hour_vars: dict[str, tk.StringVar] = {}
        current = line.normalized_hours()
        for col, category in enumerate(LABOR_CATEGORIES):
            ttk.Label(labor, text=category).grid(row=0, column=col, sticky="w")
            var = tk.StringVar(value=f"{current[category]:g}")
            hour_vars[category] = var
            ttk.Entry(labor, textvariable=var, width=9).grid(row=1, column=col, padx=(0, 6))

        ttk.Label(outer, text="Evidence / drawing references (one per line)").pack(anchor="w", pady=(10, 2))
        refs = tk.Text(outer, height=4, wrap="word")
        refs.insert("1.0", "\n".join(line.source_refs))
        refs.pack(fill="x")
        ttk.Label(outer, text="Estimator note (internal only)").pack(anchor="w", pady=(8, 2))
        note = tk.Text(outer, height=3, wrap="word")
        note.insert("1.0", line.estimator_note)
        note.pack(fill="x")

        ttk.Label(
            outer,
            text="Auto-filled pricing and the historical 60% material-markup pattern are starting points only. Edit anything that does not match the current scope or market.",
            wraplength=700,
        ).pack(anchor="w", pady=(8, 0))

        buttons = ttk.Frame(outer); buttons.pack(fill="x", pady=(12, 0))

        def accept() -> None:
            try:
                quantity = float(qty_var.get().strip())
                material = float(material_var.get().strip() or 0)
                markup = float(markup_var.get().strip() or 0) / 100.0
                tax = float(tax_var.get().strip() or 0) / 100.0
                manual_add = float(add_var.get().strip() or 0)
                hours = {category: float(hour_vars[category].get().strip() or 0) for category in LABOR_CATEGORIES}
            except ValueError:
                messagebox.showerror("Scope item", "Qty, costs, percentages, and labor hours must be numbers.", parent=win)
                return
            if quantity <= 0:
                messagebox.showerror("Scope item", "Quantity must be greater than zero.", parent=win)
                return
            line.description = desc.get("1.0", "end").strip()
            line.quantity = quantity
            line.material_cost = material
            line.material_markup_rate = markup
            line.material_tax_rate = tax
            line.manual_add = manual_add
            line.code = code_var.get().strip().upper() or "MILL"
            line.labor_hours = hours
            line.source_refs = [value.strip() for value in refs.get("1.0", "end").splitlines() if value.strip()]
            line.estimator_note = note.get("1.0", "end").strip()
            line.included = bool(included_var.get())
            if is_new:
                self.draft.lines.append(line)
            self._reset_tuning_baseline()
            self.labor_adjust_var.set(100.0)
            self.material_adjust_var.set(100.0)
            self.markup_adjust_var.set(self._current_markup_percent())
            self._refresh_lines()
            win.destroy()

        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(buttons, text="Save scope item", command=accept).pack(side="right", padx=8)

    def save(self) -> bool:
        if not self._sync_fields():
            return False
        save_estimate(self.workspace, self.draft)
        self._refresh_lines()
        self.warning_var.set("Estimate saved. " + self.warning_var.get())
        return True

    def generate_preview(self) -> None:
        if not self.save():
            return
        html_path, pdf_path = write_quote_preview(self.workspace, self.draft)
        warnings = self.draft.warnings()
        if warnings:
            messagebox.showwarning(
                "Draft JTI quote created",
                f"A JTI-formatted quote was created, but it is marked DRAFT because {len(warnings)} item(s) still need attention.\n\nFirst issue: {warnings[0]}",
                parent=self,
            )
        else:
            messagebox.showinfo(
                "JTI quote ready",
                "The quote passed the current scope/pricing review gates and was formatted in the familiar JTI quote structure. It still requires estimator final review before submission.",
                parent=self,
            )
        if self.open_path is not None:
            self.open_path(pdf_path)
        else:
            webbrowser.open(html_path.resolve().as_uri())


def launch_estimator(parent: tk.Misc, workspace: str | Path, open_path=None) -> EstimateWizard:
    return EstimateWizard(parent, workspace, open_path=open_path)
