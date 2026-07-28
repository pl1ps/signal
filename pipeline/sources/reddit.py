"""Reddit via application-only OAuth (no user password required).

Reddit blocks unauthenticated JSON requests from datacenter IPs (GitHub
Actions runners), so we authenticate with a "script" app's client
credentials and read listings from the OAuth host.
"""

import requests

from pipeline import config
from pipeline.models import Item
from pipeline.sources.base import iso_from_epoch

USER_AGENT = "signal-digest/1.0 (personal daily briefing)"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"


def _get_token(client_id, client_secret, http):
    """Exchange client credentials for an application-only bearer token."""
    response = http.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    return response.json().get("access_token")


def fetch(subreddits, client_id, client_secret, limit=15, session=None):
    """Return top posts of the day from each subreddit as Items.

    Returns [] if credentials are missing or the token cannot be obtained,
    so a Reddit outage never aborts the run.
    """
    if not client_id or not client_secret:
        return []

    http = session or requests
    token = _get_token(client_id, client_secret, http)
    if not token:
        return []

    auth_headers = {"Authorization": f"bearer {token}", "User-Agent": USER_AGENT}
    items = []
    for sub in subreddits:
        payload = http.get(
            f"{API_BASE}/r/{sub}/top",
            params={"t": "day", "limit": limit},
            headers=auth_headers,
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
