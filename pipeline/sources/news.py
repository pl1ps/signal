"""Major world headlines from public RSS feeds (no API key required)."""

import feedparser

from pipeline.models import Item
from pipeline.sources.base import iso_from_feed_time


def fetch(feeds, per_feed=10, parser=None):
    """Return headlines from each (label, url) feed as Items."""
    parse = parser or feedparser.parse
    items = []

    for label, url in feeds:
        parsed = parse(url)
        for entry in parsed.entries[:per_feed]:
            # feedparser pre-parses the feed's date into a struct_time, so we
            # convert that rather than the many date formats feeds use in text.
            items.append(Item(
                title=getattr(entry, "title", ""),
                url=getattr(entry, "link", ""),
                source="news",
                source_label=label,
                snippet=getattr(entry, "summary", "")[:300],
                published_at=iso_from_feed_time(getattr(entry, "published_parsed", None)),
            ))
    return items
