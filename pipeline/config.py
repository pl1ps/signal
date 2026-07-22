"""All tunable values live here so nothing else hardcodes constants."""

# Pre-filter and assembly
CANDIDATE_CAP = 50          # how many items reach the AI stage
ITEMS_PER_SECTION = 6       # max cards shown per section
MIN_RELEVANCE = 0.35        # AI score below this is dropped
READOUT_BARS = 48           # bars in the noise-floor readout

# Source popularity thresholds (cheap noise removal before any AI cost)
HN_MIN_POINTS = 50
REDDIT_MIN_UPVOTES = 100
GITHUB_MIN_STARS = 50

SECTIONS = [
    ("ai-tools", "AI & Tools"),
    ("code-projects", "Code & Projects"),
    ("learn-career", "Learn & Career"),
    ("tech-discussion", "Tech Discussion"),
    ("world", "World"),
]

# Used when the AI stage is unavailable and cannot assign sections.
FALLBACK_SECTION = {
    "hackernews": "tech-discussion",
    "github": "code-projects",
    "reddit": "learn-career",
    "news": "world",
}

SUBREDDITS = ["learnprogramming", "cscareerquestions", "LocalLLaMA", "artificial"]

RSS_FEEDS = [
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("NPR News", "https://feeds.npr.org/1001/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
]

GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
