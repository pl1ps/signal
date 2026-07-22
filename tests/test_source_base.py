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
