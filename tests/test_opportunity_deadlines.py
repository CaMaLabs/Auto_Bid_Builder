from datetime import datetime, timezone

from auto_bid_builder.opportunities.deadlines import is_past_due


NOW = datetime(2026, 11, 2, 20, 0, tzinfo=timezone.utc)


def test_past_due_iso_timestamp_is_rejected():
    assert is_past_due("2026-11-02T11:00:00-08:00", now=NOW)


def test_future_iso_timestamp_is_kept():
    assert not is_past_due("2026-11-02T13:00:00-08:00", now=NOW)


def test_date_only_deadline_remains_valid_through_that_date():
    assert not is_past_due("2026-11-02", now=NOW)
    assert is_past_due("2026-11-01", now=NOW)


def test_missing_or_unparseable_deadline_is_not_silently_dropped():
    assert not is_past_due(None, now=NOW)
    assert not is_past_due("TBD", now=NOW)
