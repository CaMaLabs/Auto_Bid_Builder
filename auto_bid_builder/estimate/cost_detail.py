from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from statistics import median
from typing import Any

import pdfplumber


LABOR_CODES = ("E", "M", "P", "A", "F", "H", "S", "I")


@dataclass(frozen=True)
class CostDetailLine:
    item: int
    quantity: float
    description: str
    projected_hours: dict[str, float]
    actual_hours: dict[str, float]
    labor_rates: dict[str, float]
    labor_each: float
    materials_each: float
    markup_each: float
    add_each: float
    code: str
    tax_each: float
    sell_each: float
    item_total: float

    @property
    def calculated_labor_each(self) -> float:
        return round(sum(self.projected_hours[k] * self.labor_rates[k] for k in LABOR_CODES), 2)

    @property
    def calculated_sell_each(self) -> float:
        return round(
            self.labor_each + self.materials_each + self.markup_each + self.add_each + self.tax_each,
            2,
        )

    @property
    def calculated_item_total(self) -> float:
        return round(self.quantity * self.sell_each, 2)

    @property
    def markup_rate_on_materials(self) -> float | None:
        if not self.materials_each:
            return None
        return self.markup_each / self.materials_each

    @property
    def tax_rate_on_materials(self) -> float | None:
        if not self.materials_each:
            return None
        return self.tax_each / self.materials_each

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(
            calculated_labor_each=self.calculated_labor_each,
            calculated_sell_each=self.calculated_sell_each,
            calculated_item_total=self.calculated_item_total,
            labor_matches_display=abs(self.calculated_labor_each - self.labor_each) <= 0.01,
            sell_each_matches_display=abs(self.calculated_sell_each - self.sell_each) <= 0.01,
            item_total_matches_display=abs(self.calculated_item_total - self.item_total) <= 0.01,
            markup_rate_on_materials=self.markup_rate_on_materials,
            tax_rate_on_materials=self.tax_rate_on_materials,
        )
        return data


@dataclass(frozen=True)
class CostDetailTotals:
    hours: float | None = None
    actual_hours: float | None = None
    labor: float | None = None
    materials: float | None = None
    markup: float | None = None
    add: float | None = None
    tax: float | None = None
    job_total: float | None = None


@dataclass(frozen=True)
class CostDetailDocument:
    job_number: str | None
    job_name: str | None
    terms: str | None
    rep: str | None
    lines: tuple[CostDetailLine, ...]
    displayed_totals: CostDetailTotals = field(default_factory=CostDetailTotals)

    @property
    def calculated_totals(self) -> CostDetailTotals:
        return CostDetailTotals(
            hours=round(sum(line.quantity * sum(line.projected_hours.values()) for line in self.lines), 2),
            actual_hours=round(sum(line.quantity * sum(line.actual_hours.values()) for line in self.lines), 2),
            labor=round(sum(line.quantity * line.labor_each for line in self.lines), 2),
            materials=round(sum(line.quantity * line.materials_each for line in self.lines), 2),
            markup=round(sum(line.quantity * line.markup_each for line in self.lines), 2),
            add=round(sum(line.quantity * line.add_each for line in self.lines), 2),
            tax=round(sum(line.quantity * line.tax_each for line in self.lines), 2),
            job_total=round(sum(line.item_total for line in self.lines), 2),
        )

    @property
    def inferred_labor_rates(self) -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        for code in LABOR_CODES:
            values = [line.labor_rates[code] for line in self.lines if code in line.labor_rates]
            out[code] = median(values) if values else None
        return out

    @property
    def inferred_material_markup_rate(self) -> float | None:
        values = [x.markup_rate_on_materials for x in self.lines if x.markup_rate_on_materials is not None]
        return median(values) if values else None

    @property
    def inferred_material_tax_rate(self) -> float | None:
        values = [x.tax_rate_on_materials for x in self.lines if x.tax_rate_on_materials is not None]
        return median(values) if values else None

    def to_dict(self) -> dict[str, Any]:
        calculated = self.calculated_totals
        displayed = self.displayed_totals
        return {
            "job_number": self.job_number,
            "job_name": self.job_name,
            "terms": self.terms,
            "rep": self.rep,
            "lines": [line.to_dict() for line in self.lines],
            "displayed_totals": asdict(displayed),
            "calculated_totals": asdict(calculated),
            "inferred_calibration": {
                "labor_rates_by_code": self.inferred_labor_rates,
                "material_markup_rate": self.inferred_material_markup_rate,
                "material_tax_rate": self.inferred_material_tax_rate,
            },
            "totals_match_display": _totals_match(calculated, displayed),
        }


_PAGE_HEADER_RE = re.compile(r"(?m)^JOB\s+\d+\s+COST DETAIL.*?Page\s+\d+\s*$")
_JOB_HEADER_RE = re.compile(r"(?m)^JOB\s+(?P<name>.+?)\s+(?P<terms>\d+(?:/\d+){1,5})\s+(?P<rep>[A-Z]{1,6})\s*$")
_JOB_NUMBER_RE = re.compile(r"\bJOB\s+(\d+)\s+COST DETAIL\b", re.I)

