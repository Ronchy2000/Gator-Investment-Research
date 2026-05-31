"""
Project-wide configuration and shared paths for the Gator Investment Research wiki.
All filesystem locations are derived from this file to keep the project self-contained
when the wiki directory is published as a standalone repository.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

# Docsify site directory (served via GitHub Pages)
DOCS_DIR = PROJECT_ROOT / "docs"

CATEGORY_DEFINITIONS = (
    {"label": "全部研报", "slug": "all-reports", "legacy_dir": "全部研报"},
    {"label": "宏观分析", "slug": "macro-analysis", "legacy_dir": "宏观分析"},
    {"label": "行业分析", "slug": "industry-analysis", "legacy_dir": "行业分析"},
)

# Directory for persisted article markdown files, grouped by category.
ARTICLE_CATEGORIES = {
    item["label"]: DOCS_DIR / item["slug"] for item in CATEGORY_DEFINITIONS
}
CATEGORY_SLUGS = {
    item["label"]: item["slug"] for item in CATEGORY_DEFINITIONS
}
LEGACY_CATEGORY_DIRS = {
    item["label"]: DOCS_DIR / item["legacy_dir"] for item in CATEGORY_DEFINITIONS
}

# Index file keeps track of fetched article IDs to avoid duplicates.
INDEX_FILE = DOCS_DIR / "index.json"

# Generated assets
SIDEBAR_FILE = DOCS_DIR / "_sidebar.md"
STATS_FILE = DOCS_DIR / "stats.json"

# Optional location for storing raw HTML snapshots (useful for debugging crawler output).
DATA_DIR = PROJECT_ROOT / "data"
RAW_HTML_DIR = DATA_DIR / "raw_html"


def ensure_structure() -> None:
    """
    Create required directories if they are missing. Safe to call repeatedly.
    """
    DOCS_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    RAW_HTML_DIR.mkdir(exist_ok=True)

    for path in ARTICLE_CATEGORIES.values():
        path.mkdir(parents=True, exist_ok=True)


def category_slug(label: str) -> str:
    return CATEGORY_SLUGS[label]


if __name__ == "__main__":
    ensure_structure()
