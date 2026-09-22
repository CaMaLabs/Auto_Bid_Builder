from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from statistics import median
from typing import Any, Iterable

from ..settings import DEFAULT_HOME
from .cost_detail import parse_cost_detail_pdf
from .draft import (
    HISTORICAL_STARTER_MATERIAL_MARKUP,
    LABOR_CATEGORIES,
    EstimateDraft,
    EstimateLine,
)


CALIBRATION_DIR = DEFAULT_HOME / "calibration" / "cost_details"

# These are deliberately generic, low-confidence estimating allowances rather than
# published JTI historical job prices. Real historical cost-detail data stays local
# in the user's calibration folder and is preferred whenever a reasonable match is
# available.
_FALLBACK_RULES: tuple[tuple[tuple[str, ...], dict[str, float], float, str], ...] = (
    (("casework", "cabinet", "cabinetry"), {"M": 3.0, "A": 2.0, "F": 1.0, "H": 0.5, "S": 0.5, "I": 3.0}, 650.0, "casework/cabinetry"),
    (("counter", "countertop", "worktop"), {"M": 1.0, "A": 1.0, "F": 0.5, "I": 1.5}, 450.0, "counter/worktop"),
    (("veneer", "panel", "wall panel"), {"M": 2.0, "A": 1.5, "F": 1.0, "H": 0.25, "S": 0.25, "I": 2.5}, 375.0, "panel/veneer"),
    (("shelf", "shelving", "floating shelf"), {"M": 0.75, "A": 0.5, "F": 0.25, "I": 0.75}, 125.0, "shelving"),
    (("fixture", "display", "cashwrap", "backwrap"), {"E": 0.5, "M": 2.5, "P": 0.5, "A": 2.0, "F": 1.0, "I": 2.0}, 550.0, "fixture/display"),
    (("millwork", "woodwork", "finish carpentry"), {"M": 1.5, "A": 1.0, "F": 0.5, "I": 1.5}, 300.0, "general millwork"),
)

_STOPWORDS = {
    "the", "and", "or", "of", "to", "for", "a", "an", "in", "on", "at", "by",
    "with", "from", "shown", "review", "scope", "detected", "page", "drawing", "drawings",
    "project", "manual", "pdf", "bid", "document", "documents", "related", "content",
}

_SCOPE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("casework/cabinetry", ("casework", "cabinet", "cabinetry")),
    ("counters/worktops", ("counter", "countertop", "worktop")),
    ("panels/veneer", ("panel", "veneer", "wall panel")),
    ("shelving", ("shelf", "shelving", "floating shelf")),
    ("fixtures/displays", ("fixture", "display", "cashwrap", "backwrap")),
    ("general millwork", ("millwork", "woodwork", "finish carpentry")),
)


@dataclass(frozen=True)
class HistoricalExample:
    description: str
    quantity: float
    labor_hours: dict[str, float]
    material_cost: float
    markup_rate: float | None
    tax_rate: float | None
    manual_add: float
    code: str
    source: str


@dataclass(frozen=True)
class AutoPriceSummary:
    filled_lines: int = 0
    historical_lines: int = 0
    heuristic_lines: int = 0
    collapsed_lines: int = 0
    history_examples: int = 0
    tax_rate_inferred: float | None = None
    install_rate_inferred: float | None = None


def _tokens(text: str) -> set[str]:
    words = {x.lower() for x in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text)}
    return {x for x in words if x not in _STOPWORDS}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return default


def _json_files(directory: str | Path | None = None) -> Iterable[Path]:
    root = Path(directory) if directory is not None else CALIBRATION_DIR
    if not root.exists():
        return ()
    return tuple(sorted(root.glob("*.json")))


def load_historical_examples(directory: str | Path | None = None) -> list[HistoricalExample]:
    examples: list[HistoricalExample] = []
    for path in _json_files(directory):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in payload.get("lines", []):
            qty = _safe_float(row.get("quantity"), 1.0)
            if qty <= 0:
                continue
            status = str(row.get("inclusion_status") or "base")
            if status in {"removed", "not_included", "alternate_not_selected"}:
                continue
            description = str(row.get("description") or "").strip()
            if not description:
                continue
            projected = {
                code: _safe_float((row.get("projected_hours") or {}).get(code))
                for code in LABOR_CATEGORIES
            }
            material = _safe_float(row.get("materials_each"))
            markup = row.get("markup_rate_on_materials")
            if markup is None and material > 0:
                markup = _safe_float(row.get("markup_each")) / material
            tax = row.get("tax_rate_on_materials")
            if tax is None and material > 0:
                tax = _safe_float(row.get("tax_each")) / material
            examples.append(
                HistoricalExample(
                    description=description,
                    quantity=qty,
                    labor_hours=projected,
                    material_cost=material,
                    markup_rate=None if markup is None else _safe_float(markup),
                    tax_rate=None if tax is None else _safe_float(tax),
                    manual_add=_safe_float(row.get("add_each")),
                    code=str(row.get("code") or "MILL").upper(),
                    source=path.name,
                )
            )
    return examples


