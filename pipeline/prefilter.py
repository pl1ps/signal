"""Cheap, AI-free filtering.

This is the cost-control stage: it shrinks a few hundred raw items down to a
few dozen candidates so the AI stage stays inside the free tier.
"""

import re

from pipeline import config


def extract_keywords(profile_text):
    """Read the optional 'Keywords: a, b, c' line from the profile."""
    match = re.search(r"^keywords:\s*(.+)$", profile_text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return []
    return [word.strip().lower() for word in match.group(1).split(",") if word.strip()]


def _normalize_title(title):
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def dedupe(items):
    """Drop items sharing a URL or a normalized title with an earlier item."""
    seen_urls, seen_titles, kept = set(), set(), []

    for item in items:
        title_key = _normalize_title(item.title)
        if item.url in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(item.url)
        seen_titles.add(title_key)
        kept.append(item)
    return kept


def _keyword_score(item, keywords):
    """Fraction of the profile's keywords that appear in this item."""
    if not keywords:
        return 0.0
    haystack = f"{item.title} {item.snippet}".lower()
    hits = sum(1 for word in keywords if word in haystack)
    return hits / len(keywords)


def prefilter(items, keywords, cap=config.CANDIDATE_CAP):
    """Dedupe, score, sort, and cap. Sets `prescore` on every item."""
    survivors = dedupe(items)

    for item in survivors:
        item.prescore = _keyword_score(item, keywords)

    # Keyword relevance first; popularity breaks ties.
    survivors.sort(key=lambda i: (i.prescore, i.signal_value), reverse=True)
    return survivors[:cap]
