import json

from pipeline import ai
from pipeline.models import Item


def make(title):
    return Item(title=title, url="https://a.com/1", source="hackernews",
                source_label="Hacker News")


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, response):
        self.response = response

    def post(self, url, json=None, timeout=None):
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
