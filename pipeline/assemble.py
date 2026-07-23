"""Turn scored items into the published Digest document."""

from datetime import datetime, timezone

from pipeline import config
from pipeline.models import Digest


def _iso(moment):
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_levels(scanned_items, kept_items, bars=config.READOUT_BARS):
    """Data for the noise-floor readout.

    Every scanned item becomes a bar. Kept items spike to their relevance;
    everything else sits low, forming the noise floor. When there are more
    items than `bars`, only the noise is thinned out — every kept item is
    always retained (in its original left-to-right position), so a survivor
    can never disappear from the readout. READOUT_BARS is kept larger than
    the candidate cap so the kept-heavy path below is only a safety net.
    """
    kept_urls = {item.url for item in kept_items}
    levels = []

    for item in scanned_items:
        is_kept = item.url in kept_urls
        value = max(item.relevance, 0.55) if is_kept else min(item.prescore, 0.25)
        levels.append({"v": round(value, 3), "kept": is_kept})

    if len(levels) <= bars:
        return levels

    kept_count = sum(1 for level in levels if level["kept"])
    noise_budget = bars - kept_count

    # Safety net: if survivors somehow outnumber the bars, show as many kept
    # bars as fit rather than dropping some silently.
    if noise_budget <= 0:
        return [level for level in levels if level["kept"]][:bars]

    # Keep every kept bar; fill the remaining slots with an even sample of the
    # noise, walking left to right so original order is preserved.
    noise_total = len(levels) - kept_count
    stride = noise_total / noise_budget
    result = []
    noise_seen = 0
    noise_taken = 0
    for level in levels:
        if level["kept"]:
            result.append(level)
        else:
            if noise_taken < noise_budget and noise_seen >= noise_taken * stride:
                result.append(level)
                noise_taken += 1
            noise_seen += 1
    return result


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
