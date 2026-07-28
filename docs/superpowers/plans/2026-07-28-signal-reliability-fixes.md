# Signal Reliability Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two production bugs in the live Signal app — Reddit never contributes (blocked on datacenter IPs) and the AI stage always falls back to raw headlines (`gemini-2.0-flash` has zero free-tier quota) — so the daily digest carries Reddit content and real AI summaries.

**Architecture:** Rewrite the Reddit source to use application-only OAuth (works from GitHub Actions IPs). Switch the Gemini model to `gemini-3.6-flash` (confirmed free-tier quota), send the API key in a header, add a `responseSchema` for consistent JSON, make parsing safe for "thinking" models, add retry/backoff, and add a standalone `ai_check` probe. Every failure path keeps the existing graceful-degradation contract (the run always produces a digest).

**Tech Stack:** Python 3.9-compatible (CI runs 3.12); `requests`; `pytest`; Gemini REST API; Reddit OAuth; GitHub Actions.

## Global Constraints

- Python 3.9-compatible: no `X | Y` type unions, no `match` statements. (CI runs 3.12; only 3.9.6 is installed locally.)
- Runtime dependencies limited to `requests`, `feedparser`, `pytest` — no others.
- Secrets (`GEMINI_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, Reddit bearer token) come only from the environment / GitHub Actions secrets. They must never be logged or written to `digest.json`.
- **Graceful degradation is mandatory:** no change may introduce a path that aborts the run or blanks the screen. A source that fails returns `[]` (isolated by `fetch_safe`); the AI stage on any failure returns `(items, False)`.
- Tests must not make real network calls — inject fakes.
- Beginner-readable code: short functions, explicit names, comments only where intent is non-obvious.
- The pre-existing macOS-only `NotOpenSSLWarning` from urllib3 is environmental; do not suppress it and do not treat it as a new finding.
- The chosen model is exactly `gemini-3.6-flash`. Confirmed live: `gemini-2.0-flash` returns `limit: 0` free-tier quota; `gemini-flash-latest` returns normal completions for this account.

---

## File map

- `pipeline/sources/reddit.py` — rewritten: OAuth token + authenticated listing fetch (Task 1).
- `pipeline/main.py` — `gather()` reads and forwards Reddit credentials (Task 2).
- `.github/workflows/digest.yml` — two new `env:` entries (Task 2).
- `pipeline/config.py` — model → `gemini-3.6-flash`, response schema, retry constants (Tasks 3, 4).
- `pipeline/ai.py` — header auth, response schema, thinking-safe parsing, full error-body logging (Task 3), retry/backoff (Task 4).
- `pipeline/ai_check.py` — new standalone Gemini probe (Task 5).
- `README.md` — Reddit app setup, new secrets, model note, `ai_check` usage (Task 6).
- Tests: `tests/test_reddit.py`, `tests/test_main.py`, `tests/test_ai.py`, `tests/test_ai_check.py`.

---

## Task 1: Reddit via application-only OAuth

**Files:**
- Modify: `pipeline/sources/reddit.py` (full rewrite)
- Test: `tests/test_reddit.py` (full rewrite)

**Interfaces:**
- Consumes: `Item` (`pipeline/models.py`), `iso_from_epoch` (`pipeline/sources/base.py`), `config.REDDIT_MIN_UPVOTES`.
- Produces: `fetch(subreddits, client_id, client_secret, limit=15, session=None) -> list[Item]`; internal `_get_token(client_id, client_secret, http) -> str | None`. `session`/`http` must expose `.post(url, auth=, data=, headers=, timeout=)` and `.get(url, params=, headers=, timeout=)`, each returning an object with `.json()`.

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `tests/test_reddit.py` with:
```python
from pipeline.sources import reddit


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeRedditSession:
    """Serves a canned token from .post and a canned listing from .get."""

    def __init__(self, token_payload, listing_payload):
        self.token_payload = token_payload
        self.listing_payload = listing_payload
        self.post_calls = []
        self.get_calls = []

    def post(self, url, auth=None, data=None, headers=None, timeout=None):
        self.post_calls.append({"url": url, "auth": auth, "data": data, "headers": headers})
        return FakeResp(self.token_payload)

    def get(self, url, params=None, headers=None, timeout=None):
        self.get_calls.append({"url": url, "params": params, "headers": headers})
        return FakeResp(self.listing_payload)


def _listing(title, ups, permalink="/r/x/comments/1/a/"):
    return {"data": {"children": [{"data": {
        "title": title, "ups": ups, "permalink": permalink,
        "selftext": "body text", "created_utc": 1753156620, "url": "https://ex.com/p",
    }}]}}


def test_fetch_authenticates_then_reads_listing():
    session = FakeRedditSession({"access_token": "tok123"},
                                _listing("How do I learn Python?", 500))

    items = reddit.fetch(["learnprogramming"], "cid", "secret", session=session)

    assert len(items) == 1
    assert items[0].source == "reddit"
    assert items[0].source_label == "r/learnprogramming"
    assert items[0].signal_metric == "upvotes"
    assert items[0].signal_value == 500
    # Token exchange used HTTP Basic auth + client-credentials grant.
    assert session.post_calls[0]["auth"] == ("cid", "secret")
    assert session.post_calls[0]["data"]["grant_type"] == "client_credentials"
    # Listing request hit the OAuth host with a bearer token and a User-Agent.
    assert "oauth.reddit.com" in session.get_calls[0]["url"]
    assert session.get_calls[0]["headers"]["Authorization"] == "bearer tok123"
    assert "User-Agent" in session.get_calls[0]["headers"]


def test_fetch_returns_empty_without_credentials():
    session = FakeRedditSession({"access_token": "tok"}, _listing("x", 500))
    assert reddit.fetch(["learnprogramming"], "", "", session=session) == []
    assert session.post_calls == []  # never even requested a token


def test_fetch_returns_empty_when_token_missing():
    session = FakeRedditSession({}, _listing("x", 500))  # no access_token key
    assert reddit.fetch(["learnprogramming"], "cid", "secret", session=session) == []
    assert session.get_calls == []  # no token -> never fetched a listing


def test_fetch_drops_posts_below_threshold():
    session = FakeRedditSession({"access_token": "tok"}, _listing("Low effort", 3))
    assert reddit.fetch(["learnprogramming"], "cid", "secret", session=session) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_reddit.py -v`
Expected: FAIL — `TypeError` (old `fetch` signature has no `client_id`/`client_secret`) or assertion errors on the new auth behavior.

- [ ] **Step 3: Rewrite the implementation**

Replace the entire contents of `pipeline/sources/reddit.py` with:
```python
"""Reddit via application-only OAuth (no user password required).

Reddit blocks unauthenticated JSON requests from datacenter IPs (GitHub
Actions runners), so we authenticate with a "script" app's client
credentials and read listings from the OAuth host.
"""

import requests

from pipeline import config
from pipeline.models import Item
from pipeline.sources.base import iso_from_epoch

USER_AGENT = "signal-digest/1.0 (personal daily briefing)"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"


def _get_token(client_id, client_secret, http):
    """Exchange client credentials for an application-only bearer token."""
    response = http.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    return response.json().get("access_token")


def fetch(subreddits, client_id, client_secret, limit=15, session=None):
    """Return top posts of the day from each subreddit as Items.

    Returns [] if credentials are missing or the token cannot be obtained,
    so a Reddit outage never aborts the run.
    """
    if not client_id or not client_secret:
        return []

    http = session or requests
    token = _get_token(client_id, client_secret, http)
    if not token:
        return []

    auth_headers = {"Authorization": f"bearer {token}", "User-Agent": USER_AGENT}
    items = []
    for sub in subreddits:
        payload = http.get(
            f"{API_BASE}/r/{sub}/top",
            params={"t": "day", "limit": limit},
            headers=auth_headers,
            timeout=15,
        ).json()

        for child in payload.get("data", {}).get("children", []):
            post = child.get("data", {})
            ups = post.get("ups", 0)
            if ups < config.REDDIT_MIN_UPVOTES:
                continue

            items.append(Item(
                title=post.get("title", ""),
                url=f"https://www.reddit.com{post.get('permalink', '')}",
                source="reddit",
                source_label=f"r/{sub}",
                snippet=(post.get("selftext") or "")[:300],
                signal_metric="upvotes",
                signal_value=ups,
                published_at=iso_from_epoch(post.get("created_utc")),
            ))
    return items
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_reddit.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: the Reddit tests pass; other tests are unaffected (the orchestrator wiring is updated in Task 2, but `gather` is monkeypatched in `test_main.py`, so nothing else breaks yet). One pre-existing `NotOpenSSLWarning`.

- [ ] **Step 6: Commit**

```bash
git add pipeline/sources/reddit.py tests/test_reddit.py
git commit -m "fix: fetch Reddit via application-only OAuth"
```

---

## Task 2: Forward Reddit credentials through the pipeline and workflow

**Files:**
- Modify: `pipeline/main.py` (`gather` signature + the `run` call site)
- Modify: `.github/workflows/digest.yml` (add two `env:` entries)
- Test: `tests/test_main.py` (update monkeypatch signatures; add a wiring test)

**Interfaces:**
- Consumes: `reddit.fetch(subreddits, client_id, client_secret, ...)` (Task 1), `config.SUBREDDITS`.
- Produces: `gather(gh_token=None, reddit_client_id=None, reddit_client_secret=None) -> (items, sources_ok, sources_failed)`.

- [ ] **Step 1: Write the failing wiring test**

Add to `tests/test_main.py` (keep the existing tests; add this and the import if not present):
```python
from pipeline import config


def test_gather_passes_reddit_credentials(monkeypatch):
    captured = {}

    def fake_reddit_fetch(subreddits, client_id, client_secret):
        captured["args"] = (subreddits, client_id, client_secret)
        return []

    monkeypatch.setattr(main.reddit, "fetch", fake_reddit_fetch)
    monkeypatch.setattr(main.hackernews, "fetch", lambda: [])
    monkeypatch.setattr(main.github, "fetch", lambda token=None: [])
    monkeypatch.setattr(main.news, "fetch", lambda feeds: [])

    main.gather("ghtok", "cid", "secret")

    assert captured["args"] == (config.SUBREDDITS, "cid", "secret")
```

- [ ] **Step 2: Update the existing `run` tests' `gather` monkeypatches**

In `tests/test_main.py`, the existing tests replace `gather` with a lambda that takes a single `token` argument. `run` now calls `gather` with three positional arguments, so those lambdas must accept them. Change each `monkeypatch.setattr(main, "gather", lambda token=None: (...))` to:
```python
    monkeypatch.setattr(main, "gather", lambda *args, **kwargs: (...))
```
(Apply to every `gather` monkeypatch in the file — `test_run_writes_digest_json` and `test_run_dry_run_does_not_write`. Keep the returned tuple exactly as it was in each test.)

- [ ] **Step 3: Run to verify the new test fails**

Run: `python3 -m pytest tests/test_main.py::test_gather_passes_reddit_credentials -v`
Expected: FAIL — `TypeError` (current `gather(token=None)` doesn't accept three args / doesn't pass credentials to `reddit.fetch`).

- [ ] **Step 4: Update `gather` and the `run` call site**

In `pipeline/main.py`, replace the `gather` function with:
```python
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
```

In the same file, replace the single `gather(...)` call inside `run` with:
```python
    raw_items, sources_ok, sources_failed = gather(
        os.environ.get("GH_TOKEN"),
        os.environ.get("REDDIT_CLIENT_ID"),
        os.environ.get("REDDIT_CLIENT_SECRET"),
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_main.py -v`
Expected: PASS (all `test_main` tests, including the new wiring test).

- [ ] **Step 6: Add the workflow secrets**

In `.github/workflows/digest.yml`, under the **Build digest** step's `env:` block (which already has `GEMINI_API_KEY` and `GH_TOKEN`), add these two lines:
```yaml
          REDDIT_CLIENT_ID: ${{ secrets.REDDIT_CLIENT_ID }}
          REDDIT_CLIENT_SECRET: ${{ secrets.REDDIT_CLIENT_SECRET }}
```

- [ ] **Step 7: Verify the workflow YAML parses**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/digest.yml')); print('workflow YAML OK')"`
Expected: `workflow YAML OK`
(If PyYAML is not installed, `python3 -m pip install --user pyyaml` first — a local check only; do NOT add it to `requirements.txt`.)

- [ ] **Step 8: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all pass, one pre-existing `NotOpenSSLWarning`.

- [ ] **Step 9: Commit**

```bash
git add pipeline/main.py tests/test_main.py .github/workflows/digest.yml
git commit -m "feat: forward Reddit OAuth credentials from env and workflow"
```

---

## Task 3: AI — switch model, header auth, response schema, thinking-safe parsing

**Files:**
- Modify: `pipeline/config.py` (model + response schema)
- Modify: `pipeline/ai.py` (header auth, schema in body, robust parse, full error-body logging)
- Test: `tests/test_ai.py` (update fakes; add tests)

**Interfaces:**
- Consumes: `config.GEMINI_MODEL`, `config.GEMINI_URL`, `config.GEMINI_RESPONSE_SCHEMA`, `config.SECTIONS`.
- Produces: unchanged public signature `rank_and_summarize(profile, items, api_key, session=None) -> (items, ai_used)`; `session.post` is now called as `.post(url, json=, headers=, timeout=)`. `_parse_text(payload) -> str` now concatenates non-thought text parts.

- [ ] **Step 1: Update config**

In `pipeline/config.py`, change the model line:
```python
GEMINI_MODEL = "gemini-3.6-flash"
```
And add, directly below the existing `GEMINI_URL` line, the response schema (Gemini uses uppercase OpenAPI-subset type names):
```python
# Structured-output schema so Gemini returns consistent, parseable JSON.
GEMINI_RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "index": {"type": "INTEGER"},
            "keep": {"type": "BOOLEAN"},
            "section": {"type": "STRING"},
            "why": {"type": "STRING"},
            "summary": {"type": "STRING"},
            "relevance": {"type": "NUMBER"},
        },
        "required": ["index", "keep"],
    },
}
```

- [ ] **Step 2: Write the failing tests**

In `tests/test_ai.py`, update the fakes and add tests. Replace the `FakeResponse` and `FakeSession` classes with these (adds `.text`, a `headers` kwarg, and records the call), and add the four new tests below:
```python
class FakeResponse:
    def __init__(self, payload, status=200, text=""):
        self._payload = payload
        self.status_code = status
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            error = RuntimeError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.last_url = None
        self.last_headers = None

    def post(self, url, json=None, headers=None, timeout=None):
        self.last_url = url
        self.last_headers = headers
        return self.response


def test_rank_and_summarize_sends_key_in_header_not_url():
    session = FakeSession(FakeResponse(gemini_envelope("[]")))
    ai.rank_and_summarize("profile", [make("A story")], api_key="secretkey", session=session)
    assert session.last_headers["x-goog-api-key"] == "secretkey"
    assert "secretkey" not in session.last_url
    assert "key=" not in session.last_url


def test_rank_and_summarize_requests_structured_output():
    captured = {}

    class CapturingSession:
        def post(self, url, json=None, headers=None, timeout=None):
            captured["body"] = json
            return FakeResponse(gemini_envelope("[]"))

    ai.rank_and_summarize("profile", [make("A story")], api_key="k", session=CapturingSession())
    gen = captured["body"]["generationConfig"]
    assert gen["responseMimeType"] == "application/json"
    assert gen["responseSchema"]["type"] == "ARRAY"


def test_parse_text_skips_thinking_parts():
    payload = {"candidates": [{"content": {"parts": [
        {"text": "internal reasoning", "thought": True},
        {"text": "[{\"index\": 0, \"keep\": true}]"},
    ]}}]}
    assert ai._parse_text(payload) == "[{\"index\": 0, \"keep\": true}]"


def test_rank_and_summarize_logs_error_body_on_failure(caplog):
    body = '{"error":{"code":429,"message":"quota"}}'
    session = FakeSession(FakeResponse({}, status=429, text=body))
    items, ai_used = ai.rank_and_summarize("profile", [make("A story")],
                                           api_key="k", session=session)
    assert ai_used is False
    assert "quota" in caplog.text  # the real error body reached the log
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_ai.py -v`
Expected: FAIL — key still in URL, no `responseSchema`, `_parse_text` takes only `parts[0]`, and the error body is not logged.

- [ ] **Step 4: Update the implementation**

In `pipeline/ai.py`, replace `_parse_text` and `rank_and_summarize`, and add the `_log_ai_failure` helper:
```python
def _parse_text(payload):
    """Concatenate the answer text, skipping any 'thinking' parts.

    gemini-3.6-flash is a thinking model: a response may include a reasoning
    part (marked thought=True) before the answer part. We want only the answer.
    """
    parts = payload["candidates"][0]["content"]["parts"]
    texts = [p["text"] for p in parts if "text" in p and not p.get("thought")]
    return "".join(texts)


def _log_ai_failure(exc, api_key):
    """Log the failure with the real error body, never the API key."""
    detail = str(exc)
    response = getattr(exc, "response", None)
    if response is not None:
        body = getattr(response, "text", "")
        if body:
            detail += " | body: " + body
    log.warning("AI stage failed, falling back to raw items: %s",
                detail.replace(api_key, "<redacted>"))


def rank_and_summarize(profile, items, api_key, session=None):
    """Return (items, ai_used). On any failure, returns the input untouched."""
    if not api_key or not items:
        log.warning("AI stage skipped: no API key or no items")
        return items, False

    http = session or requests
    url = config.GEMINI_URL.format(model=config.GEMINI_MODEL)
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = {
        "contents": [{"parts": [{"text": build_prompt(profile, items)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": config.GEMINI_RESPONSE_SCHEMA,
            "temperature": 0.2,
        },
    }

    try:
        response = http.post(url, json=body, headers=headers, timeout=90)
        response.raise_for_status()
        verdicts = json.loads(_parse_text(response.json()))
        return apply_verdicts(items, verdicts), True
    except Exception as exc:  # broad: the digest must survive any AI failure
        _log_ai_failure(exc, api_key)
        return items, False
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_ai.py -v`
Expected: PASS (all `test_ai` tests, including the four new ones; the existing `test_rank_and_summarize_parses_model_output` still passes because a single answer part concatenates to itself).

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all pass, one pre-existing `NotOpenSSLWarning`.

- [ ] **Step 7: Commit**

```bash
git add pipeline/config.py pipeline/ai.py tests/test_ai.py
git commit -m "fix: use gemini-3.6-flash with header auth, response schema, thinking-safe parsing"
```

---

## Task 4: AI — retry with backoff on transient errors

**Files:**
- Modify: `pipeline/config.py` (retry constants)
- Modify: `pipeline/ai.py` (`rank_and_summarize` retry loop + `_is_retryable`)
- Test: `tests/test_ai.py` (add retry tests)

**Interfaces:**
- Consumes: `config.GEMINI_MAX_ATTEMPTS`, `config.GEMINI_BACKOFF_BASE`.
- Produces: `rank_and_summarize(profile, items, api_key, session=None, sleep=time.sleep) -> (items, ai_used)` — an injectable `sleep` (default `time.sleep`) so tests run instantly; internal `_is_retryable(exc) -> bool`.

- [ ] **Step 1: Add retry constants to config**

In `pipeline/config.py`, add below the schema:
```python
# AI request retry (transient 429/5xx only; a structural 429 is not retryable)
GEMINI_MAX_ATTEMPTS = 3
GEMINI_BACKOFF_BASE = 1.0   # seconds; delay = base * 2**attempt
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_ai.py`:
```python
class SequenceSession:
    """Returns queued responses in order, one per .post call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls += 1
        return self.responses.pop(0)


def test_rank_and_summarize_retries_then_succeeds():
    ok = gemini_envelope(json.dumps([{"index": 0, "keep": True, "section": "world",
                                      "why": "w", "summary": "s", "relevance": 0.7}]))
    session = SequenceSession([FakeResponse({}, status=429, text="quota"),
                               FakeResponse(ok)])
    sleeps = []

    items, ai_used = ai.rank_and_summarize("profile", [make("A story")], api_key="k",
                                           session=session, sleep=lambda s: sleeps.append(s))

    assert ai_used is True
    assert session.calls == 2
    assert len(sleeps) == 1  # one backoff between the two attempts


def test_rank_and_summarize_gives_up_after_max_attempts():
    session = SequenceSession([FakeResponse({}, status=429, text="quota")
                               for _ in range(5)])
    sleeps = []

    original = [make("A story")]
    items, ai_used = ai.rank_and_summarize("profile", original, api_key="k",
                                           session=session, sleep=lambda s: sleeps.append(s))

    assert ai_used is False
    assert items == original
    assert session.calls == 3           # config.GEMINI_MAX_ATTEMPTS
    assert len(sleeps) == 2             # backoff between attempts, not after the last


def test_rank_and_summarize_does_not_retry_non_retryable():
    session = SequenceSession([FakeResponse({}, status=400, text="bad request")])
    sleeps = []

    ai.rank_and_summarize("profile", [make("A story")], api_key="k",
                          session=session, sleep=lambda s: sleeps.append(s))

    assert session.calls == 1           # 400 is not retried
    assert sleeps == []
```

- [ ] **Step 3: Run to verify they fail**

Run: `python3 -m pytest tests/test_ai.py -k retry -v` and `... -k non_retryable -v`
Expected: FAIL — `rank_and_summarize` has no `sleep` parameter and does not retry.

- [ ] **Step 4: Add the retry loop**

In `pipeline/ai.py`, add `import time` at the top (with the other imports) and add near the other helpers:
```python
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc):
    """Retry only transient HTTP statuses; a structural 429 will just repeat,
    but the bounded loop still exits quickly and falls back."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status in RETRYABLE_STATUS
```
Then replace `rank_and_summarize` with the retrying version:
```python
def rank_and_summarize(profile, items, api_key, session=None, sleep=time.sleep):
    """Return (items, ai_used). On any failure, returns the input untouched."""
    if not api_key or not items:
        log.warning("AI stage skipped: no API key or no items")
        return items, False

    http = session or requests
    url = config.GEMINI_URL.format(model=config.GEMINI_MODEL)
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = {
        "contents": [{"parts": [{"text": build_prompt(profile, items)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": config.GEMINI_RESPONSE_SCHEMA,
            "temperature": 0.2,
        },
    }

    last_exc = None
    for attempt in range(config.GEMINI_MAX_ATTEMPTS):
        try:
            response = http.post(url, json=body, headers=headers, timeout=90)
            response.raise_for_status()
            verdicts = json.loads(_parse_text(response.json()))
            return apply_verdicts(items, verdicts), True
        except Exception as exc:  # broad: the digest must survive any AI failure
            last_exc = exc
            is_last = attempt == config.GEMINI_MAX_ATTEMPTS - 1
            if is_last or not _is_retryable(exc):
                break
            sleep(config.GEMINI_BACKOFF_BASE * (2 ** attempt))

    _log_ai_failure(last_exc, api_key)
    return items, False
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_ai.py -v`
Expected: PASS (all, including the three retry tests). Note the existing failure test `test_rank_and_summarize_falls_back_when_request_fails` uses a `BoomSession` raising a plain `RuntimeError` (no `.response`), so `_is_retryable` is `False` and it falls back after one attempt — still passing.

- [ ] **Step 6: Commit**

```bash
git add pipeline/config.py pipeline/ai.py tests/test_ai.py
git commit -m "feat: retry the AI request with backoff on transient errors"
```

---

## Task 5: `ai_check` — standalone Gemini probe

**Files:**
- Create: `pipeline/ai_check.py`
- Test: `tests/test_ai_check.py`

**Interfaces:**
- Consumes: `config.GEMINI_MODEL`, `config.GEMINI_URL`.
- Produces: `check(api_key, session=None) -> (ok: bool, detail: str)`; a `main()` that reads `GEMINI_API_KEY`, prints the detail, and exits 0 on success / 1 on failure. Runnable as `python -m pipeline.ai_check`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ai_check.py`:
```python
from pipeline import ai_check


class FakeResponse:
    def __init__(self, status=200, text="", payload=None):
        self.status_code = status
        self.text = text
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.last_headers = None

    def post(self, url, json=None, headers=None, timeout=None):
        self.last_headers = headers
        return self.response


def test_check_reports_ok_on_200():
    session = FakeSession(FakeResponse(status=200))
    ok, detail = ai_check.check("k", session=session)
    assert ok is True
    assert session.last_headers["x-goog-api-key"] == "k"


def test_check_reports_quota_body_on_429():
    session = FakeSession(FakeResponse(status=429, text='{"error":{"message":"limit: 0"}}'))
    ok, detail = ai_check.check("k", session=session)
    assert ok is False
    assert "limit: 0" in detail


def test_check_reports_missing_key():
    ok, detail = ai_check.check("", session=None)
    assert ok is False
    assert "GEMINI_API_KEY" in detail
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_ai_check.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.ai_check'`.

- [ ] **Step 3: Write the implementation**

Create `pipeline/ai_check.py`:
```python
"""One-shot Gemini connectivity/quota probe.

Run:  python -m pipeline.ai_check
Prints whether GEMINI_MODEL is reachable and within quota for the key in
GEMINI_API_KEY, or the exact error body (which names the quota) on failure.
"""

import os
import sys

import requests

from pipeline import config


def check(api_key, session=None):
    """Return (ok, detail). Never includes the API key in the detail."""
    if not api_key:
        return False, "No GEMINI_API_KEY in environment."

    http = session or requests
    url = config.GEMINI_URL.format(model=config.GEMINI_MODEL)
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = {"contents": [{"parts": [{"text": "Reply with the single word: ok"}]}]}

    try:
        response = http.post(url, json=body, headers=headers, timeout=30)
        if response.status_code == 200:
            return True, f"OK - {config.GEMINI_MODEL} is reachable and within quota."
        return False, f"HTTP {response.status_code}: {response.text}".replace(api_key, "<redacted>")
    except Exception as exc:
        detail = str(exc)
        response = getattr(exc, "response", None)
        if response is not None:
            detail += " | body: " + getattr(response, "text", "")
        return False, detail.replace(api_key, "<redacted>")


def main():
    ok, detail = check(os.environ.get("GEMINI_API_KEY"))
    print(detail)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_ai_check.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all pass, one pre-existing `NotOpenSSLWarning`.

- [ ] **Step 6: Commit**

```bash
git add pipeline/ai_check.py tests/test_ai_check.py
git commit -m "feat: add ai_check Gemini connectivity/quota probe"
```

---

## Task 6: Documentation

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: the setup steps for Reddit OAuth and the note on the model + probe.

- [ ] **Step 1: Update the README**

In `README.md`, make these edits:

(a) In the Setup section, add a **Reddit** subsection:
```markdown
### Connect Reddit (so it works from GitHub Actions)

Reddit blocks unauthenticated requests from datacenter IPs, so the pipeline
authenticates with a free Reddit app.

1. Go to https://www.reddit.com/prefs/apps → **Create another app**.
2. Choose type **script**. Set the redirect URI to `http://localhost` (unused).
3. Copy the **client ID** (under the app name) and the **secret**.
4. Add both as repository secrets (Settings → Secrets and variables → Actions):
   - `REDDIT_CLIENT_ID`
   - `REDDIT_CLIENT_SECRET`

No Reddit username or password is stored. If these secrets are absent, the app
simply skips Reddit and still builds the digest from the other sources.
```

(b) Update the AI/Gemini note to state the model and the probe. Add near the Gemini key step:
```markdown
The AI stage uses the **`gemini-3.6-flash`** model. Note: some models (e.g.
`gemini-2.0-flash`) have a **zero** free-tier quota on some accounts and will
always 429 — `gemini-3.6-flash` is the confirmed free-tier model here. To test
what a key is allowed, run:

    GEMINI_API_KEY=your_key python -m pipeline.ai_check

It prints "OK ..." if the model is reachable, or the exact quota error if not.
```

- [ ] **Step 2: Verify documented commands work**

Run: `python3 -m pytest -q`
Expected: all pass. (The `ai_check` command needs a real key and network, so it is not run here; its logic is covered by `tests/test_ai_check.py`.)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add Reddit OAuth setup and Gemini model/probe notes"
```

---

## Self-Review

**Spec coverage.** Spec §2 (Reddit OAuth) → Tasks 1–2 (rewrite + wiring + workflow secrets + README). §3 B1 (surface error) → Task 3 `_log_ai_failure` logs the full response body. B2 (responseSchema + thinking parse) → Task 3 (`GEMINI_RESPONSE_SCHEMA`, thinking-safe `_parse_text`). B3 (retry, secondary) → Task 4. B4 (configurable model, pinned `gemini-3.6-flash`) → Task 3 config. B5 (key in header) → Task 3 headers. B6 (`ai_check`) → Task 5. B7 (structural fix = model switch) → Task 3 config + Task 5 probe as the build-time gate. §4 (README, workflow, tests, security) → Tasks 2 and 6, and every task's tests are network-free. §7 definition-of-done items each map to a task.

**Deferred / not in this plan (per spec §5–6):** the UI redesign (separate pass), any thinking-budget `generationConfig` field (the robust parser handles thinking output without an unverified API field), and a live end-to-end Gemini/Reddit run — the implementer cannot hold the real secrets, so real confirmation is: the user runs `python -m pipeline.ai_check` and triggers the workflow. This is called out here rather than hidden.

**Placeholder scan.** No TBD/TODO. Every code step contains complete code; every test step contains real assertions; Task 2 Step 2 references specific existing tests by name and states the exact edit rather than "similar to".

**Type consistency.** `reddit.fetch(subreddits, client_id, client_secret, limit=15, session=None)` is defined in Task 1 and called with matching arguments in Task 2's `gather` and its wiring test. `gather(gh_token, reddit_client_id, reddit_client_secret)` defined and called consistently. `rank_and_summarize(..., sleep=time.sleep)` in Task 4 extends Task 3's signature additively (existing callers unaffected). `_parse_text`, `_log_ai_failure`, `_is_retryable`, `check` names are used consistently. `config.GEMINI_RESPONSE_SCHEMA`, `GEMINI_MAX_ATTEMPTS`, `GEMINI_BACKOFF_BASE` are defined before use.
