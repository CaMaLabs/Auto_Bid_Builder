from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

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

    The wizard intentionally keeps historical starter rates visibly provisional.  It
    will create a quote preview at any time, but the preview remains marked DRAFT until
    scope, pricing, and tax review gates are complete.
    """

    def __init__(self, parent: tk.Misc, workspace: str | Path, open_path=None) -> None:
        super().__init__(parent)
        self.workspace = Path(workspace)
        self.open_path = open_path
        self.draft = load_estimate(self.workspace) or create_estimate_from_workspace(self.workspace)
        self.title("Build Estimate - Auto Bid Builder")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.transient(parent)
        self._build_ui()
        self._load_fields()
        self._refresh_lines()

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
            text="Historical starter values are prefilled from JTI cost-detail examples. Confirm the current bid's rates before treating the preview as ready. Installation starts at $0 because historical I rates varied by job.",
            wraplength=1080,
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

        lines_frame = ttk.LabelFrame(self, text="3. Scope and pricing lines", padding=8)
        lines_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        toolbar = ttk.Frame(lines_frame)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(toolbar, text="Add scope item", command=self.add_line).pack(side="left")
        ttk.Button(toolbar, text="Edit selected", command=self.edit_selected).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Remove selected", command=self.remove_selected).pack(side="left")
        ttk.Label(toolbar, text="Double-click a row to edit it. Imported scope lines are suggestions until an estimator accepts them.").pack(side="right")

        columns = ("item", "included", "description", "qty", "labor", "material", "markup", "tax", "amount")
        self.tree = ttk.Treeview(lines_frame, columns=columns, show="headings", selectmode="browse", height=12)
        headings = {
            "item": "#", "included": "In?", "description": "Description", "qty": "Qty", "labor": "Labor",
            "material": "Material", "markup": "Markup", "tax": "Tax", "amount": "Amount",
        }
        widths = {"item": 42, "included": 45, "description": 430, "qty": 60, "labor": 95, "material": 95, "markup": 90, "tax": 80, "amount": 105}
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
        ttk.Label(bottom, textvariable=self.warning_var, wraplength=720).pack(side="left", fill="x", expand=True)
        ttk.Button(bottom, text="Save", command=self.save).pack(side="right")
        ttk.Button(bottom, text="Generate quote preview", command=self.generate_preview).pack(side="right", padx=8)

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
            self.warning_var.set("✓ Scope, pricing, and tax gates are complete. Preview is ready for estimator final review.")

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
            text="Material markup starts at the historical 60% pattern learned from prior JTI cost-detail reports. Change it when this bid requires something else.",
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
                "Draft quote created",
                f"A quote preview was created, but it is marked DRAFT because {len(warnings)} item(s) still need attention.\n\nFirst issue: {warnings[0]}",
                parent=self,
            )
        else:
            messagebox.showinfo(
                "Quote preview ready",
                "The quote preview passed the current scope/pricing review gates. It still requires estimator final review before submission.",
                parent=self,
            )
        if self.open_path is not None:
            self.open_path(pdf_path)
        else:
            webbrowser.open(html_path.resolve().as_uri())


def launch_estimator(parent: tk.Misc, workspace: str | Path, open_path=None) -> EstimateWizard:
    return EstimateWizard(parent, workspace, open_path=open_path)
