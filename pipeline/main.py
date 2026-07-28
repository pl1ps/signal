"""Entry point: fetch, filter, summarize, assemble, publish."""

import argparse
import json
import logging
import os

from pipeline import ai, assemble, config, prefilter
from pipeline.sources import base, github, hackernews, news, reddit

log = logging.getLogger(__name__)


def load_profile(path="profile.md"):
    """Read the interest profile; an env var wins so it can stay private."""
    from_env = os.environ.get("PROFILE")
    if from_env:
        return from_env
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        log.warning("no profile at %s; relevance will be generic", path)
        return ""


def gather(gh_token=None, reddit_client_id=None, reddit_client_secret=None):
    """Fetch every source. Returns (items, sources_ok, sources_failed)."""
    plan = [
        ("hackernews", lambda: hackernews.fetch()),
        ("github", lambda: github.fetch(token=gh_token)),
        ("reddit", lambda: reddit.fetch(config.SUBREDDITS,
                                        reddit_client_id, reddit_client_secret)),
        ("news", lambda: news.fetch(config.RSS_FEEDS)),
    ]

    items, ok, failed = [], [], []
    for name, fetcher in plan:
        fetched, succeeded = base.fetch_safe(name, fetcher)
        items.extend(fetched)
        (ok if succeeded else failed).append(name)

    return items, ok, failed


def run(dry_run=False, output_path="digest.json"):
    """Run the whole pipeline. Returns the digest as a dict."""
    profile = load_profile()
    keywords = prefilter.extract_keywords(profile)

    raw_items, sources_ok, sources_failed = gather(
        os.environ.get("GH_TOKEN"),
        os.environ.get("REDDIT_CLIENT_ID"),
        os.environ.get("REDDIT_CLIENT_SECRET"),
    )
    log.info("fetched %d raw items (ok=%s failed=%s)", len(raw_items), sources_ok, sources_failed)

    candidates = prefilter.prefilter(raw_items, keywords)
    log.info("pre-filtered to %d candidates", len(candidates))

    kept, ai_used = ai.rank_and_summarize(
        profile, candidates, os.environ.get("GEMINI_API_KEY")
    )
    log.info("ai_used=%s kept=%d", ai_used, len(kept))

    # candidates drives the readout bars; the headline count is the full
    # gathered pool, so "N scanned" reflects the real subtraction, not the cap.
    digest = assemble.assemble(kept, candidates, sources_ok, sources_failed, ai_used,
                               scanned_total=len(raw_items))
    payload = digest.to_dict()

    if dry_run:
        print(json.dumps(payload, indent=2)[:4000])
    else:
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        log.info("wrote %s", output_path)

    return payload


def cli():
    parser = argparse.ArgumentParser(description="Build the Signal digest.")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the digest instead of writing digest.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    cli()
