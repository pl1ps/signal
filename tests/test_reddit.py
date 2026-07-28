from pipeline.sources import reddit


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeRedditSession:
    """Serves a canned token from .post and a canned listing from .get."""

    def __init__(self, token_payload, listing_payload):
        self.token_payload = token_payload
        self.listing_payload = listing_payload
        self.post_calls = []
        self.get_calls = []

    def post(self, url, auth=None, data=None, headers=None, timeout=None):
        self.post_calls.append({"url": url, "auth": auth, "data": data, "headers": headers})
        return FakeResp(self.token_payload)

    def get(self, url, params=None, headers=None, timeout=None):
        self.get_calls.append({"url": url, "params": params, "headers": headers})
        return FakeResp(self.listing_payload)


def _listing(title, ups, permalink="/r/x/comments/1/a/"):
    return {"data": {"children": [{"data": {
        "title": title, "ups": ups, "permalink": permalink,
        "selftext": "body text", "created_utc": 1753156620, "url": "https://ex.com/p",
    }}]}}


def test_fetch_authenticates_then_reads_listing():
    session = FakeRedditSession({"access_token": "tok123"},
                                _listing("How do I learn Python?", 500))

    items = reddit.fetch(["learnprogramming"], "cid", "secret", session=session)

    assert len(items) == 1
    assert items[0].source == "reddit"
    assert items[0].source_label == "r/learnprogramming"
    assert items[0].signal_metric == "upvotes"
    assert items[0].signal_value == 500
    # Token exchange used HTTP Basic auth + client-credentials grant.
    assert session.post_calls[0]["auth"] == ("cid", "secret")
    assert session.post_calls[0]["data"]["grant_type"] == "client_credentials"
    # Listing request hit the OAuth host with a bearer token and a User-Agent.
    assert "oauth.reddit.com" in session.get_calls[0]["url"]
    assert session.get_calls[0]["headers"]["Authorization"] == "bearer tok123"
    assert "User-Agent" in session.get_calls[0]["headers"]


def test_fetch_returns_empty_without_credentials():
    session = FakeRedditSession({"access_token": "tok"}, _listing("x", 500))
    assert reddit.fetch(["learnprogramming"], "", "", session=session) == []
    assert session.post_calls == []  # never even requested a token


def test_fetch_returns_empty_when_token_missing():
    session = FakeRedditSession({}, _listing("x", 500))  # no access_token key
    assert reddit.fetch(["learnprogramming"], "cid", "secret", session=session) == []
    assert session.get_calls == []  # no token -> never fetched a listing


def test_fetch_drops_posts_below_threshold():
    session = FakeRedditSession({"access_token": "tok"}, _listing("Low effort", 3))
    assert reddit.fetch(["learnprogramming"], "cid", "secret", session=session) == []
