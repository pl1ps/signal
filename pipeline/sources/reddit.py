"""Reddit via public .json listing endpoints (no API key required)."""

import requests

from pipeline import config
from pipeline.models import Item
from pipeline.sources.base import iso_from_epoch

# Reddit rate-limits aggressively without a descriptive User-Agent.
USER_AGENT = "signal-digest/1.0 (personal daily briefing)"


def fetch(subreddits, limit=15, session=None):
    """Return top posts of the day from each subreddit as Items."""
    http = session or requests
    items = []

    for sub in subreddits:
        payload = http.get(
            f"https://www.reddit.com/r/{sub}/top.json",
            params={"t": "day", "limit": limit},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        ).json()

        for child in payload.get("data", {}).get("children", []):
            post = child.get("data", {})
            ups = post.get("ups", 0)
            if ups < config.REDDIT_MIN_UPVOTES:
                continue

            items.append(Item(
                title=post.get("title", ""),
                url=f"https://www.reddit.com{post.get('permalink', '')}",
                source="reddit",
                source_label=f"r/{sub}",
                snippet=(post.get("selftext") or "")[:300],
                signal_metric="upvotes",
                signal_value=ups,
                published_at=iso_from_epoch(post.get("created_utc")),
            ))
    return items
