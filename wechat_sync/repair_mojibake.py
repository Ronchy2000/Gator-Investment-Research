"""Redownload canonical articles and remove duplicate mojibake archives."""

from __future__ import annotations

import argparse
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .client import RapidAPIClient, load_api_key_pool
from .downloader import (
    DEFAULT_ASSET_ROOT,
    DEFAULT_CONTENT_DIR,
    ArticleSummary,
    DownloadedArticle,
    WeChatArticleDownloader,
)
from .sync import (
    INDEX_ROOT,
    PROJECT_ROOT,
    SHANGHAI,
    _load_accounts,
    _load_json,
    _save_index,
    _timestamp,
)


MOJIBAKE_RE = re.compile(r"(?:’╝|ŃĆ|[ÕĶń][^\s<])")
MAX_DUPLICATE_TIME_DELTA_SECONDS = 60


def mojibake_score(value: str) -> int:
    return len(MOJIBAKE_RE.findall(value))


def looks_corrupt(entry: dict[str, Any], markdown: str) -> bool:
    title_score = mojibake_score(str(entry.get("title") or ""))
    return title_score >= 2 or mojibake_score(markdown) >= 8


def _entry_path(entry: dict[str, Any]) -> Path:
    return PROJECT_ROOT / str(entry.get("markdownPath") or "")


def _entry_summary(entry: dict[str, Any]) -> ArticleSummary:
    return ArticleSummary(
        article_id=str(entry["articleId"]),
        title=str(entry.get("title") or entry["articleId"]),
        url=str(entry["sourceUrl"]),
        cover_url="",
        published_at=_timestamp(entry["publishedAt"]),
    )


def _replacement_entry(downloaded: DownloadedArticle) -> dict[str, Any]:
    return {
        "articleId": downloaded.article_id,
        "title": downloaded.title,
        "publishedAt": downloaded.published_at.isoformat(),
        "sourceUrl": downloaded.source_url,
        "markdownPath": downloaded.markdown_path.relative_to(PROJECT_ROOT).as_posix(),
        "cover": downloaded.cover_path,
        "assetCount": downloaded.asset_count,
    }


def _find_replacement(
    corrupt: dict[str, Any],
    healthy: list[dict[str, Any]],
) -> dict[str, Any] | None:
    published_at = _timestamp(corrupt["publishedAt"])
    asset_count = int(corrupt.get("assetCount") or 0)
    candidates: list[tuple[float, int, dict[str, Any]]] = []
    for entry in healthy:
        candidate_time = _timestamp(entry["publishedAt"])
        if candidate_time.date() != published_at.date():
            continue
        if asset_count and int(entry.get("assetCount") or 0) != asset_count:
            continue
        delta = abs((candidate_time - published_at).total_seconds())
        if delta <= MAX_DUPLICATE_TIME_DELTA_SECONDS:
            article_id = str(entry.get("articleId", ""))
            canonical_rank = 0 if article_id.startswith("wx-") else 1
            candidates.append((delta, canonical_rank, entry))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    if len(candidates) > 1 and candidates[0][:2] == candidates[1][:2]:
        return None
    return candidates[0][2]


def _remove_entry_files(entry: dict[str, Any]) -> None:
    markdown_path = _entry_path(entry)
    if markdown_path.is_file() and markdown_path.is_relative_to(DEFAULT_CONTENT_DIR):
        markdown_path.unlink()

    cover = str(entry.get("cover") or "")
    if cover.startswith("/article-assets/"):
        asset_dir = PROJECT_ROOT / "public" / Path(cover.lstrip("/")).parent
        if asset_dir.is_dir() and asset_dir.is_relative_to(DEFAULT_ASSET_ROOT):
            shutil.rmtree(asset_dir)


def repair_account(slug: str, delay_seconds: float) -> tuple[int, int]:
    account = _load_accounts({slug})[0]
    index_path = INDEX_ROOT / f"{slug}.json"
    index = _load_json(index_path)
    entries = index.get("articles")
    if not isinstance(entries, list):
        raise ValueError(f"{index_path.name} 的 articles 必须是数组")

    corrupt: list[dict[str, Any]] = []
    healthy: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        markdown_path = _entry_path(entry)
        markdown = markdown_path.read_text(encoding="utf-8") if markdown_path.is_file() else ""
        (corrupt if looks_corrupt(entry, markdown) else healthy).append(entry)

    if not corrupt:
        print(f"[{account.name}] 未发现乱码文章")
        return 0, 0

    replacements: dict[str, dict[str, Any]] = {}
    for entry in corrupt:
        replacement = _find_replacement(entry, healthy)
        if replacement is None:
            raise ValueError(
                f"无法为乱码文章 {entry.get('articleId')} 唯一确定正常规范条目"
            )
        replacements[str(entry["articleId"])] = replacement

    client = RapidAPIClient(load_api_key_pool())
    downloader = WeChatArticleDownloader()
    refreshed: dict[str, dict[str, Any]] = {}
    replacement_ids = {str(entry["articleId"]) for entry in replacements.values()}
    for position, article_id in enumerate(sorted(replacement_ids), start=1):
        entry = next(item for item in healthy if str(item["articleId"]) == article_id)
        print(f"[{account.name} {position}/{len(replacement_ids)}] 重新下载 {entry['title']}")
        summary = _entry_summary(entry)
        detail = client.fetch_article_detail(summary.url)
        downloaded = downloader.download_detail(summary, account.name, detail)
        refreshed[article_id] = _replacement_entry(downloaded)

        if position < len(replacement_ids) and delay_seconds:
            time.sleep(delay_seconds)

    corrupt_ids = {str(entry["articleId"]) for entry in corrupt}
    next_entries: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        article_id = str(entry.get("articleId") or "")
        if article_id in corrupt_ids:
            continue
        next_entries.append(refreshed.get(article_id, entry))

    for entry in corrupt:
        _remove_entry_files(entry)

    next_entries.sort(key=lambda entry: str(entry.get("publishedAt", "")), reverse=True)
    index["articles"] = next_entries
    index["updatedAt"] = datetime.now(tz=SHANGHAI).isoformat()
    _save_index(index_path, index)
    print(
        f"[{account.name}] 重新下载 {len(refreshed)} 篇，"
        f"删除乱码重复条目 {len(corrupt)} 篇"
    )
    return len(refreshed), len(corrupt)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="重新下载并清理乱码公众号文章")
    parser.add_argument("--account", required=True, help="目标公众号 slug")
    parser.add_argument("--delay", type=float, default=2.0, help="文章间隔秒数")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.delay < 0:
        print("--delay 不能小于 0")
        return 2
    try:
        repair_account(args.account, args.delay)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"乱码修复失败: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
