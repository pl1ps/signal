"""Hacker News via the official free Firebase API (no key required)."""

import requests

from pipeline import config
from pipeline.models import Item
from pipeline.sources.base import iso_from_epoch

API = "https://hacker-news.firebaseio.com/v0"


def fetch(limit=60, session=None):
    """Return popular HN stories as Items."""
    http = session or requests
    story_ids = http.get(f"{API}/topstories.json", timeout=15).json()[:limit]

    items = []
    for story_id in story_ids:
        data = http.get(f"{API}/item/{story_id}.json", timeout=15).json()
        if not data or data.get("type") != "story":
            continue
        score = data.get("score", 0)
        if score < config.HN_MIN_POINTS:
            continue

        items.append(Item(
            title=data.get("title", ""),
            url=data.get("url") or f"https://news.ycombinator.com/item?id={story_id}",
            source="hackernews",
            source_label="Hacker News",
            snippet=(data.get("text") or "")[:300],
            signal_metric="points",
            signal_value=score,
            published_at=iso_from_epoch(data.get("time")),
        ))
    return items
