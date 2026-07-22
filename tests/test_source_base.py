from pipeline.sources import base
from pipeline.sources.base import fetch_safe


def test_fetch_safe_returns_items_and_true_on_success():
    items, ok = fetch_safe("demo", lambda: ["a", "b"])
    assert items == ["a", "b"]
    assert ok is True


def test_fetch_safe_swallows_exception_and_reports_failure():
    def boom():
        raise RuntimeError("network down")

    items, ok = fetch_safe("demo", boom)
    assert items == []
    assert ok is False


def test_iso_from_epoch_formats_as_utc_z():
    assert base.iso_from_epoch(1_000_000_000) == "2001-09-09T01:46:40Z"


def test_iso_from_epoch_returns_blank_for_missing_timestamp():
    assert base.iso_from_epoch(None) == ""
    assert base.iso_from_epoch(0) == ""


def test_iso_from_feed_time_formats_as_utc_z():
    assert base.iso_from_feed_time((2026, 7, 22, 5, 0, 0, 0, 0, 0)) == "2026-07-22T05:00:00Z"


def test_iso_from_feed_time_returns_blank_when_absent():
    assert base.iso_from_feed_time(None) == ""
