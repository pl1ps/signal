from pipeline.sources import github


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class RecordingSession:
    def __init__(self, payload):
        self.payload = payload
        self.last_params = None
        self.last_headers = None

    def get(self, url, params=None, headers=None, timeout=None):
        self.last_params = params
        self.last_headers = headers
        return FakeResponse(self.payload)


def test_fetch_maps_repos_to_items():
    session = RecordingSession({
        "items": [{
            "full_name": "acme/agent-kit",
            "html_url": "https://github.com/acme/agent-kit",
            "description": "Build agents fast.",
            "stargazers_count": 1200,
            "created_at": "2026-07-18T10:00:00Z",
        }]
    })

    items = github.fetch(token="t0ken", session=session)

    assert len(items) == 1
    assert items[0].title == "acme/agent-kit"
    assert items[0].source == "github"
    assert items[0].signal_metric == "stars"
    assert items[0].signal_value == 1200
    assert items[0].snippet == "Build agents fast."
    assert session.last_headers["Authorization"] == "Bearer t0ken"


def test_fetch_omits_auth_header_when_no_token():
    session = RecordingSession({"items": []})
    github.fetch(token=None, session=session)
    assert "Authorization" not in session.last_headers
