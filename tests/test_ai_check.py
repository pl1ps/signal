from pipeline import ai_check


class FakeResponse:
    def __init__(self, status=200, text="", payload=None):
        self.status_code = status
        self.text = text
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.last_headers = None

    def post(self, url, json=None, headers=None, timeout=None):
        self.last_headers = headers
        return self.response


def test_check_reports_ok_on_200():
    session = FakeSession(FakeResponse(status=200))
    ok, detail = ai_check.check("k", session=session)
    assert ok is True
    assert session.last_headers["x-goog-api-key"] == "k"


def test_check_reports_quota_body_on_429():
    session = FakeSession(FakeResponse(status=429, text='{"error":{"message":"limit: 0"}}'))
    ok, detail = ai_check.check("k", session=session)
    assert ok is False
    assert "limit: 0" in detail


def test_check_reports_missing_key():
    ok, detail = ai_check.check("", session=None)
    assert ok is False
    assert "GEMINI_API_KEY" in detail