def import_cost_detail_pdf(path: str | Path, directory: str | Path | None = None) -> Path:
    """Parse one private historical cost-detail PDF into the local calibration library.

    Nothing is uploaded or committed. The parsed JSON remains under the user's
    Auto Bid Builder application-data directory unless an alternate directory is
    explicitly supplied.
    """
    source = Path(path)
    doc = parse_cost_detail_pdf(source)
    root = Path(directory) if directory is not None else CALIBRATION_DIR
    root.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", source.stem).strip("_") or "cost_detail"
    target = root / f"{stem}.json"
    suffix = 2
    while target.exists():
        target = root / f"{stem}_{suffix}.json"
        suffix += 1
    target.write_text(json.dumps(doc.to_dict(), indent=2), encoding="utf-8")
    return target


def _similarity(description: str, example: HistoricalExample) -> float:
    current = _tokens(description)
    prior = _tokens(example.description)
    if not current or not prior:
        return 0.0
    intersection = len(current & prior)
    if not intersection:
        return 0.0
    cosine_like = intersection / math.sqrt(len(current) * len(prior))
    anchor_bonus = 0.0
    lower_current = description.lower()
    lower_prior = example.description.lower()
    for _label, anchors in _SCOPE_GROUPS:
        if any(term in lower_current for term in anchors) and any(term in lower_prior for term in anchors):
            anchor_bonus = 0.18
            break
    return min(1.0, cosine_like + anchor_bonus)


def _weighted(values: list[tuple[float, float]]) -> float:
    total_weight = sum(weight for weight, _value in values)
    if total_weight <= 0:
        return 0.0
    return sum(weight * value for weight, value in values) / total_weight


def _evidence_scale(line: EstimateLine) -> float:
    count = max(1, len(line.source_refs))
    return min(3.0, max(1.0, math.sqrt(count)))


def _historical_result(line: EstimateLine, examples: list[HistoricalExample]) -> tuple[dict[str, float], float, float, float, float, str, str] | None:
    scored = sorted(
        ((score, example) for example in examples if (score := _similarity(line.description, example)) >= 0.18),
        key=lambda item: item[0],
        reverse=True,
    )[:4]
    if not scored:
        return None
    scale = _evidence_scale(line)
    hours = {
        code: round(_weighted([(score, ex.labor_hours.get(code, 0.0)) for score, ex in scored]) * scale, 2)
        for code in LABOR_CATEGORIES
    }
    material = round(_weighted([(score, ex.material_cost) for score, ex in scored]) * scale, 2)
    add = round(_weighted([(score, ex.manual_add) for score, ex in scored]) * scale, 2)
    markups = [(score, ex.markup_rate) for score, ex in scored if ex.markup_rate is not None]
    taxes = [(score, ex.tax_rate) for score, ex in scored if ex.tax_rate is not None]
    markup = _weighted([(w, float(v)) for w, v in markups]) if markups else HISTORICAL_STARTER_MATERIAL_MARKUP
    tax = _weighted([(w, float(v)) for w, v in taxes]) if taxes else 0.0
    code_weights: dict[str, float] = {}
    for score, ex in scored:
        code_weights[ex.code] = code_weights.get(ex.code, 0.0) + score
    code = max(code_weights, key=code_weights.get) if code_weights else "MILL"
    best = scored[0][0]
    confidence = "high" if best >= 0.62 and len(scored) >= 2 else "medium" if best >= 0.36 else "low"
    source = f"private local history ({len(scored)} similar line{'s' if len(scored) != 1 else ''})"
    return hours, material, markup, tax, add, code, f"{source}; {confidence} confidence"


def _heuristic_result(line: EstimateLine) -> tuple[dict[str, float], float, float, float, float, str, str]:
    text = line.description.lower()
    selected = None
    for anchors, hours, material, label in _FALLBACK_RULES:
        if any(anchor in text for anchor in anchors):
            selected = (hours, material, label)
            break
    if selected is None:
        selected = ({"M": 1.0, "A": 0.75, "F": 0.25, "I": 1.0}, 225.0, "unclassified millwork")
    base_hours, base_material, label = selected
    scale = _evidence_scale(line)
    hours = {code: round(_safe_float(base_hours.get(code)) * scale, 2) for code in LABOR_CATEGORIES}
    material = round(base_material * scale, 2)
    return hours, material, HISTORICAL_STARTER_MATERIAL_MARKUP, 0.0, 0.0, "MILL", f"best-effort {label} allowance; low confidence"


