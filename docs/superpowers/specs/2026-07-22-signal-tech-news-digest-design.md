# Signal — Personal Tech & World News Daily Briefing (Design Spec)

- **Date:** 2026-07-22
- **Status:** Approved design — ready for implementation planning
- **Working name:** Signal (rename freely)

---

## 1. Overview

Signal is a personal, installable phone app (PWA) that delivers a **once-a-day, concise briefing** of the tech/AI world plus major world news. An AI filters a few hundred raw items down to only what is relevant to the user, and rewrites each keeper into a plain-language, skimmable card. The goal is to replace scattered doom-scrolling across multiple platforms with a two-minute morning read.

**Primary user:** the author — a CS student, early in their programming journey, interested in AI and current tech, who wants to stay informed without spending time reading source platforms directly.

**Guiding constraints (in priority order):**
1. **Working-first** — a real app used daily beats a clever one.
2. **Free to run** — target $0/month operating cost.
3. **Beginner-friendly stack** — gentle learning curve, minimal tooling.
4. **Concise & on-the-go** — fast to read, works offline.
5. **Personal now, but built so it could grow to multi-user later without a rewrite.**

---

## 2. Goals and non-goals

### Goals
- Aggregate from multiple free tech/news sources on a daily schedule.
- Use an AI to (a) judge relevance against a user-written interest profile and (b) summarize each kept item concisely.
- Present the result as an installable, offline-capable PWA with a clean, readable UI.
- Run entirely on free infrastructure (GitHub Actions + GitHub Pages + a free-tier LLM).
- Degrade gracefully so the user always has something to read.

### Non-goals (v1 — deliberately cut, see §12)
- X/Twitter as a source.
- Push notifications.
- User accounts / authentication / multi-user.
- Behavioral personalization (learning from taps/saves).
- Bookmarking or read/unread sync across devices.
- Full-article scraping (summaries are built from titles, snippets, and metadata).
- In-app search.

---

## 3. Users and scale

- **v1:** a single user (the author), possibly shared informally with a few friends by URL.
- **Scale assumption:** one interest profile, one digest per run. Volumes are tiny — a few hundred raw items per day, filtered to a few dozen, summarized in a handful of AI calls.
- **Growth path:** see §10. The architecture is structured so multi-user is an evolution, not a rewrite.

---

## 4. Architecture

Everything lives in **one free GitHub repository**. A scheduled GitHub Actions job runs the Python pipeline, which writes `digest.json` into the repo. GitHub Pages serves both the PWA and `digest.json`. The phone app is a thin reader that fetches and renders the JSON, caching it for offline use.

```
   ┌─────────────────────── GitHub (one free repo) ───────────────────────┐
   │                                                                       │
   │   GitHub Actions (cron, ~06:17 user-local time)                       │
   │        │                                                              │
   │        ▼                                                              │
   │   Python pipeline:  FETCH → NORMALIZE → PRE-FILTER → AI RANK+SUMMARIZE│
   │        │                                              (Gemini, free)  │
   │        ▼                                                              │
   │   writes  digest.json  ──commit──►  repo                              │
   │                                       │                               │
   │   GitHub Pages serves:  PWA files  +  digest.json                     │
   └───────────────────────────────────────┼───────────────────────────────┘
                                            │  (HTTPS fetch)
                                            ▼
                                   📱 Phone (PWA)
                              reads digest.json, renders it,
                              caches it for offline reading
```

**Key property:** all intelligence and all secrets live server-side in the scheduled job. The LLM API key is stored as an encrypted GitHub Actions **secret** and never reaches the client. The client only ever reads the public `digest.json`, which contains no secrets.

**Repository visibility:** public repo (simplest path to unlimited free Actions minutes and free Pages). Published content is only news summaries — no secrets. The interest profile is non-sensitive but personal; it may be kept in the repo as `profile.md`, or moved to a GitHub Actions secret if the user prefers it not be public (see §5 and §8).

---

## 5. Personalization

A single interest profile drives relevance judging and the phrasing of each item's "why it matters to you" line.

- **Storage:** `profile.md` in the repo (default), or a GitHub Actions secret named `PROFILE` if the user wants it private.
- **Content:** a short natural-language self-description plus optional explicit keywords. Example:

  > "CS student, early in programming, strongly interested in AI (LLMs, AI agents, tools I could actually use), learning-to-code resources, and CS career advice. Also want the day's major world news. Prefer practical over academic. Keywords: LLM, AI agent, Python, beginner, internship, open source."

- **How it is used:**
  - The **pre-filter** uses the keywords for cheap first-pass matching (no AI cost).
  - The **AI stage** uses the full profile text to score relevance and to write the personalized "why it matters to you" line.
- **Editing interests:** edit one file; next run reflects it.

---

## 6. The pipeline (Python, runs in GitHub Actions)

