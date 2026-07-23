from datetime import datetime, timezone

from pipeline import assemble
from pipeline.models import Item


def make(title, section="ai-tools", relevance=0.9, source="hackernews"):
    return Item(title=title, url=f"https://a.com/{title}", source=source,
                source_label="Hacker News", section_id=section, relevance=relevance)


NOW = datetime(2026, 7, 22, 6, 17, tzinfo=timezone.utc)


def test_assemble_groups_into_sections_and_omits_empty_ones():
    kept = [make("A", "ai-tools"), make("B", "world")]

    digest = assemble.assemble(kept, kept, ["hackernews"], [], True, now=NOW)

    ids = [section["id"] for section in digest.sections]
    assert ids == ["ai-tools", "world"]      # order follows config.SECTIONS
    assert digest.sections[0]["title"] == "AI & Tools"


def test_assemble_drops_low_relevance_when_ai_used():
    kept = [make("Strong", relevance=0.9), make("Weak", relevance=0.05)]
    digest = assemble.assemble(kept, kept, [], [], True, now=NOW)
    assert digest.kept == 1


def test_assemble_keeps_everything_when_ai_unavailable():
    kept = [make("Strong", relevance=0.0), make("Weak", relevance=0.0)]
    digest = assemble.assemble(kept, kept, [], [], False, now=NOW)
    assert digest.kept == 2


def test_assemble_assigns_fallback_sections_when_ai_unavailable():
    kept = [make("Repo", section="", source="github")]
    digest = assemble.assemble(kept, kept, [], [], False, now=NOW)
    assert digest.sections[0]["id"] == "code-projects"


def test_assemble_caps_items_per_section():
    kept = [make(f"S{n}") for n in range(20)]
    digest = assemble.assemble(kept, kept, [], [], True, now=NOW)
    assert len(digest.sections[0]["items"]) == 6


def test_assemble_records_counts_and_status():
    scanned = [make(f"S{n}") for n in range(30)]
    digest = assemble.assemble(scanned[:2], scanned, ["hackernews"], ["reddit"], True, now=NOW)

    assert digest.scanned == 30
    assert digest.kept == 2
    assert digest.sources_failed == ["reddit"]
    assert digest.generated_at == "2026-07-22T06:17:00Z"


def test_build_levels_marks_kept_items_and_limits_bar_count():
    scanned = [make(f"S{n}", relevance=0.0) for n in range(100)]
    levels = assemble.build_levels(scanned, scanned[:3], bars=10)

    assert len(levels) == 10
    assert sum(1 for level in levels if level["kept"]) >= 1
    assert all(0.0 <= level["v"] <= 1.0 for level in levels)


def test_build_levels_never_drops_a_kept_item_when_downsampling():
    # 100 scanned items; the kept ones sit at positions that an even stride
    # sample (indices 0, 10, 20, ...) would mostly miss.
    scanned = [make(f"S{n}", relevance=0.0) for n in range(100)]
    kept = [scanned[1], scanned[49], scanned[99]]
    for item in kept:
        item.relevance = 0.9

    levels = assemble.build_levels(scanned, kept, bars=10)

    assert len(levels) == 10
    # All three survivors must appear, not just "at least one".
    assert sum(1 for level in levels if level["kept"]) == 3
