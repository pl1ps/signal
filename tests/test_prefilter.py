from pipeline import prefilter
from pipeline.models import Item


def make(title, url="https://a.com/1", snippet="", signal=0):
    return Item(title=title, url=url, source="hackernews",
                source_label="Hacker News", snippet=snippet, signal_value=signal)


def test_extract_keywords_reads_the_keywords_line():
    profile = "I am a CS student.\nKeywords: LLM, AI agent, Python, internship"
    assert prefilter.extract_keywords(profile) == ["llm", "ai agent", "python", "internship"]


def test_extract_keywords_returns_empty_when_absent():
    assert prefilter.extract_keywords("No keyword line here.") == []


def test_dedupe_removes_same_url_and_same_title():
    items = [
        make("Same story", url="https://a.com/x"),
        make("Same story", url="https://b.com/y"),   # duplicate title
        make("Other", url="https://a.com/x"),        # duplicate url
        make("Unique", url="https://c.com/z"),
    ]
    assert len(prefilter.dedupe(items)) == 2


def test_prefilter_scores_keyword_matches_and_caps():
    items = [
        make("New LLM agent framework", url="https://a.com/1", snippet="python inside", signal=10),
        make("Gardening tips", url="https://a.com/2", signal=999),
    ]
    result = prefilter.prefilter(items, ["llm", "agent", "python"], cap=5)

    assert result[0].title == "New LLM agent framework"
    assert result[0].prescore > result[1].prescore


def test_prefilter_caps_result_length():
    items = [make(f"Story {n}", url=f"https://a.com/{n}") for n in range(20)]
    assert len(prefilter.prefilter(items, [], cap=5)) == 5
