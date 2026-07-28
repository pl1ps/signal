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
