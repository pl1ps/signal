from pipeline.sources import hackernews


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    """Serves canned responses keyed by URL substring."""

    def __init__(self, routes):
        self.routes = routes

    def get(self, url, timeout=None, **kwargs):
        for key, payload in self.routes.items():
            if key in url:
                return FakeResponse(payload)
        raise AssertionError(f"unexpected url {url}")


def test_fetch_keeps_popular_stories_and_drops_quiet_ones():
    session = FakeSession({
        "topstories.json": [1, 2],
        "item/1.json": {
            "type": "story", "title": "Big AI release",
            "url": "https://example.com/ai", "score": 340, "time": 1753156620,
        },
        "item/2.json": {
            "type": "story", "title": "Quiet post",
            "url": "https://example.com/quiet", "score": 3, "time": 1753156620,
        },
    })

    items = hackernews.fetch(limit=2, session=session)

    assert len(items) == 1
    assert items[0].title == "Big AI release"
    assert items[0].source == "hackernews"
    assert items[0].signal_metric == "points"
    assert items[0].signal_value == 340
    assert items[0].published_at.endswith("Z")


def test_fetch_falls_back_to_hn_permalink_when_story_has_no_url():
    session = FakeSession({
        "topstories.json": [7],
        "item/7.json": {"type": "story", "title": "Ask HN: how to learn?",
                        "score": 200, "time": 1753156620},
    })

    items = hackernews.fetch(limit=1, session=session)

    assert items[0].url == "https://news.ycombinator.com/item?id=7"