Six stages with clean interfaces so each is independently testable. Each stage consumes a well-defined structure and produces the next.

1. **Fetch** — pull raw items from each source. Each source fetcher is isolated in its own module and wrapped so a failure returns an empty result plus a logged error rather than crashing the run.
2. **Normalize** — map every source's raw response into a common item shape (see §7). This is where source-specific quirks are contained.
3. **Pre-filter** (no AI — free and fast):
   - Deduplicate by URL and near-duplicate title.
   - Drop low-signal items below a per-source popularity threshold (HN points, Reddit upvotes, GitHub recent stars).
   - Score remaining items by cheap keyword match against the profile keywords.
   - Keep the top ~40–60 candidates. **This step is the primary cost control** — it ensures only a manageable, relevant subset reaches the paid/limited AI stage.
4. **AI rank + summarize** — send the candidate list plus the profile to the LLM in a small number of batched calls. The model returns, per item it keeps: a relevance score, a target section, a one-line "why it matters to you," and a 1–2 sentence plain-language summary. Requests are batched to minimize call count and stay within free-tier limits.
5. **Assemble** — group kept items into sections, sort within each by relevance, cap items per section for conciseness, and produce the `digest.json` object including a generation timestamp and a run-status block.
6. **Publish** — commit `digest.json` to the repo. This daily commit also serves as repository activity that keeps the scheduled workflow from being auto-disabled.

**Configuration (concrete defaults, all editable):**
- Schedule: one run per day at ~06:17 user-local time, expressed as a UTC cron in the workflow (user supplies their timezone at setup; the odd minute avoids top-of-hour Actions congestion). A second daily run can be added later by adding one cron line.
- Candidate cap: 50. Items per section: 5–7. Relevance threshold for inclusion: tuned during implementation.
- LLM: Google Gemini (Flash-class model) as the default free provider; Groq as a documented fallback. Exact model id and current free-tier limits are confirmed at implementation time.

---

## 7. Data model

### `digest.json` (top level)
```json
{
  "generated_at": "2026-07-22T06:17:00Z",
  "generator_version": 1,
  "sections": [ /* Section objects, see below */ ],
  "status": {
    "sources_ok": ["hackernews", "github", "reddit", "news"],
    "sources_failed": [],
    "ai_used": true
  }
}
```

### Section
```json
{
  "id": "ai-tools",
  "title": "🤖 AI & Tools",
  "items": [ /* Item objects */ ]
}
```

### Item
```json
{
  "title": "Original item title",
  "url": "https://example.com/article",
  "source": "hackernews",
  "source_label": "Hacker News",
  "why": "One-line reason this matters to you.",
  "summary": "1–2 sentence plain-language summary.",
  "signal": { "metric": "points", "value": 340 },
  "published_at": "2026-07-22T04:00:00Z",
  "relevance": 0.82
}
```

- `status` lets the app show honest freshness/health (e.g., "AI summaries unavailable this run — showing raw items").
- `signal` is the source's popularity metric (points/upvotes/stars) for lightweight context and optional display.

### Default sections
- **🤖 AI & Tools** — AI news and usable tools (HN, r/LocalLLaMA, r/artificial).
- **💻 Code & Projects** — GitHub trending and "Show HN"-style build posts.
- **🎓 Learn & Career** — r/learnprogramming, r/cscareerquestions, learning-oriented articles.
- **🔥 Tech Discussion** — notable general tech chatter not captured above.
- **🌍 World** — major global headlines.

The AI assigns each kept item to one of these sections. Empty sections are omitted from the rendered digest.

---

## 8. Sources (all free; keys avoided where possible)

| Source | Access method | Auth | Provides |
|---|---|---|---|
| **Hacker News** | Official Firebase API | None | Top tech links & discussion |
| **GitHub Trending** | GitHub Search API (recent repos by stars, AI/dev topics) | The repo's built-in `GITHUB_TOKEN` | Fast-rising projects |
| **Reddit** | Public `.json` listing endpoints | None | Learning, career, hands-on AI |
| **World news** | RSS feeds (e.g. BBC World, Reuters, AP) | None | Major global headlines |

**Reddit subreddits (v1, editable list):** `r/learnprogramming`, `r/cscareerquestions`, `r/LocalLLaMA`, `r/artificial`.

**Notes:**
- Reddit public JSON is rate-limited but ample for one daily batch; if limits are hit, back off and rely on the last-good digest (see §9), or add free Reddit API credentials later.
- GitHub trending has no official API; the GitHub Search API (recent creation date sorted by stars, filtered by relevant topics) is a robust, free stand-in using the token already available in Actions.
- The source set is defined in one configuration module so sources and thresholds can be added/removed without touching pipeline logic.

---

## 9. Reliability and error handling

