import json

from pipeline import config, main
from pipeline.models import Item


def make(title, section="ai-tools"):
    return Item(title=title, url=f"https://a.com/{title}", source="hackernews",
                source_label="Hacker News", section_id=section, relevance=0.9)


def test_load_profile_reads_file(tmp_path):
    path = tmp_path / "profile.md"
    path.write_text("I like AI.\nKeywords: ai, python\n", encoding="utf-8")
    assert "I like AI." in main.load_profile(str(path))


def test_load_profile_returns_empty_string_when_missing(tmp_path):
    assert main.load_profile(str(tmp_path / "nope.md")) == ""


def test_run_writes_digest_json(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "gather", lambda *args, **kwargs: ([make("A")], ["hackernews"], []))
    monkeypatch.setattr(main, "load_profile", lambda path="profile.md": "I like AI.")
    monkeypatch.setattr(main.ai, "rank_and_summarize",
                        lambda profile, items, api_key, session=None: (items, True))

    output = tmp_path / "digest.json"
    result = main.run(output_path=str(output))

    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["sections"][0]["items"][0]["title"] == "A"
    assert written["status"]["ai_used"] is True
    assert result["readout"]["kept"] == 1


def test_run_dry_run_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "gather", lambda *args, **kwargs: ([make("A")], [], []))
    monkeypatch.setattr(main, "load_profile", lambda path="profile.md": "")
    monkeypatch.setattr(main.ai, "rank_and_summarize",
                        lambda profile, items, api_key, session=None: (items, True))

    output = tmp_path / "digest.json"
    main.run(dry_run=True, output_path=str(output))

    assert not output.exists()


def test_gather_passes_reddit_credentials(monkeypatch):
    captured = {}

    def fake_reddit_fetch(subreddits, client_id, client_secret):
        captured["args"] = (subreddits, client_id, client_secret)
        return []

    monkeypatch.setattr(main.reddit, "fetch", fake_reddit_fetch)
    monkeypatch.setattr(main.hackernews, "fetch", lambda: [])
    monkeypatch.setattr(main.github, "fetch", lambda token=None: [])
    monkeypatch.setattr(main.news, "fetch", lambda feeds: [])

    main.gather("ghtok", "cid", "secret")

    assert captured["args"] == (config.SUBREDDITS, "cid", "secret")
