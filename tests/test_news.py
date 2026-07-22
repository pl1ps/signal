from types import SimpleNamespace

from pipeline.sources import news


def fake_parser(url):
    # feedparser exposes the parsed date as published_parsed, a 9-field
    # struct_time; a plain tuple behaves the same for our purposes.
    return SimpleNamespace(entries=[
        SimpleNamespace(title="Global summit opens",
                        link="https://bbc.co.uk/news/1",
                        summary="Leaders meet to discuss trade.",
                        published_parsed=(2026, 7, 22, 5, 0, 0, 0, 0, 0)),
        SimpleNamespace(title="Second story",
                        link="https://bbc.co.uk/news/2",
                        summary="More detail.",
                        published_parsed=None),
    ])


def test_fetch_maps_entries_to_items_and_respects_per_feed():
    items = news.fetch([("BBC World", "https://example.com/rss")],
                       per_feed=1, parser=fake_parser)

    assert len(items) == 1
    assert items[0].title == "Global summit opens"
    assert items[0].source == "news"
    assert items[0].source_label == "BBC World"
    assert items[0].snippet == "Leaders meet to discuss trade."
    assert items[0].signal_metric == ""
    assert items[0].published_at == "2026-07-22T05:00:00Z"


def test_fetch_leaves_published_at_blank_when_feed_has_no_date():
    items = news.fetch([("BBC World", "https://example.com/rss")],
                       per_feed=2, parser=fake_parser)
    assert items[1].published_at == ""


def test_fetch_reads_every_feed():
    feeds = [("BBC World", "https://a"), ("NPR News", "https://b")]
    items = news.fetch(feeds, per_feed=2, parser=fake_parser)
    assert len(items) == 4
    assert {i.source_label for i in items} == {"BBC World", "NPR News"}
