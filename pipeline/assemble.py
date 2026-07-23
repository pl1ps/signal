"""Turn scored items into the published Digest document."""

from datetime import datetime, timezone

from pipeline import config
from pipeline.models import Digest


def _iso(moment):
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_levels(scanned_items, kept_items, bars=config.READOUT_BARS):
    """Data for the noise-floor readout.

    Every scanned item becomes a bar. Kept items spike to their relevance;
    everything else sits low, forming the noise floor.
    """
    kept_urls = {item.url for item in kept_items}
    levels = []

    for item in scanned_items:
        is_kept = item.url in kept_urls
        value = max(item.relevance, 0.55) if is_kept else min(item.prescore, 0.25)
        levels.append({"v": round(value, 3), "kept": is_kept})

    if len(levels) <= bars:
        return levels

    step = len(levels) / bars
    sampled = [levels[int(index * step)] for index in range(bars)]

    # Downsampling can drop kept items. Put any that were lost back, each into
    # its own slot that currently holds noise, so no survivor disappears.
    sampled_ids = {id(level) for level in sampled}
    missing = [lvl for lvl in levels if lvl["kept"] and id(lvl) not in sampled_ids]

    for level in missing:
        for slot, existing in enumerate(sampled):
            if not existing["kept"]:
                sampled[slot] = level
                break
    return sampled


def assemble(kept, scanned_items, sources_ok, sources_failed, ai_used, now=None):
    """Group kept items into sections and build the Digest."""
    moment = now or datetime.now(timezone.utc)

    if ai_used:
        survivors = [item for item in kept if item.relevance >= config.MIN_RELEVANCE]
    else:
        # No AI scores exist, so relevance cannot be used to filter.
        survivors = list(kept)
        for item in survivors:
            if not item.section_id:
                item.section_id = config.FALLBACK_SECTION.get(item.source, "tech-discussion")

    sections = []
    for section_id, title in config.SECTIONS:
        members = [item for item in survivors if item.section_id == section_id]
        if not members:
            continue
        members.sort(key=lambda i: i.relevance, reverse=True)
        members = members[:config.ITEMS_PER_SECTION]
        sections.append({
            "id": section_id,
            "title": title,
            "items": [item.to_dict() for item in members],
        })

    published_count = sum(len(section["items"]) for section in sections)

    return Digest(
        generated_at=_iso(moment),
        sections=sections,
        scanned=len(scanned_items),
        kept=published_count,
        levels=build_levels(scanned_items, survivors),
        sources_ok=sources_ok,
        sources_failed=sources_failed,
        ai_used=ai_used,
    )