def historical_profile(examples: list[HistoricalExample]) -> tuple[dict[str, float], float | None, float | None]:
    rates: dict[str, list[float]] = {code: [] for code in LABOR_CATEGORIES}
    tax_values: list[float] = []
    markup_values: list[float] = []

    # Labor rates are not carried on HistoricalExample because a line's projected
    # hours and dollars are enough for matching. Read document calibration metadata
    # separately below when available.
    for path in _json_files():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        calibration = payload.get("inferred_calibration") or {}
        for code, value in (calibration.get("labor_rates_by_code") or {}).items():
            value = _safe_float(value)
            if code in rates and value > 0:
                rates[code].append(value)
        value = calibration.get("material_tax_rate")
        if value is not None and _safe_float(value) > 0:
            tax_values.append(_safe_float(value))
        value = calibration.get("material_markup_rate")
        if value is not None and _safe_float(value) > 0:
            markup_values.append(_safe_float(value))
    inferred_rates = {code: median(values) for code, values in rates.items() if values}
    return inferred_rates, (median(markup_values) if markup_values else None), (median(tax_values) if tax_values else None)


def _category_for_description(description: str) -> str:
    text = description.lower()
    for label, anchors in _SCOPE_GROUPS:
        if any(anchor in text for anchor in anchors):
            return label
    return "other millwork"


def consolidate_generated_review_lines(draft: EstimateDraft) -> int:
    """Collapse page-by-page zero-dollar review suggestions into scope allowances.

    Existing user-entered or already-priced lines are never collapsed.
    """
    generated = [
        line for line in draft.lines
        if line.description.lower().startswith("review scope")
        and line.material_cost == 0
        and line.manual_add == 0
        and sum(line.normalized_hours().values()) == 0
    ]
    if len(generated) < 3 or len(generated) != len(draft.lines):
        return 0

    groups: dict[str, list[EstimateLine]] = {}
    for line in generated:
        groups.setdefault(_category_for_description(line.description), []).append(line)

    collapsed: list[EstimateLine] = []
    for item, (label, rows) in enumerate(groups.items(), start=1):
        refs: list[str] = []
        for row in rows:
            for ref in row.source_refs:
                if ref not in refs:
                    refs.append(ref)
        collapsed.append(
            EstimateLine(
                item=item,
                description=(
                    f"Provisional {label} allowance — detected across {len(refs) or len(rows)} "
                    "drawing/spec reference(s). Verify actual takeoff, dimensions, finish, and quantity before bid."
                ),
                quantity=1.0,
                source_refs=refs,
            )
        )
    old_count = len(draft.lines)
    draft.lines = collapsed
    return old_count - len(collapsed)


def apply_auto_pricing(
    draft: EstimateDraft,
    *,
    overwrite: bool = False,
    calibration_dir: str | Path | None = None,
    collapse_generated: bool = True,
) -> AutoPriceSummary:
    """Fill zero-dollar estimate lines using local history first, then heuristics.

    Existing non-zero estimator-entered values are preserved unless overwrite=True.
    Any automatic fill clears the pricing/tax confirmations so a human has to review
    the generated values before the quote can become ready.
    """
    collapsed = consolidate_generated_review_lines(draft) if collapse_generated else 0
    examples = load_historical_examples(calibration_dir)

    # Use locally imported historical rate/tax medians where available. Non-zero
    # estimator-entered labor rates always win.
    inferred_rates: dict[str, float] = {}
    inferred_markup: float | None = None
    inferred_tax: float | None = None
    if calibration_dir is None:
        inferred_rates, inferred_markup, inferred_tax = historical_profile(examples)
    else:
        # Tests and alternate private libraries still get line matching; profile
        # inference is intentionally limited to the app's normal private library.
        pass
    for code, rate in inferred_rates.items():
        if overwrite or float(draft.labor_rates.get(code, 0.0) or 0.0) <= 0:
            draft.labor_rates[code] = round(rate, 2)

    filled = historical = heuristic = 0
    for line in draft.lines:
        if not line.included:
            continue
        currently_unpriced = (
            line.material_cost == 0
            and line.manual_add == 0
            and sum(line.normalized_hours().values()) == 0
        )
        if not overwrite and not currently_unpriced:
            continue
        result = _historical_result(line, examples)
        if result is not None:
            hours, material, markup, tax, add, code, source = result
            historical += 1
        else:
            hours, material, markup, tax, add, code, source = _heuristic_result(line)
            if inferred_tax is not None:
                tax = inferred_tax
            if inferred_markup is not None:
                markup = inferred_markup
            heuristic += 1
        line.labor_hours = hours
        line.material_cost = material
        line.material_markup_rate = markup
        line.material_tax_rate = tax
        line.manual_add = add
        line.code = code
        note = f"AUTO-PRICED: {source}. Review before submission."
        if note not in line.estimator_note:
            line.estimator_note = (line.estimator_note + "\n" + note).strip()
        filled += 1

    if filled:
        draft.pricing_profile_confirmed = False
        draft.tax_rate_confirmed = False

    return AutoPriceSummary(
        filled_lines=filled,
        historical_lines=historical,
        heuristic_lines=heuristic,
        collapsed_lines=collapsed,
        history_examples=len(examples),
        tax_rate_inferred=inferred_tax,
        install_rate_inferred=inferred_rates.get("I"),
    )
