"""Failure isolation: one broken source must never abort the whole run."""

import logging

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
