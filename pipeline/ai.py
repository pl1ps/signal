"""Relevance ranking and summarization via the Gemini REST API.

Every failure path returns (items, False) so the run always produces a digest.
"""

import json
import logging

import requests

from pipeline import config

log = logging.getLogger(__name__)

INSTRUCTIONS = """You are the editor of one person's daily briefing.

Their profile:
{profile}

Below are today's candidate items. Keep ONLY items genuinely useful or
interesting to this person. Be strict — keeping 6 to 15 items is normal.

For each item you keep, write:
- "why": ONE short sentence, addressed to them, on why it matters to them.
- "summary": ONE or TWO plain-language sentences on what it actually is.
  Assume they are early in their programming journey. No jargon without a gloss.
- "section": one of {section_ids}
- "relevance": 0.0 to 1.0

Reply with ONLY a JSON array, no prose, no code fences:
[{{"index": 0, "keep": true, "section": "ai-tools", "why": "...",
   "summary": "...", "relevance": 0.82}}]

Items:
{items}
"""


def build_prompt(profile, items):
    section_ids = ", ".join(section_id for section_id, _ in config.SECTIONS)
    lines = []
    for index, item in enumerate(items):
        snippet = item.snippet[:200].replace("\n", " ")
        lines.append(f"[{index}] ({item.source_label}) {item.title} — {snippet}")
    return INSTRUCTIONS.format(
        profile=profile.strip(),
        section_ids=section_ids,
        items="\n".join(lines),
    )


def _parse_text(payload):
    """Pull the model's text out of the Gemini response envelope."""
    return payload["candidates"][0]["content"]["parts"][0]["text"]


def apply_verdicts(items, verdicts):
    """Attach AI fields to items the model kept; drop the rest."""
    valid_sections = {section_id for section_id, _ in config.SECTIONS}
    kept = []

    for verdict in verdicts:
        index = verdict.get("index")
        if not isinstance(index, int) or not 0 <= index < len(items):
            continue
        if not verdict.get("keep"):
            continue

        item = items[index]
        section = verdict.get("section", "")
        item.section_id = section if section in valid_sections else "tech-discussion"
        item.why = verdict.get("why", "")
        item.summary = verdict.get("summary", "")
        item.relevance = float(verdict.get("relevance", 0.0))
        kept.append(item)

    return kept


def rank_and_summarize(profile, items, api_key, session=None):
    """Return (items, ai_used). On any failure, returns the input untouched."""
    if not api_key or not items:
        log.warning("AI stage skipped: no API key or no items")
        return items, False

    http = session or requests
    url = config.GEMINI_URL.format(model=config.GEMINI_MODEL) + f"?key={api_key}"
    body = {
        "contents": [{"parts": [{"text": build_prompt(profile, items)}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }

    try:
        response = http.post(url, json=body, timeout=90)
        response.raise_for_status()
        verdicts = json.loads(_parse_text(response.json()))
        return apply_verdicts(items, verdicts), True
    except Exception as exc:  # broad: the digest must survive any AI failure
        # Some request errors embed the full URL (with ?key=...) in their
        # message, so scrub the key before it ever reaches a log line.
        safe_message = str(exc).replace(api_key, "<redacted>")
        log.warning("AI stage failed, falling back to raw items: %s", safe_message)
        return items, False
