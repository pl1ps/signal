from pipeline.models import Item, Digest


def test_item_to_dict_nests_signal_and_rounds_relevance():
    item = Item(
        title="Tool use for small models",
        url="https://example.com/a",
        source="hackernews",
        source_label="Hacker News",
        signal_metric="points",
        signal_value=340,
        why="Cheaper agents.",
        summary="A short summary.",
        relevance=0.8249,
    )
    d = item.to_dict()
    assert d["signal"] == {"metric": "points", "value": 340}
    assert d["relevance"] == 0.825
    assert "prescore" not in d          # internal only, never published
    assert "snippet" not in d


def test_digest_to_dict_shape():
    digest = Digest(
        generated_at="2026-07-22T06:17:00Z",
        sections=[{"id": "world", "title": "World", "items": []}],
        scanned=412,
        kept=8,
        levels=[{"v": 0.1, "kept": False}],
        sources_ok=["hackernews"],
        sources_failed=["reddit"],
        ai_used=True,
    )
    d = digest.to_dict()
    assert d["generator_version"] == 1
    assert d["readout"] == {"scanned": 412, "kept": 8, "levels": [{"v": 0.1, "kept": False}]}
    assert d["status"]["sources_failed"] == ["reddit"]
