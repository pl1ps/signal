"""Failure isolation: one broken source must never abort the whole run."""

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def fetch_safe(name, fetcher):
    """Run `fetcher`, converting any failure into an empty result.

    Returns (items, ok). The caller records `ok` so the digest can honestly
    report which sources contributed.
    """
    try:
        return fetcher(), True
    except Exception as exc:  # deliberately broad: no source may crash the run
        log.warning("source %s failed: %s", name, exc)
        return [], False


def iso_from_epoch(epoch_seconds):
    """Convert a Unix timestamp to an ISO-8601 UTC string ending in Z.

    Returns "" when the source supplied no timestamp. "" is the project's
    explicit "unknown" value, and is published as-is.
    """
    if not epoch_seconds:
        return ""
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def iso_from_feed_time(parsed_time):
    """Convert feedparser's published_parsed struct_time to ISO-8601 UTC.

    Returns "" when the feed entry carried no parseable date.
    """
    if not parsed_time:
        return ""
    return datetime(*parsed_time[:6], tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
