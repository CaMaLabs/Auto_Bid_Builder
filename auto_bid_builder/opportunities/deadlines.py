from __future__ import annotations

from datetime import date, datetime, time, timezone


def parse_deadline(value: str | None) -> datetime | date | None:
    text = str(value or "").strip()
    if not text:
        return None

    cleaned = text.replace("Z", "+00:00")
    try:
        if "T" in cleaned or " " in cleaned:
            return datetime.fromisoformat(cleaned)
        return date.fromisoformat(cleaned[:10])
    except ValueError:
        pass

    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M %p", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt == "%m/%d/%Y":
                return parsed.date()
            return parsed
        except ValueError:
            continue
    return None


def is_past_due(value: str | None, *, now: datetime | None = None) -> bool:
    """Return True only when a supplied, parseable response deadline has passed.

    Date-only deadlines remain valid through the entire named date. Unknown or
    malformed deadlines are retained for estimator review rather than silently
    discarded.
    """
    parsed = parse_deadline(value)
    if parsed is None:
        return False

    current = now or datetime.now().astimezone()
    if isinstance(parsed, datetime):
        if parsed.tzinfo is not None:
            if current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc) < current.astimezone(timezone.utc)
        return parsed < current.replace(tzinfo=None)

    return parsed < current.date()
