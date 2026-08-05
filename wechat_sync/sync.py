"""Synchronize configured WeChat accounts into the shared article archive."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from .client import RapidAPIClient, RapidAPIError, load_api_key_pool
from .downloader import ArticleSummary, WeChatArticleDownloader


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "accounts.json"
INDEX_ROOT = Path(__file__).resolve().parent / "indexes"
SHANGHAI = ZoneInfo("Asia/Shanghai")
MAX_LIST_PAGES_PER_ACCOUNT = 40
LIST_PAGE_SIZE = 10
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class AccountConfig:
    slug: str
    name: str
    seed_article_url: str
    earliest: date
    reported_count: Optional[int]


@dataclass(frozen=True)
class CollectionState:
    articles: list[ArticleSummary]
    backfill_complete: bool
    backfill_next_page: int


def _write_actions_outputs(succeeded: int, failed: int) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as output:
        output.write(f"articles_synced={succeeded}\n")
        output.write(f"articles_failed={failed}\n")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"配置文件不是 JSON 对象: {path}")
    return payload


def _load_accounts(selected_slugs: set[str]) -> list[AccountConfig]:
    payload = _load_json(CONFIG_PATH)
    raw_accounts = payload.get("accounts")
    if not isinstance(raw_accounts, list) or not raw_accounts:
        raise ValueError("accounts.json 的 accounts 必须是非空数组")

    accounts: list[AccountConfig] = []
    seen_slugs: set[str] = set()
    for item in raw_accounts:
        if not isinstance(item, dict):
            raise ValueError("accounts.json 包含无效账号配置")
        slug = str(item.get("slug", "")).strip()
        name = str(item.get("name", "")).strip()
        seed_article_url = str(item.get("seed_article_url", "")).strip()
        earliest_value = str(item.get("earliest_date", "")).strip()
        raw_reported_count = item.get("reported_article_count")
        if (
            not SLUG_RE.fullmatch(slug)
            or not name
            or not seed_article_url.startswith("https://mp.weixin.qq.com/")
            or not earliest_value
        ):
            raise ValueError(
                "公众号配置缺少有效 slug、name、seed_article_url 或 "
                f"earliest_date: {item}"
            )
        if slug in seen_slugs:
            raise ValueError(f"公众号 slug 重复: {slug}")
        seen_slugs.add(slug)
        reported_count = None
        if raw_reported_count is not None:
            reported_count = int(raw_reported_count)
            if reported_count < 1:
                raise ValueError(f"公众号 reported_article_count 必须大于 0: {slug}")
        if not selected_slugs or slug in selected_slugs:
            accounts.append(
                AccountConfig(
                    slug=slug,
                    name=name,
                    seed_article_url=seed_article_url,
                    earliest=date.fromisoformat(earliest_value),
                    reported_count=reported_count,
                )
            )

    unknown = selected_slugs - seen_slugs
    if unknown:
        raise ValueError(f"未找到公众号配置: {', '.join(sorted(unknown))}")
    return accounts


def _timestamp(value: Any) -> datetime:
    if isinstance(value, str):
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            pass
        else:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=SHANGHAI)
            return parsed.astimezone(SHANGHAI)
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


def _url_key(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.netloc.lower() == "mp.weixin.qq.com" and parsed.path.startswith("/s/"):
        return urlunsplit(("https", "mp.weixin.qq.com", parsed.path.rstrip("/"), "", ""))
    if parsed.netloc.lower() == "mp.weixin.qq.com" and parsed.path.rstrip("/") == "/s":
        allowed = {"__biz", "mid", "idx", "sn"}
        query = [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=False)
            if key in allowed
        ]
        return urlunsplit(
            ("https", "mp.weixin.qq.com", "/s", urlencode(sorted(query)), "")
        )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _is_indexed(
    article: ArticleSummary,
    indexed_ids: set[str],
    indexed_urls: set[str],
    indexed_title_dates: set[tuple[str, date]],
) -> bool:
    return (
        article.article_id in indexed_ids
        or _url_key(article.url) in indexed_urls
        or (article.title, article.published_at.date()) in indexed_title_dates
    )


def _pending_record(article: ArticleSummary) -> dict[str, str]:
    return {
        "articleId": article.article_id,
        "title": article.title,
        "url": article.url,
        "coverUrl": article.cover_url,
        "publishedAt": article.published_at.isoformat(),
    }


def _save_index(path: Path, index: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _fetch_page(
    client: RapidAPIClient,
    identifier: str,
    page: int,
    retries: int = 3,
) -> list[dict[str, Any]]:
    for attempt in range(1, retries + 1):
        rows = client.fetch_articles(identifier, page)
        if rows or page > 1 or attempt == retries:
            return rows
        print(f"第 1 页为空，{attempt}/{retries} 次尝试后等待重试")
        time.sleep(attempt * 2)
    return []


def _collect_articles(
    client: RapidAPIClient,
    account: AccountConfig,
    indexed_ids: set[str],
    indexed_urls: set[str],
    indexed_title_dates: set[tuple[str, date]],
    backfill_complete: bool,
    backfill_next_page: int,
    known_history_remaining: bool,
    history_page_limit: Optional[int],
    max_pages: int,
    delay_seconds: float,
) -> CollectionState:
    collected: dict[str, ArticleSummary] = {}
    pages_used = 0
    inspected_pages: set[int] = set()
    reached_history_boundary = False

    # Once historical backfill has started, always inspect the newest pages first.
    if indexed_ids:
        reached_incremental_boundary = False
        prior_urls: set[str] = set()
        for page in range(1, max_pages + 1):
            rows = _fetch_page(client, account.seed_article_url, page)
            pages_used += 1
            inspected_pages.add(page)
            if not rows:
                if page == 1:
                    print(
                        f"[{account.name}] 文章列表第一页暂时为空，"
                        "跳过本轮增量边界检查并继续历史回补"
                    )
                reached_incremental_boundary = True
                break

            page_articles = [_normalize_article(row) for row in rows]
            page_urls = {_url_key(article.url) for article in page_articles}
            if page_urls and page_urls.issubset(prior_urls):
                reached_incremental_boundary = True
                break
            prior_urls.update(page_urls)

            for article in page_articles:
                if (
                    article.published_at.date() >= account.earliest
                    and not _is_indexed(
                        article, indexed_ids, indexed_urls, indexed_title_dates
                    )
                ):
                    collected[_url_key(article.url)] = article

            if any(article.published_at.date() < account.earliest for article in page_articles):
                reached_incremental_boundary = True
                break
            if any(
                _is_indexed(
                    article, indexed_ids, indexed_urls, indexed_title_dates
                )
                for article in page_articles
            ):
                reached_incremental_boundary = True
                break
            if pages_used < max_pages:
                time.sleep(delay_seconds)

        if not reached_incremental_boundary and pages_used >= max_pages:
            raise RapidAPIError(
                f"{account.name} 连续 {max_pages} 页仍未遇到已入库文章，"
                "为避免增量漏文已停止，请提高 --max-pages 后重试"
            )

    if not backfill_complete and pages_used < max_pages:
        start_page = 1 if not indexed_ids else max(1, backfill_next_page - 1)
        prior_urls: set[str] = set()
        last_page = start_page - 1
        candidate_page = start_page
        while pages_used < max_pages:
            page = candidate_page
            candidate_page += 1
            if known_history_remaining and history_page_limit is not None:
                page = ((page - 1) % history_page_limit) + 1
                if len(inspected_pages) >= history_page_limit:
                    break
            if page in inspected_pages:
                continue
            rows = _fetch_page(client, account.seed_article_url, page)
            pages_used += 1
            inspected_pages.add(page)
            last_page = page
            if not rows:
                if page == 1:
                    if not indexed_ids:
                        raise RapidAPIError(
                            f"{account.name} 文章列表第一页为空，RapidAPI 数据可能尚未刷新"
                        )
                if known_history_remaining:
                    if pages_used < max_pages:
                        time.sleep(delay_seconds)
                    continue
                backfill_complete = True
                break

            page_articles = [_normalize_article(row) for row in rows]
            page_urls = {_url_key(article.url) for article in page_articles}
            if page_urls and page_urls.issubset(prior_urls):
                if known_history_remaining:
                    if pages_used < max_pages:
                        time.sleep(delay_seconds)
                    continue
                backfill_complete = True
                break
            prior_urls.update(page_urls)

            for article in page_articles:
                if (
                    article.published_at.date() >= account.earliest
                    and not _is_indexed(
                        article, indexed_ids, indexed_urls, indexed_title_dates
                    )
                ):
                    collected[_url_key(article.url)] = article

            if any(article.published_at.date() < account.earliest for article in page_articles):
                backfill_complete = True
                reached_history_boundary = True
                break
            if pages_used < max_pages:
                time.sleep(delay_seconds)

        if known_history_remaining and not reached_history_boundary:
            backfill_complete = False
            if history_page_limit is not None:
                backfill_next_page = ((candidate_page - 1) % history_page_limit) + 1
            else:
                backfill_next_page = last_page + 1
        else:
            backfill_next_page = max(backfill_next_page, last_page + 1)

    return CollectionState(
        articles=sorted(collected.values(), key=lambda article: article.published_at),
        backfill_complete=backfill_complete,
        backfill_next_page=backfill_next_page,
    )


def _synchronize_account(
    account: AccountConfig,
    client: RapidAPIClient,
    downloader: WeChatArticleDownloader,
    max_pages: int,
    delay_seconds: float,
) -> tuple[int, int]:
    index_path = INDEX_ROOT / f"{account.slug}.json"
    index = _load_json(index_path)
    existing_entries = index.get("articles", [])
    if not isinstance(existing_entries, list):
        raise ValueError(f"{index_path.name} 的 articles 字段不是数组")

    indexed_ids = {
        str(entry.get("articleId", "")).strip()
        for entry in existing_entries
        if isinstance(entry, dict) and str(entry.get("articleId", "")).strip()
    }
    indexed_urls = {
        _url_key(str(entry.get("sourceUrl", "")))
        for entry in existing_entries
        if isinstance(entry, dict) and str(entry.get("sourceUrl", "")).strip()
    }
    indexed_title_dates = {
        (
            str(entry.get("title", "")).strip(),
            _timestamp(entry.get("publishedAt")).date(),
        )
        for entry in existing_entries
        if isinstance(entry, dict)
        and str(entry.get("title", "")).strip()
        and entry.get("publishedAt") is not None
    }

    raw_pending = index.get("pendingArticles", [])
    if not isinstance(raw_pending, list):
        raise ValueError(f"{index_path.name} 的 pendingArticles 字段不是数组")
    pending_by_id: dict[str, ArticleSummary] = {}
    for item in raw_pending:
        if not isinstance(item, dict):
            continue
        article = _normalize_article(item)
        if not _is_indexed(
            article, indexed_ids, indexed_urls, indexed_title_dates
        ):
            pending_by_id[article.article_id] = article

    migrated_complete_default = bool(existing_entries) and "backfillComplete" not in index
    backfill_complete = bool(
        index.get("backfillComplete", migrated_complete_default)
    )
    known_history_remaining = (
        account.reported_count is not None
        and len(existing_entries) < account.reported_count
    )
    backfill_next_page = max(1, int(index.get("backfillNextPage", 1)))
    if known_history_remaining and backfill_complete:
        backfill_complete = False
        print(
            f"[{account.name}] 已归档 {len(existing_entries)}/"
            f"{account.reported_count} 篇，继续探测可能延迟开放的历史分页"
        )
    collection = _collect_articles(
        client=client,
        account=account,
        indexed_ids=indexed_ids,
        indexed_urls=indexed_urls,
        indexed_title_dates=indexed_title_dates,
        backfill_complete=backfill_complete,
        backfill_next_page=backfill_next_page,
        known_history_remaining=known_history_remaining,
        history_page_limit=(
            (account.reported_count + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE
            if known_history_remaining and account.reported_count is not None
            else None
        ),
        max_pages=max_pages,
        delay_seconds=delay_seconds,
    )
    for article in collection.articles:
        if not _is_indexed(
            article, indexed_ids, indexed_urls, indexed_title_dates
        ):
            pending_by_id[article.article_id] = article

    entries = list(existing_entries)

    def save_state() -> None:
        next_index = {
            "version": 4,
            "account": {
                "slug": account.slug,
                "name": account.name,
                "seedArticleUrl": account.seed_article_url,
            },
            "earliestDate": account.earliest.isoformat(),
            "backfillComplete": collection.backfill_complete,
            "backfillNextPage": collection.backfill_next_page,
            "pendingArticles": [
                _pending_record(article)
                for article in sorted(
                    pending_by_id.values(),
                    key=lambda item: item.published_at,
                    reverse=True,
                )
            ],
            "articles": entries,
        }
        current_without_timestamp = {
            key: value for key, value in index.items() if key != "updatedAt"
        }
        if current_without_timestamp == next_index:
            return
        next_index["updatedAt"] = datetime.now(tz=SHANGHAI).isoformat()
        _save_index(index_path, next_index)
        index.clear()
        index.update(next_index)

    save_state()
    pending = sorted(pending_by_id.values(), key=lambda article: article.published_at)
    backfill_label = "历史回补完成" if collection.backfill_complete else (
        f"历史回补待续（下次从第 {collection.backfill_next_page} 页附近继续）"
    )
    print(
        f"[{account.name}] 发现 {len(collection.articles)} 篇未入库文章，"
        f"本次需处理 {len(pending)} 篇（含失败重试）；{backfill_label}"
    )

    succeeded = 0
    failures: list[tuple[ArticleSummary, str]] = []
    for position, article in enumerate(pending, start=1):
        print(f"[{account.name} {position}/{len(pending)}] 下载 {article.title}")
        try:
            detail = client.fetch_article_detail(article.url)
            downloaded = downloader.download_detail(article, account.name, detail)
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
            indexed_ids.add(downloaded.article_id)
            indexed_urls.add(_url_key(downloaded.source_url))
            indexed_title_dates.add(
                (downloaded.title, downloaded.published_at.date())
            )
            pending_by_id.pop(article.article_id, None)
            succeeded += 1
            print(f"  已保存 {relative_path}，本地资源 {downloaded.asset_count} 个")
        save_state()
        if position < len(pending):
            time.sleep(delay_seconds)

    if failures:
        print(f"[{account.name}] 以下文章保留到下次同步重试：", file=sys.stderr)
        for article, message in failures:
            print(f"- {article.title}: {message}", file=sys.stderr)
    return succeeded, len(failures)


def synchronize(
    max_pages: int,
    delay_seconds: float,
    selected_slugs: set[str],
) -> tuple[int, int, list[str]]:
    accounts = _load_accounts(selected_slugs)
    key_pool = load_api_key_pool()
    client = RapidAPIClient(key_pool)
    print(f"已加载 {client.key_count} 个 RapidAPI Key，按日期轮换并自动故障转移")
    downloader = WeChatArticleDownloader()
    succeeded = 0
    failed = 0
    account_errors: list[str] = []

    for position, account in enumerate(accounts, start=1):
        print(f"=== 同步公众号：{account.name} ({account.slug}) ===")
        try:
            account_succeeded, account_failed = _synchronize_account(
                account=account,
                client=client,
                downloader=downloader,
                max_pages=max_pages,
                delay_seconds=delay_seconds,
            )
        except (OSError, ValueError, RapidAPIError) as error:
            account_errors.append(f"{account.name}: {error}")
            print(f"[{account.name}] 同步失败: {error}", file=sys.stderr)
        else:
            succeeded += account_succeeded
            failed += account_failed
        if position < len(accounts):
            time.sleep(delay_seconds)

    return succeeded, failed, account_errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="同步已配置的微信公众号文章")
    parser.add_argument(
        "--account",
        action="append",
        default=[],
        help="只同步指定账号 slug；可重复使用，默认同步全部账号",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1,
        help="每个公众号最多读取的列表页数（默认 1）",
    )
    parser.add_argument("--delay", type=float, default=2.0, help="请求间隔秒数")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.max_pages < 1:
        print("--max-pages 必须大于 0", file=sys.stderr)
        return 2
    if args.max_pages > MAX_LIST_PAGES_PER_ACCOUNT:
        print(
            f"--max-pages 不能超过 {MAX_LIST_PAGES_PER_ACCOUNT}，"
            "避免单次任务过度消耗 RapidAPI 月度额度",
            file=sys.stderr,
        )
        return 2
    if args.delay < 0:
        print("--delay 不能小于 0", file=sys.stderr)
        return 2
    try:
        succeeded, failed, account_errors = synchronize(
            max_pages=args.max_pages,
            delay_seconds=args.delay,
            selected_slugs=set(args.account),
        )
    except (OSError, ValueError, RapidAPIError) as error:
        print(f"同步失败: {error}", file=sys.stderr)
        _write_actions_outputs(0, 1)
        return 1

    _write_actions_outputs(succeeded, failed + len(account_errors))
    for message in account_errors:
        print(f"- {message}", file=sys.stderr)
    print(
        f"同步完成：新增 {succeeded} 篇，文章失败 {failed} 篇，"
        f"账号失败 {len(account_errors)} 个"
    )
    return 1 if failed or account_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
