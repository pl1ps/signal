"""Data shapes shared by every pipeline stage."""

from dataclasses import dataclass, field


@dataclass
class Item:
    """One piece of content, from any source, at any pipeline stage."""

    title: str
    url: str
    source: str
    source_label: str
    snippet: str = ""
    signal_metric: str = ""      # "points" | "upvotes" | "stars" | ""
    signal_value: int = 0
    published_at: str = ""

    # Filled in by later stages
    prescore: float = 0.0        # cheap keyword score, internal only
    relevance: float = 0.0       # AI score, published
    why: str = ""
    summary: str = ""
    section_id: str = ""

    def to_dict(self) -> dict:
        """Only the fields the app needs. prescore and snippet stay internal."""
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "source_label": self.source_label,
            "why": self.why,
            "summary": self.summary,
            "signal": {"metric": self.signal_metric, "value": self.signal_value},
            "published_at": self.published_at,
            "relevance": round(self.relevance, 3),
        }


@dataclass
class Digest:
    """The complete published document."""

    generated_at: str
    sections: list = field(default_factory=list)
    scanned: int = 0
    kept: int = 0
    levels: list = field(default_factory=list)
    sources_ok: list = field(default_factory=list)
    sources_failed: list = field(default_factory=list)
    ai_used: bool = True

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "generator_version": 1,
            "sections": self.sections,
            "readout": {
                "scanned": self.scanned,
                "kept": self.kept,
                "levels": self.levels,
            },
            "status": {
                "sources_ok": self.sources_ok,
                "sources_failed": self.sources_failed,
                "ai_used": self.ai_used,
            },
        }
