"""Fast-rising repositories via the GitHub Search API.

GitHub has no official "trending" API, so we approximate it: repositories
created recently that have already gathered a lot of stars.
"""

from datetime import datetime, timedelta, timezone

import requests

from pipeline import config
from pipeline.models import Item

SEARCH_URL = "https://api.github.com/search/repositories"


def fetch(token=None, days=7, limit=30, session=None):
    """Return recently created, fast-growing repos as Items."""
    http = session or requests
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = http.get(
        SEARCH_URL,
        params={
            "q": f"created:>{since} stars:>{config.GITHUB_MIN_STARS}",
            "sort": "stars",
            "order": "desc",
            "per_page": limit,
        },
        headers=headers,
        timeout=15,
    ).json()

    items = []
    for repo in payload.get("items", []):
        items.append(Item(
            title=repo.get("full_name", ""),
            url=repo.get("html_url", ""),
            source="github",
            source_label="GitHub",
            snippet=(repo.get("description") or "")[:300],
            signal_metric="stars",
            signal_value=repo.get("stargazers_count", 0),
            published_at=repo.get("created_at", ""),
        ))
    return items
