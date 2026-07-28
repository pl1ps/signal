# Signal Reliability Fixes — Design Spec

- **Date:** 2026-07-27
- **Status:** Approved design — ready for implementation planning
- **Scope:** Two production bug fixes (Reddit, AI summaries) shipped together; a UI redesign deferred to a separate follow-up pass.

---

## 1. Background

Signal ([github.com/pl1ps/signal](https://github.com/pl1ps/signal)) is live and the daily GitHub Actions job runs. Testing the deployed app surfaced three issues. Root causes were read directly from the production run logs, not assumed:

1. **Reddit never contributes.** Log: `WARNING source reddit failed: Expecting value: line 1 column 1 (char 0)`. Reddit returns a non-JSON block page to unauthenticated requests from datacenter IPs (GitHub Actions runners). `fetch_safe` isolates it, so the run survives, but Reddit is dead weight.
2. **No AI summaries — only raw headlines.** Log: `WARNING AI stage failed, falling back to raw items: 429 Client Error: Too Many Requests ... gemini-2.0-flash`. The `GEMINI_API_KEY` secret **is** set; the failure is a Gemini quota error (HTTP 429), so the pipeline correctly falls back to raw headlines (`ai_used: false`). **The Google AI Studio usage dashboard (28 days, free tier, project "Signal") shows only ~3 total API requests, of which essentially all errored — a ~100% error rate on near-zero volume.** This rules out volume-based quota exhaustion: the key hits 429 on essentially its first call, which is *structural*, not "used too much."

**Root cause confirmed** (from the live 429 body): `gemini-2.0-flash` has a **free-tier limit of `0`** on this project across every metric — `GenerateRequestsPerMinutePerProjectPerModel-FreeTier`, `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, and `GenerateContentInputTokensPerModelPerMinute-FreeTier` all report `limit: 0`. Google grants this specific model no free allowance for this account; the API worked at all times, it just refused this model. A live test confirmed free-tier quota *does* exist for the account on newer flash models (`gemini-flash-latest` returned a normal completion). **Resolution: switch the model** (see B7). No billing change and no provider change are required.
3. **UI reads as templated.** Functionality is fine; the visual design needs a distinctive pass. Deferred (see §5).

**Guiding constraints (unchanged from the original project):** Python 3.9-compatible (CI runs 3.12); runtime dependencies limited to `requests`, `feedparser`, `pytest`; no build tools/framework for the PWA; secrets only via env / GitHub Actions secrets, never logged or written to `digest.json`; graceful degradation is mandatory — no fix may introduce a path that aborts the run or blanks the screen; beginner-readable code.

---

## 2. Part A — Reddit via application-only OAuth

### Goal
Fetch subreddit listings reliably from GitHub Actions by authenticating, without storing a Reddit username or password.

### Approach
Use Reddit's **application-only ("userless") OAuth**:

1. The user creates a free Reddit **"script" app** at https://www.reddit.com/prefs/apps → obtains a **client ID** and **client secret**.
2. Stored as GitHub Actions secrets: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`. No username/password.
3. The pipeline requests a bearer token: `POST https://www.reddit.com/api/v1/access_token`, HTTP Basic auth `(client_id, client_secret)`, form body `grant_type=client_credentials`, with a descriptive `User-Agent`. It reads the `access_token` from the JSON response.
4. It then reads listings from `https://oauth.reddit.com/r/<sub>/top?t=day&limit=<n>` with headers `Authorization: bearer <token>` and the same `User-Agent`.
5. Items are mapped exactly as today (same `Item` fields, same `REDDIT_MIN_UPVOTES` threshold, same `iso_from_epoch` for `published_at`).

> **Implementation-time verification:** confirm `grant_type=client_credentials` is accepted for a "script" app against Reddit's current OAuth docs. If it is rejected, fall back to the documented userless path that still uses only the two `REDDIT_CLIENT_*` secrets. Do not adopt any flow that requires storing a Reddit account password.

### Interface / testability
- `fetch(subreddits, client_id, client_secret, limit=15, session=None)` — credentials passed in (read from env by the orchestrator), `session` injectable so tests never hit the network.
- A token helper (e.g. `_get_token(client_id, client_secret, session)`) that tests exercise with a fake session returning a canned `{"access_token": ...}`.

### Degradation (must hold)
If `client_id`/`client_secret` are absent, or the token request fails, or a listing request fails, `fetch` returns `[]` (or raises, caught by `fetch_safe`). Reddit landing in `sources_failed` must never abort the run — identical behavior to today.

### Orchestration
`pipeline/main.py`'s `gather()` reads `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` from the environment and passes them to `reddit.fetch`, still wrapped in `fetch_safe`.

### Config
`config.py` keeps the existing `SUBREDDITS` list. Any Reddit endpoint constants live in the source module or config, not hardcoded inline more than once.

---

## 3. Part B — AI: diagnose the 429, then harden

### Goal
Make the AI stage produce consistent summaries when quota allows, fail transient limits gracefully, and expose the true quota so the abnormal 429 can be understood.

### B1. Surface the real error (diagnosis)
The current handler logs only the exception's status line. Change it to capture and log **Gemini's full error response body** on failure — Gemini's 429 payload names the exact quota metric and its limit (e.g. requests-per-day vs per-minute, free-tier value). This turns "some 429" into a specific, actionable fact. The body must be logged **without** including the API key (the key currently travels in the URL query string — see B5).

### B2. Structured output via `responseSchema`
Send Gemini a `responseSchema` (with `responseMimeType: application/json`) describing the expected output exactly: a JSON array of objects `{index: int, keep: bool, section: string, why: string, summary: string, relevance: number}`. This eliminates malformed-JSON as a failure mode. `apply_verdicts` (existing) continues to validate `index` range and `section` membership defensively — the schema reduces, but does not replace, validation.

**Thinking-model note:** `gemini-3.6-flash` is a "thinking" model (its responses carry a `thoughtSignature`, and it may emit reasoning as a separate content part). The parser must extract the actual answer, not a reasoning part — `_parse_text` currently takes `parts[0].text`, which is not safe if a thought part precedes the answer. The implementation must either concatenate/select the text part that carries the JSON, or disable/limit "thinking" for this call (e.g. a zero/low thinking budget in `generationConfig`) so structured JSON output is deterministic. This must be verified against a real response during implementation.

### B3. Retry with backoff (secondary — not the primary fix)
The dashboard shows the current 429 is **structural, not volume-driven**, so retry/backoff will NOT resolve it — a request that fails structurally fails on every attempt. Retry/backoff is still worth adding as defensive hardening for genuinely transient per-minute limits once the structural cause (B1/B7) is resolved, but it is explicitly secondary. Wrap the Gemini request in a small bounded retry loop: a few attempts on `429`/`5xx` with exponential backoff (e.g. ~1s, 2s, 4s), never hanging a scheduled run. If all attempts fail, return `(items, False)`.

### B7. Resolve the structural cause (primary fix) — RESOLVED
The 429 body confirmed the cause: `gemini-2.0-flash` has `limit: 0` free-tier quota for this account, while newer flash models do have free quota (verified live). **The fix is a model switch, nothing more** — no billing, no provider change. Set `GEMINI_MODEL = "gemini-3.6-flash"` (B4) and confirm it via `ai_check` (B6) as the build-time gate. This single change is what restores summaries; B2–B5 are correctness/robustness improvements that matter once requests succeed. Record the working model in the README.

### B4. Configurable model & generation config
Set `config.GEMINI_MODEL = "gemini-3.6-flash"` (chosen: newest flash with confirmed free-tier quota for this account; `gemini-2.0-flash` was zeroed). Keep the model name and generation settings in `config.py` so a future switch is a one-line change. The generation config should carry the `responseSchema`/`responseMimeType` from B2 and any thinking-budget setting from B2's note.

> **Build-time gate:** the first AI-work step runs `python -m pipeline.ai_check` (B6) against `gemini-3.6-flash` and must show a real completion before the rest of the AI changes are trusted. If `gemini-3.6-flash` unexpectedly reports `limit: 0`, fall back to the confirmed-working `gemini-flash-latest` alias (or `gemini-3.5-flash`) and record the change. Record the chosen model in the README.

### B5. Send the key in a header, not the URL
Move the API key from the URL query string (`?key=...`) to the `x-goog-api-key` request header. URLs are the most leak-prone place for a secret (proxy logs, crash dumps, error bodies we now log in B1). This is a small, strict improvement that also makes B1's body-logging safe.

### B6. Standalone diagnostic
Add `python -m pipeline.ai_check`: makes one minimal Gemini call using `GEMINI_API_KEY` from the environment and prints the outcome — success, or the full error body/limits on 429. It must never print the key. This lets the user (or implementer) see exactly what a key is permitted without running the whole pipeline, and is the primary tool for resolving the abnormal-429 question.

### Degradation (must hold)
Every failure path in the AI stage still returns `(items, False)` so the digest renders raw headlines. No change to that contract.

---

## 4. Cross-cutting: setup, testing, security

### Setup docs (README)
Add a Reddit section: create a "script" app, copy client ID/secret, add `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` as repository secrets. Note the two new `env:` entries in the workflow. Document the chosen Gemini model and its free-tier limits, and mention `python -m pipeline.ai_check` as the way to test a key.

### Workflow
Add `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` to the "Build digest" step's `env:`, sourced from secrets. No other workflow change.

### Testing
- Reddit: unit tests for the token exchange (fake session → canned token) and listing mapping (fake session → canned listing), plus the no-credentials and failed-token degradation paths. Network-free.
- AI: unit tests for `responseSchema`-shaped parsing via `apply_verdicts`, the retry/backoff behavior (fake session raising 429 then succeeding; and exhausting retries → `(items, False)`), and that a failure returns the unchanged items. Backoff sleeps must be patched so tests are fast. Network-free.
- The full suite must stay green (currently 42 tests) and test output pristine (the pre-existing macOS-only `NotOpenSSLWarning` is environmental and stays).

### Security
- No secret (Gemini key, Reddit client secret, bearer token) may be logged or written to `digest.json`. The B1 error-body logging must be verified not to echo the key (guaranteed by B5 moving it to a header).
- Reddit bearer token is held only in memory for the run.

---

## 5. Part C — UI redesign (deferred, separate pass)

Not part of this plan's implementation. After A and B are merged and the app is showing real AI summaries and real Reddit content, run a dedicated design pass:
- Produce **2–3 distinct rendered visual directions** in the app's real HTML/CSS stack, screenshot each, and let the user choose one (or a blend).
- Designing against real content (not placeholder headlines) is why this comes second.
- This pass will use the frontend-design guidance and the browser tooling (Playwright render + screenshot) already available.

Tooling note for the user: external mockup tools (Google Stitch, v0.dev) are useful for inspiration to bring into that pass; the rendered-directions approach avoids a translation gap because what is approved is built in the shipping stack. ("Claude Design 2.0" was mentioned but is not a product this spec relies on; Claude Artifacts is the real equivalent for live UI preview.)

---

## 6. Out of scope (this plan)

- The UI redesign (Part C — separate pass).
- Adding a second daily run, changing sources beyond Reddit's auth, or any new source.
- Behavioral personalization, accounts, push — all still deferred as in the original spec.

---

## 7. Definition of done (Parts A + B)

- A scheduled run authenticates to Reddit and Reddit appears in `sources_ok` with items in the digest (verified against a real run).
- When quota allows, `ai_used: true` and items carry `why` + `summary`; when it doesn't, the run still produces a raw-headline digest.
- `python -m pipeline.ai_check` prints a clear success or the exact quota detail on 429.
- The API key is sent via header; no secret appears in any log or in `digest.json`.
- README documents the Reddit app setup, the two new secrets, the chosen Gemini model, and the diagnostic command.
- Full test suite green; new tests cover the Reddit token flow and the AI schema/retry paths, network-free.