- **Per-source isolation:** a failing source contributes nothing but never aborts the run; the digest is built from whatever succeeded. Failures are recorded in `status.sources_failed`.
- **AI fallback:** if the LLM is unavailable or rate-limited, skip summarization and emit the top pre-filtered items using their original titles, with `status.ai_used = false`. The user still gets a usable (if less polished) digest.
- **Last-good digest:** if an entire run fails before publishing, the previously committed `digest.json` remains in place and stays cached on the phone. The user never sees a blank screen.
- **Failure visibility:** GitHub emails the owner when an Actions run fails.
- **Manual trigger:** the workflow includes `workflow_dispatch` so the user can force a fresh run on demand from the GitHub UI.
- **Scheduling caveats accepted:** Actions cron is best-effort with a few minutes of possible drift (irrelevant for a daily briefing); the daily commit prevents the 60-day inactivity auto-disable.
- **Freshness display:** the app shows the `generated_at` timestamp so the user always knows how current the digest is.

---

## 10. Keeping the door open (future multi-user)

The design isolates two boundaries that make growth an evolution rather than a rewrite:
- **The digest contract:** the app only knows "fetch a digest document and render it." Today that document is a static `digest.json`; later it can become a per-user API endpoint returning the same shape.
- **The profile boundary:** today a single `profile.md`/secret; later per-user data behind authentication.

The six pipeline stages, the data model, and the entire PWA UI survive that transition unchanged. Only the storage of profiles and the serving of digests would be swapped (e.g., to Approach B: a serverless scheduler + per-user storage).

---

## 11. The app (plain HTML/CSS/JavaScript PWA)

Deliberately minimal and build-tool-free so a beginner can read and understand every file.

**Files:**
- `index.html` — structure.
- `style.css` — clean, readable, dark-mode-friendly typography.
- `app.js` — fetch `digest.json`, render sections and cards, handle refresh and offline state.
- `manifest.json` — name, icons, theme, `display: standalone` for home-screen install.
- `sw.js` — service worker caching the app shell and the last digest for offline reading.
- `icons/` — app icons.

**Behaviors:**
- Fetch and render `digest.json` grouped by section as compact cards: title, "why it matters to you" line, 1–2 sentence summary, source badge + signal, tap-to-open source link.
- **Offline:** service worker serves the cached app and the last digest when there is no network — ideal for commuting.
- **Installable:** "Add to Home Screen" yields a real icon and full-screen launch. (On iOS this is done via Safari's Share menu.)
- **Freshness & control:** show the "Updated HH:MM" timestamp; provide a manual refresh that re-fetches `digest.json`.
- **Honest degradation:** if `status.ai_used` is false or sources failed, show a small, non-alarming note.

**Card layout (reference sketch):**
```
┌────────────────────────────────────────────┐
│ 🤖 AI & Tools                               │
│                                            │
│  <Item title>                               │
│  → <why it matters to you>                  │
│  <1–2 sentence summary>                     │
│  Hacker News · 340 pts                    → │
└────────────────────────────────────────────┘
```

---

## 12. Scope — what v1 does NOT include (YAGNI)

Cut on purpose to ship something used daily: X/Twitter, push notifications, user accounts, behavioral learning, bookmarking/read-sync, full-article scraping, and in-app search. Each is a clean future add; none is required for a daily briefing. arXiv is also deferred for v1 (too research-dense for the current stage) and can be reintroduced later as a "light" source.

---

## 13. Cost plan

| Piece | Service | Cost |
|---|---|---|
| Scheduled compute | GitHub Actions | $0 |
| Hosting | GitHub Pages | $0 |
| Storage | The repo | $0 |
| AI | Gemini free tier (Groq fallback) | $0 within rate limits |

The pre-filter keeps AI usage to a few batched calls per day, comfortably inside free limits. The only ceiling is rate limits, not dollars.

---

## 14. Testing strategy

- **Unit tests with mocked responses** for each source fetcher, the normalizer, the pre-filter, and the assembler — no live network required.
- **AI stage tested against a recorded mock response** so tests never spend live API calls; a separate, opt-in integration check can exercise the real API sparingly.
- **`--dry-run` mode** runs the full pipeline and prints the resulting digest without committing — the primary fast feedback loop during development.
- **App:** previewed locally via a simple static server; manual verification of render, offline behavior, and install.
- Implementation follows a test-first workflow.

---

## 15. Configuration summary (concrete values, all editable)

- **Schedule:** ~06:17 user-local, once daily (UTC cron in the workflow; timezone provided at setup).
- **Sources:** Hacker News, GitHub (Search API), Reddit (`r/learnprogramming`, `r/cscareerquestions`, `r/LocalLLaMA`, `r/artificial`), world-news RSS.
- **Candidate cap:** 50; **items/section:** 5–7.
- **LLM:** Gemini Flash-class (default), Groq (fallback); exact model id + limits confirmed at implementation.
- **Repo visibility:** public; profile optionally private via Actions secret.
