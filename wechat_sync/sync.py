"""Synchronize one configured WeChat account into local Markdown files."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .client import WeReadClient, WeReadRelayError, load_credentials
from .downloader import ArticleSummary, WeChatArticleDownloader


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ACCOUNT_PATH = Path(__file__).resolve().parent / "account.json"
INDEX_PATH = Path(__file__).resolve().parent / "index.json"
SHANGHAI = ZoneInfo("Asia/Shanghai")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"配置文件不是 JSON 对象: {path}")
    return payload


def _timestamp(value: Any) -> datetime:
    timestamp = float(value)
    if timestamp > 10_000_000_000:
        timestamp /= 1000
    return datetime.fromtimestamp(timestamp, tz=SHANGHAI)


def _first_string(item: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _normalize_article(item: dict[str, Any]) -> ArticleSummary:
    article_id = _first_string(item, ("id", "articleId", "article_id"))
    url = _first_string(item, ("url", "link", "articleUrl", "article_url"))
    title = _first_string(item, ("title", "name"))
    cover_url = _first_string(item, ("picUrl", "cover", "coverUrl", "pic_url"))
    published_value = next(
        (
            item[key]
            for key in ("publishTime", "publish_time", "publishedAt", "createTime")
            if item.get(key) is not None
        ),
        None,
    )
    if not article_id or not url or published_value is None:
        raise ValueError(f"文章列表项缺少必要字段: {item}")
    return ArticleSummary(
        article_id=article_id,
        title=title or article_id,
        url=url,
        cover_url=cover_url,
        published_at=_timestamp(published_value),
    )


def _save_index(index: dict[str, Any]) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = INDEX_PATH.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(INDEX_PATH)


def _fetch_page(
    client: WeReadClient,
    mp_id: str,
    page: int,
    retries: int = 3,
) -> list[dict[str, Any]]:
    for attempt in range(1, retries + 1):
        rows = client.fetch_articles(mp_id, page)
        if rows or page > 1 or attempt == retries:
            return rows
        print(f"第 1 页为空，{attempt}/{retries} 次尝试后等待重试")
        time.sleep(attempt * 2)
    return []


def _collect_articles(
    client: WeReadClient,
    mp_id: str,
    earliest: date,
    indexed_urls: set[str],
    max_pages: int,
    delay_seconds: float,
) -> list[ArticleSummary]:
    collected: dict[str, ArticleSummary] = {}
    prior_page_urls: set[str] = set()

    for page in range(1, max_pages + 1):
        rows = _fetch_page(client, mp_id, page)
        if not rows:
            if page == 1:
                raise WeReadRelayError("文章列表第一页为空，中转服务可能尚未刷新数据")
            break

        page_articles = [_normalize_article(row) for row in rows]
        page_urls = {article.url for article in page_articles}
        if page_urls and page_urls.issubset(prior_page_urls):
            break
        prior_page_urls.update(page_urls)

        for article in page_articles:
            if article.published_at.date() >= earliest:
                collected[article.url] = article

        has_older_article = any(
            article.published_at.date() < earliest for article in page_articles
        )
        has_indexed_article = any(article.url in indexed_urls for article in page_articles)
        if has_older_article or has_indexed_article:
            break

        if page < max_pages:
            time.sleep(delay_seconds)

    return sorted(collected.values(), key=lambda article: article.published_at)


def synchronize(max_pages: int, delay_seconds: float) -> tuple[int, int]:
    account = _load_json(ACCOUNT_PATH)
    mp_id = str(account.get("mp_id", "")).strip()
    source_name = str(account.get("name", "")).strip()
    earliest_value = str(account.get("earliest_date", "")).strip()
    if not mp_id or not source_name or not earliest_value:
        raise ValueError("account.json 缺少 mp_id、name 或 earliest_date")
    earliest = date.fromisoformat(earliest_value)

    index = _load_json(INDEX_PATH)
    existing_entries = index.get("articles", [])
    if not isinstance(existing_entries, list):
        raise ValueError("index.json 的 articles 字段不是数组")
    indexed_urls = {
        str(entry.get("sourceUrl", "")).strip()
        for entry in existing_entries
        if isinstance(entry, dict)
    }

    client = WeReadClient(load_credentials())
    articles = _collect_articles(
        client=client,
        mp_id=mp_id,
        earliest=earliest,
        indexed_urls=indexed_urls,
        max_pages=max_pages,
        delay_seconds=delay_seconds,
    )
    pending = [article for article in articles if article.url not in indexed_urls]
    print(f"发现 {len(articles)} 篇范围内文章，其中 {len(pending)} 篇待下载")

    downloader = WeChatArticleDownloader()
    succeeded = 0
    failures: list[tuple[ArticleSummary, str]] = []
    entries = list(existing_entries)

    for position, article in enumerate(pending, start=1):
        print(f"[{position}/{len(pending)}] 下载 {article.title}")
        try:
            downloaded = downloader.download(article, source_name)
        except Exception as error:
            failures.append((article, str(error)))
            print(f"  失败: {error}", file=sys.stderr)
        else:
            relative_path = downloaded.markdown_path.relative_to(PROJECT_ROOT).as_posix()
            entries.append(
                {
                    "articleId": downloaded.article_id,
                    "title": downloaded.title,
                    "publishedAt": downloaded.published_at.isoformat(),
                    "sourceUrl": downloaded.source_url,
                    "markdownPath": relative_path,
                    "cover": downloaded.cover_path,
                    "assetCount": downloaded.asset_count,
                }
            )
            entries.sort(key=lambda entry: str(entry.get("publishedAt", "")), reverse=True)
            index = {
                "version": 1,
                "account": {"mpId": mp_id, "name": source_name},
                "earliestDate": earliest.isoformat(),
                "updatedAt": datetime.now(tz=SHANGHAI).isoformat(),
                "articles": entries,
            }
            _save_index(index)
            succeeded += 1
            print(f"  已保存 {relative_path}，本地资源 {downloaded.asset_count} 个")

        if position < len(pending):
            time.sleep(delay_seconds)

    if failures:
        print("以下文章保留到下次同步重试：", file=sys.stderr)
        for article, message in failures:
            print(f"- {article.title}: {message}", file=sys.stderr)
    return succeeded, len(failures)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="同步获得信息差公众号文章")
    parser.add_argument("--max-pages", type=int, default=20, help="最多读取的列表页数")
    parser.add_argument("--delay", type=float, default=2.0, help="请求间隔秒数")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.max_pages < 1:
        print("--max-pages 必须大于 0", file=sys.stderr)
        return 2
    if args.delay < 0:
        print("--delay 不能小于 0", file=sys.stderr)
        return 2
    try:
        succeeded, failed = synchronize(args.max_pages, args.delay)
    except (OSError, ValueError, WeReadRelayError) as error:
        print(f"同步失败: {error}", file=sys.stderr)
        return 1
    print(f"同步完成：新增 {succeeded} 篇，失败 {failed} 篇")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
