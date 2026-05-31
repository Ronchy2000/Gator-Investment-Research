from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
CATEGORY_RE = re.compile(r"^-\s*分类:\s*(.+)$", re.MULTILINE)
DATE_RE = re.compile(r"^-\s*日期:\s*(.+)$", re.MULTILINE)
ARTICLE_ID_RE = re.compile(r"^-\s*文章ID:\s*(\d+)$", re.MULTILINE)
SOURCE_RE = re.compile(r"^-\s*来源:\s*(.+)$", re.MULTILINE)
DATE_PREFIX_RE = re.compile(r"^(\d{4}\.\d{2}\.\d{2})-")


@dataclass(frozen=True)
class ArticleMetadata:
    title: str
    category: str
    date: Optional[str]
    article_id: Optional[int]
    source_url: Optional[str]


def _first_match(pattern: re.Pattern[str], text: str) -> Optional[str]:
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1).strip()


def parse_article_metadata(file_path: Path) -> ArticleMetadata:
    content = file_path.read_text(encoding="utf-8")

    title = _first_match(TITLE_RE, content) or file_path.stem
    category = _first_match(CATEGORY_RE, content) or "全部研报"
    date = _first_match(DATE_RE, content)
    article_id_text = _first_match(ARTICLE_ID_RE, content)
    source_url = _first_match(SOURCE_RE, content)

    if not date:
        date_match = DATE_PREFIX_RE.match(file_path.stem)
        if date_match:
            date = date_match.group(1)

    return ArticleMetadata(
        title=title,
        category=category,
        date=date or None,
        article_id=int(article_id_text) if article_id_text else None,
        source_url=source_url or None,
    )


def build_storage_filename(article_id: Optional[int], date: Optional[str]) -> str:
    if date and article_id is not None:
        return f"{date}-{article_id}.md"
    if article_id is not None:
        return f"article-{article_id}.md"
    if date:
        return f"{date}-article.md"
    return "article.md"


def sanitize_legacy_filename(name: str, max_len: int = 160) -> str:
    name = re.sub(r"[\\/*?:\"<>|]", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    if len(name) > max_len:
        name = name[:max_len].rstrip()
    return name or "article"


def build_legacy_filename(title: str, date: Optional[str]) -> str:
    prefix = f"{date}-" if date else ""
    return sanitize_legacy_filename(f"{prefix}{title}") + ".md"