_LINE_RE = re.compile(
    r"Item\s+Qty\s+Description\s+"
    r"(?P<item>\d+)\s+(?P<qty>\d+(?:\.\d+)?)\s+(?P<desc>.*?)"
    r"E\s+M\s+P\s+A\s+F\s+H\s+S\s+I\s+Hours\s+Each\s*"
    r"(?P<hours>(?:-?\d+(?:\.\d+)?\s+){8}-?\d+(?:\.\d+)?)\s*"
    r"(?P<actual>(?:-?\d+(?:\.\d+)?\s+){8}-?\d+(?:\.\d+)?)\s*"
    r"(?P<rates>(?:-?\d+(?:\.\d+)?\s+){7}-?\d+(?:\.\d+)?)\s*"
    r"Labor\s+Materials\s+Markup\s+Add\s+Code\s+Tax\s+Each\s+Each\s+Item\s+Total\s*"
    r"(?P<labor>-?\d+\.\d{2})\s+(?P<materials>-?\d+\.\d{2})\s+"
    r"(?P<markup>-?\d+\.\d{2})\s+(?P<add>-?\d+\.\d{2})\s+"
    r"(?P<code>[A-Z]{1,8})\s+(?P<tax>-?\d+\.\d{2})\s+"
    r"(?P<each>-?\d+\.\d{2})\s+(?P<total>-?\d+\.\d{2})",
    re.I | re.S,
)

_TOTAL_RE = re.compile(
    r"Hours\s+Actual\s+Labor\s+Materials\s+Markup\s+Add\s+Tax\s+Job\s+Total\s*"
    r"(?P<hours>-?\d+(?:\.\d+)?)\s+(?P<actual>-?\d+(?:\.\d+)?)\s+"
    r"(?P<labor>-?\d+\.\d{2})\s+(?P<materials>-?\d+\.\d{2})\s+"
    r"(?P<markup>-?\d+\.\d{2})\s+(?P<add>-?\d+\.\d{2})\s+"
    r"(?P<tax>-?\d+\.\d{2})\s+(?P<total>-?\d+\.\d{2})",
    re.I,
)


def _clean(text: str) -> str:
    return " ".join(text.split())


def _eight(values: str) -> dict[str, float]:
    nums = [float(x) for x in values.split()]
    if len(nums) < 8:
        raise ValueError("expected eight labor-category values")
    return dict(zip(LABOR_CODES, nums[:8]))


def _totals_match(calculated: CostDetailTotals, displayed: CostDetailTotals) -> bool | None:
    checked = 0
    for key in ("hours", "actual_hours", "labor", "materials", "markup", "add", "tax", "job_total"):
        a = getattr(calculated, key)
        b = getattr(displayed, key)
        if b is None:
            continue
        checked += 1
        tolerance = 0.11 if key in {"hours", "actual_hours"} else 0.01
        if a is None or abs(a - b) > tolerance:
            return False
    return True if checked else None


def parse_cost_detail_text(text: str) -> CostDetailDocument:
    job_number_match = _JOB_NUMBER_RE.search(text)
    clean = _PAGE_HEADER_RE.sub("", text)
    header = _JOB_HEADER_RE.search(clean)

    lines: list[CostDetailLine] = []
    for match in _LINE_RE.finditer(clean):
        hours = _eight(match.group("hours"))
        actual = _eight(match.group("actual"))
        rates = _eight(match.group("rates"))
        lines.append(
            CostDetailLine(
                item=int(match.group("item")),
                quantity=float(match.group("qty")),
                description=_clean(match.group("desc")),
                projected_hours=hours,
                actual_hours=actual,
                labor_rates=rates,
                labor_each=float(match.group("labor")),
                materials_each=float(match.group("materials")),
                markup_each=float(match.group("markup")),
                add_each=float(match.group("add")),
                code=match.group("code").upper(),
                tax_each=float(match.group("tax")),
                sell_each=float(match.group("each")),
                item_total=float(match.group("total")),
            )
        )

    total_match = _TOTAL_RE.search(clean)
    totals = CostDetailTotals()
    if total_match:
        totals = CostDetailTotals(
            hours=float(total_match.group("hours")),
            actual_hours=float(total_match.group("actual")),
            labor=float(total_match.group("labor")),
            materials=float(total_match.group("materials")),
            markup=float(total_match.group("markup")),
            add=float(total_match.group("add")),
            tax=float(total_match.group("tax")),
            job_total=float(total_match.group("total")),
        )

    return CostDetailDocument(
        job_number=job_number_match.group(1) if job_number_match else None,
        job_name=_clean(header.group("name")) if header else None,
        terms=header.group("terms") if header else None,
        rep=header.group("rep") if header else None,
        lines=tuple(lines),
        displayed_totals=totals,
    )


def parse_cost_detail_pdf(path: str | Path) -> CostDetailDocument:
    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text(x_tolerance=1, y_tolerance=3) or "")
    return parse_cost_detail_text("\n".join(chunks))
