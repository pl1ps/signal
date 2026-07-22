from pipeline.sources import reddit


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class RecordingSession:
    def __init__(self, payload):
        self.payload = payload
        self.headers_seen = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.headers_seen.append(headers)
        return FakeResponse(self.payload)


def _listing(title, ups, permalink="/r/x/comments/1/a/"):
    return {"data": {"children": [{"data": {
        "title": title, "ups": ups, "permalink": permalink,
        "selftext": "body text", "created_utc": 1753156620, "url": "https://ex.com/p",
    }}]}}


def test_fetch_keeps_upvoted_posts_and_sends_user_agent():
    session = RecordingSession(_listing("How do I learn Python?", 500))

    items = reddit.fetch(["learnprogramming"], session=session)

    assert len(items) == 1
    assert items[0].source == "reddit"
    assert items[0].source_label == "r/learnprogramming"
    assert items[0].signal_metric == "upvotes"
    assert items[0].signal_value == 500
    # Reddit rate-limits hard without a descriptive User-Agent.
    assert "User-Agent" in session.headers_seen[0]


def test_fetch_drops_posts_below_threshold():
    session = RecordingSession(_listing("Low effort post", 3))
    assert reddit.fetch(["learnprogramming"], session=session) == []
