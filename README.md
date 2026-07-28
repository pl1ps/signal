# Signal

A personal daily briefing. It reads Hacker News, GitHub, Reddit, and world news
every morning, uses AI to keep only what matters to you, and serves it as an
installable phone app. Runs on free tiers only.

## How it works

A scheduled GitHub Action runs a Python pipeline once a day. The pipeline fetches
a few hundred items, cheaply filters them to about 50 candidates, asks Gemini which
are worth your time, and writes `digest.json`. GitHub Pages serves this repo, so the
app fetches that file and caches it for offline reading.

**Sources:**
- Hacker News (posts with 50+ points)
- GitHub (repos created in the last 7 days with 50+ stars — there's no official
  "trending" API, so this is the closest approximation)
- Reddit: r/learnprogramming, r/cscareerquestions, r/LocalLLaMA, r/artificial
  (posts with 100+ upvotes)
- World news: BBC World, NPR News, and Al Jazeera RSS feeds

## Setup

### 1. Get a free Gemini API key
Visit https://aistudio.google.com/apikey and create a key.

The AI stage uses the **`gemini-3.6-flash`** model. Note: some models (e.g.
`gemini-2.0-flash`) have a **zero** free-tier quota on some accounts and will
always 429 — `gemini-3.6-flash` is the confirmed free-tier model here. To test
what a key is allowed, run:

    GEMINI_API_KEY=your_key python -m pipeline.ai_check

It prints "OK ..." if the model is reachable, or the exact quota error if not.

### 2. Add it as a repository secret
Repo → Settings → Secrets and variables → Actions → New repository secret.
Name it exactly `GEMINI_API_KEY`.

(GitHub Actions also passes the repo's built-in `GITHUB_TOKEN` to the pipeline
automatically as `GH_TOKEN` — this just raises the GitHub API rate limit. You
don't need to create it yourself.)

### 3. Connect Reddit (so it works from GitHub Actions)

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

### 4. Turn on GitHub Pages
Repo → Settings → Pages → Source: **Deploy from a branch** → Branch: `main`, folder `/ (root)`.
Your app appears at `https://<your-username>.github.io/<repo-name>/`.

### 5. Set your schedule
Edit `.github/workflows/digest.yml`. The cron is in **UTC**. To get a 06:17 local
briefing, subtract your UTC offset from 06:17:

| Your timezone | cron line |
|---|---|
| UTC+0 | `"17 6 * * *"` |
| UTC+1 | `"17 5 * * *"` |
| UTC+8 | `"17 22 * * *"` |
| UTC-5 | `"17 11 * * *"` |

The workflow ships with `"17 22 * * *"` (a UTC+8 06:17 briefing) — edit it to match
your own timezone.

### 6. Write your profile
Edit `profile.md` to describe your interests. This drives what gets kept and how
each item is explained to you. Keep the `Keywords:` line — the cheap pre-filter uses it.

To keep your profile out of a public repo, add its text as a secret named `PROFILE`
and add `PROFILE: ${{ secrets.PROFILE }}` under the "Build digest" step's `env:`.

### 7. Fonts and icons
Self-hosted fonts (`fonts/`) and home-screen icons (`icons/`) are already included.
To use your own, see `fonts/README.md` and `icons/README.md` for the exact files and
sizes to replace — the app degrades gracefully (system font, no icon) if either is
ever missing.

### 8. Run it once
Repo → Actions → "Build digest" → **Run workflow**. Then open your Pages URL.

### 9. Install it on your phone
- **iPhone:** open the URL in **Safari** → Share → Add to Home Screen.
- **Android:** open in Chrome → menu → Install app.

## Running locally

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest -q                # run the tests
python3 -m pipeline.main --dry-run  # print a digest without writing the file
python3 -m http.server 8000         # preview the app at localhost:8000
```

Set `GEMINI_API_KEY` in your shell to exercise the AI stage locally. Without it the
pipeline still runs and falls back to raw headlines. You can also set `GH_TOKEN` to
raise the GitHub API rate limit.

## Tuning

Everything adjustable lives in `pipeline/config.py`: sources, subreddits, RSS feeds,
score thresholds, how many items per section, and the model name.

## When something breaks

The digest is built to degrade rather than fail. A dead source is skipped, an
unavailable AI falls back to raw headlines, and a failed run leaves yesterday's
digest in place. GitHub emails you when a run fails; the app shows a note when
part of the digest is missing.
