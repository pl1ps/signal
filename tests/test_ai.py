import json

from pipeline import ai
from pipeline.models import Item


def make(title):
    return Item(title=title, url="https://a.com/1", source="hackernews",
                source_label="Hacker News")


class FakeResponse:
    def __init__(self, payload, status=200, text=""):
        self._payload = payload
        self.status_code = status
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            error = RuntimeError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.last_url = None
        self.last_headers = None

    def post(self, url, json=None, headers=None, timeout=None):
        self.last_url = url
        self.last_headers = headers
        return self.response


def gemini_envelope(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def test_build_prompt_includes_profile_indexes_and_section_ids():
    prompt = ai.build_prompt("I like AI agents.", [make("A story")])
    assert "I like AI agents." in prompt
    assert "[0]" in prompt
    assert "ai-tools" in prompt


def test_apply_verdicts_fills_ai_fields_and_drops_rejected():
    items = [make("Keep me"), make("Drop me")]
    verdicts = [
        {"index": 0, "keep": True, "section": "ai-tools",
         "why": "Useful to you.", "summary": "It does a thing.", "relevance": 0.9},
        {"index": 1, "keep": False},
    ]

    kept = ai.apply_verdicts(items, verdicts)

    assert len(kept) == 1
    assert kept[0].why == "Useful to you."
    assert kept[0].section_id == "ai-tools"
    assert kept[0].relevance == 0.9


def test_apply_verdicts_ignores_out_of_range_indexes():
    kept = ai.apply_verdicts([make("Only")], [{"index": 99, "keep": True}])
    assert kept == []


def test_rank_and_summarize_parses_model_output():
    payload = json.dumps([{"index": 0, "keep": True, "section": "world",
                           "why": "Big news.", "summary": "A summary.",
                           "relevance": 0.7}])
    session = FakeSession(FakeResponse(gemini_envelope(payload)))

    items, ai_used = ai.rank_and_summarize("profile", [make("A story")],
                                           api_key="k", session=session)

    assert ai_used is True
    assert items[0].summary == "A summary."


def test_rank_and_summarize_falls_back_when_request_fails():
    class BoomSession:
        def post(self, *args, **kwargs):
            raise RuntimeError("rate limited")

    original = [make("A story")]
    items, ai_used = ai.rank_and_summarize("profile", original,
                                           api_key="k", session=BoomSession())

    assert ai_used is False
    assert items == original          # unchanged, still renderable


def test_rank_and_summarize_falls_back_without_api_key():
    items, ai_used = ai.rank_and_summarize("profile", [make("A story")], api_key=None)
    assert ai_used is False


def test_rank_and_summarize_sends_key_in_header_not_url():
    session = FakeSession(FakeResponse(gemini_envelope("[]")))
    ai.rank_and_summarize("profile", [make("A story")], api_key="secretkey", session=session)
    assert session.last_headers["x-goog-api-key"] == "secretkey"
    assert "secretkey" not in session.last_url
    assert "key=" not in session.last_url


def test_rank_and_summarize_requests_structured_output():
    captured = {}

    class CapturingSession:
        def post(self, url, json=None, headers=None, timeout=None):
            captured["body"] = json
            return FakeResponse(gemini_envelope("[]"))

    ai.rank_and_summarize("profile", [make("A story")], api_key="k", session=CapturingSession())
    gen = captured["body"]["generationConfig"]
    assert gen["responseMimeType"] == "application/json"
    assert gen["responseSchema"]["type"] == "ARRAY"


def test_parse_text_skips_thinking_parts():
    payload = {"candidates": [{"content": {"parts": [
        {"text": "internal reasoning", "thought": True},
        {"text": "[{\"index\": 0, \"keep\": true}]"},
    ]}}]}
    assert ai._parse_text(payload) == "[{\"index\": 0, \"keep\": true}]"


def test_rank_and_summarize_logs_error_body_on_failure(caplog):
    body = '{"error":{"code":429,"message":"quota"}}'
    session = FakeSession(FakeResponse({}, status=429, text=body))
    items, ai_used = ai.rank_and_summarize("profile", [make("A story")],
                                           api_key="k", session=session,
                                           sleep=lambda s: None)
    assert ai_used is False
    assert "quota" in caplog.text  # the real error body reached the log


class SequenceSession:
    """Returns queued responses in order, one per .post call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls += 1
        return self.responses.pop(0)


def test_rank_and_summarize_retries_then_succeeds():
    ok = gemini_envelope(json.dumps([{"index": 0, "keep": True, "section": "world",
                                      "why": "w", "summary": "s", "relevance": 0.7}]))
    session = SequenceSession([FakeResponse({}, status=429, text="quota"),
                               FakeResponse(ok)])
    sleeps = []

    items, ai_used = ai.rank_and_summarize("profile", [make("A story")], api_key="k",
                                           session=session, sleep=lambda s: sleeps.append(s))

    assert ai_used is True
    assert session.calls == 2
    assert len(sleeps) == 1  # one backoff between the two attempts


def test_rank_and_summarize_gives_up_after_max_attempts():
    session = SequenceSession([FakeResponse({}, status=429, text="quota")
                               for _ in range(5)])
    sleeps = []

    original = [make("A story")]
    items, ai_used = ai.rank_and_summarize("profile", original, api_key="k",
                                           session=session, sleep=lambda s: sleeps.append(s))

    assert ai_used is False
    assert items == original
    assert session.calls == 3           # config.GEMINI_MAX_ATTEMPTS
    assert len(sleeps) == 2             # backoff between attempts, not after the last


def test_rank_and_summarize_does_not_retry_non_retryable():
    session = SequenceSession([FakeResponse({}, status=400, text="bad request")])
    sleeps = []

    ai.rank_and_summarize("profile", [make("A story")], api_key="k",
                          session=session, sleep=lambda s: sleeps.append(s))

    assert session.calls == 1           # 400 is not retried
    assert sleeps == []
