"""Import known WeChat article URLs without using history-list credentials."""

from __future__ import annotations

import argparse
import html
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .downloader import DownloadedArticle, WeChatArticleDownloader
from .sync import (
    INDEX_ROOT,
    PROJECT_ROOT,
    SHANGHAI,
    AccountConfig,
    _load_accounts,
    _load_json,
    _save_index,
    _url_key,
)


WECHAT_URL_RE = re.compile(
    r"https?://mp\.weixin\.qq\.com/s"
    r"(?:/[A-Za-z0-9_-]+(?:\?[^\s)>\]\"']+)?|\?[^\s)>\]\"']+)"
)


def _extract_urls(values: Iterable[str]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for value in values:
        for match in WECHAT_URL_RE.finditer(value):
            url = html.unescape(match.group(0)).rstrip(".,;，。；")
            key = _url_key(url)
            if key not in seen:
                seen.add(key)
                urls.append(url)
    return urls


def _load_input_values(direct_urls: list[str], input_path: Path | None) -> list[str]:
    values = list(direct_urls)
    if input_path is not None:
        values.append(input_path.read_text(encoding="utf-8"))
    return values


def _index_entry(downloaded: DownloadedArticle) -> dict[str, Any]:
    return {
        "articleId": downloaded.article_id,
        "title": downloaded.title,
        "publishedAt": downloaded.published_at.isoformat(),
        "sourceUrl": downloaded.source_url,
        "markdownPath": downloaded.markdown_path.relative_to(PROJECT_ROOT).as_posix(),
        "cover": downloaded.cover_path,
        "assetCount": downloaded.asset_count,
    }


def _save_imported_article(
    index_path: Path,
    index: dict[str, Any],
    downloaded: DownloadedArticle,
) -> None:
    entries = index.setdefault("articles", [])
    if not isinstance(entries, list):
        raise ValueError(f"{index_path.name} 的 articles 字段不是数组")
    entries.append(_index_entry(downloaded))
    entries.sort(key=lambda entry: str(entry.get("publishedAt", "")), reverse=True)

    raw_pending = index.get("pendingArticles", [])
    if isinstance(raw_pending, list):
        downloaded_url = _url_key(downloaded.source_url)
        index["pendingArticles"] = [
            item
            for item in raw_pending
            if not isinstance(item, dict)
            or (
                str(item.get("articleId", "")).strip() != downloaded.article_id
                and _url_key(str(item.get("url", ""))) != downloaded_url
            )
        ]
    index["updatedAt"] = datetime.now(tz=SHANGHAI).isoformat()
    _save_index(index_path, index)


def import_urls(
    account: AccountConfig,
    urls: list[str],
    *,
    delay_seconds: float,
) -> tuple[int, int, int]:
    index_path = INDEX_ROOT / f"{account.slug}.json"
    index = _load_json(index_path)
    entries = index.get("articles", [])
    if not isinstance(entries, list):
        raise ValueError(f"{index_path.name} 的 articles 字段不是数组")

    account_payload = index.get("account", {})
    if not isinstance(account_payload, dict) or str(
        account_payload.get("slug", "")
    ).strip() != account.slug:
        raise ValueError(f"{index_path.name} 与公众号 {account.slug} 不匹配")

    indexed_ids = {
        str(entry.get("articleId", "")).strip()
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("articleId", "")).strip()
    }
    indexed_urls = {
        _url_key(str(entry.get("sourceUrl", "")))
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("sourceUrl", "")).strip()
    }
    downloader = WeChatArticleDownloader()
    succeeded = 0
    skipped = 0
    failed = 0

    for position, url in enumerate(urls, start=1):
        if _url_key(url) in indexed_urls:
            skipped += 1
            print(f"[{position}/{len(urls)}] 已入库，跳过 {url}")
            continue

        print(f"[{position}/{len(urls)}] 导入 {url}")
        try:
            downloaded = downloader.download_url(url, account.name)
            if downloaded.article_id in indexed_ids:
                skipped += 1
                print(f"  文章 ID 已入库，跳过 {downloaded.article_id}")
                continue
            _save_imported_article(index_path, index, downloaded)
        except Exception as error:
            failed += 1
            print(f"  失败: {error}", file=sys.stderr)
        else:
            succeeded += 1
            indexed_ids.add(downloaded.article_id)
            indexed_urls.add(_url_key(downloaded.source_url))
            print(
                f"  已保存 {downloaded.markdown_path.relative_to(PROJECT_ROOT)}，"
                f"本地资源 {downloaded.asset_count} 个"
            )
        if position < len(urls) and delay_seconds:
            time.sleep(delay_seconds)

    return succeeded, skipped, failed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从已知微信原文链接回填历史文章")
    parser.add_argument("--account", required=True, help="目标公众号 slug")
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="微信原文链接；可重复使用",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="包含微信原文链接的 UTF-8 文本或 Markdown 文件",
    )
    parser.add_argument("--delay", type=float, default=2.0, help="文章间隔秒数")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.delay < 0:
        print("--delay 不能小于 0", file=sys.stderr)
        return 2
    try:
        values = _load_input_values(args.url, args.input)
        urls = _extract_urls(values)
        if not urls:
            raise ValueError("没有找到有效的 mp.weixin.qq.com/s/ 文章链接")
        account = _load_accounts({args.account})[0]
        succeeded, skipped, failed = import_urls(
            account,
            urls,
            delay_seconds=args.delay,
        )
    except (OSError, ValueError) as error:
        print(f"导入失败: {error}", file=sys.stderr)
        return 1

    print(f"导入完成：新增 {succeeded} 篇，跳过 {skipped} 篇，失败 {failed} 篇")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
