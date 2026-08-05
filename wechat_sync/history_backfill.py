"""Discover and locally import legacy WeChat articles through a cursor API."""

from __future__ import annotations

import argparse
import getpass
import html
import json
import os
import re
import stat
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import requests

from .import_urls import import_urls
from .sync import (
    INDEX_ROOT,
    PROJECT_ROOT,
    SHANGHAI,
    AccountConfig,
    _load_accounts,
    _load_json,
    _url_key,
)


DEFAULT_API_BASE_URL = "https://api.justoneapi.com"
API_PATH = "/api/weixin/get-account-history-articles/v2"
STATE_ROOT = PROJECT_ROOT / "data" / "wechat" / "history-backfill"
DEFAULT_TOKEN_PATH = PROJECT_ROOT / "data" / "wechat" / "justone-token"
URL_FIELDS = {"url", "link", "contenturl", "articleurl", "workurl"}
TITLE_FIELDS = {"title", "name", "appmsgtitle"}
PUBLISHED_FIELDS = {
    "publishtime",
    "publishedat",
    "publictime",
    "updatetime",
    "createtime",
}


class DiscoveryError(RuntimeError):
    """The external history index could not return a usable response."""


@dataclass(frozen=True)
class DiscoveredArticle:
    url: str
    title: str
    published_date: Optional[date]


@dataclass(frozen=True)
class IndexedIdentity:
    urls: set[str]
    title_dates: set[tuple[str, date]]


def _normalized_field(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _first_field(item: dict[str, Any], names: set[str]) -> Any:
    for key, value in item.items():
        if _normalized_field(str(key)) in names and value not in (None, ""):
            return value
    return None


def _published_date(value: Any) -> Optional[date]:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) or str(value).strip().isdigit():
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(timestamp, tz=SHANGHAI).date()
        except (OSError, OverflowError, ValueError):
            return None

    normalized = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(normalized[:10], pattern).date()
        except ValueError:
            continue
    return None


def _normalize_wechat_url(value: Any) -> str:
    url = html.unescape(str(value or "").strip())
    if url.startswith("http://mp.weixin.qq.com/"):
        url = "https://" + url.removeprefix("http://")
    if not url.startswith("https://mp.weixin.qq.com/s"):
        return ""
    return url


def _extract_articles(data: Any) -> list[DiscoveredArticle]:
    discovered: list[DiscoveredArticle] = []
    seen: set[str] = set()
    for item in _walk_dicts(data):
        url = _normalize_wechat_url(_first_field(item, URL_FIELDS))
        if not url:
            continue
        key = _url_key(url)
        if key in seen:
            continue
        seen.add(key)
        title = str(_first_field(item, TITLE_FIELDS) or "").strip()
        published = _published_date(_first_field(item, PUBLISHED_FIELDS))
        discovered.append(
            DiscoveredArticle(url=url, title=title, published_date=published)
        )
    return discovered


def _offset_from_dict(item: dict[str, Any]) -> str:
    for key, value in item.items():
        if _normalized_field(str(key)) == "offset" and not isinstance(
            value, (dict, list)
        ):
            return str(value or "").strip()
    return ""


def _extract_next_offset(data: Any) -> str:
    for item in _walk_dicts(data):
        for key, value in item.items():
            if _normalized_field(str(key)) in {"paginginfo", "paging"} and isinstance(
                value, dict
            ):
                offset = _offset_from_dict(value)
                if offset:
                    return offset
    for item in _walk_dicts(data):
        offset = _offset_from_dict(item)
        if offset:
            return offset
    return ""


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _save_api_token(path: Path) -> None:
    token = getpass.getpass("Just One API token（输入不回显）: ").strip()
    if not token:
        raise ValueError("token 不能为空")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(token, encoding="utf-8")
    temporary_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    temporary_path.replace(path)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _load_api_token(path: Path) -> str:
    env_token = os.environ.get("JUSTONE_API_TOKEN", "").strip()
    if env_token:
        return env_token
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _new_state(account: AccountConfig) -> dict[str, Any]:
    return {
        "version": 2,
        "account": account.slug,
        "ghId": account.gh_id,
        "offset": "",
        "seenOffsets": [],
        "pendingUrls": [],
        "pagesCompleted": 0,
        "complete": False,
    }


def _load_state(path: Path, account: AccountConfig) -> dict[str, Any]:
    if not path.exists():
        return _new_state(account)
    state = _load_json(path)
    if state.get("version") != 2:
        raise ValueError(
            f"历史回填断点版本不兼容: {path}；确认后使用 --reset-state"
        )
    if state.get("account") != account.slug or state.get("ghId") != account.gh_id:
        raise ValueError(
            f"历史回填断点与公众号配置不一致: {path}；"
            "确认后使用 --reset-state"
        )
    if not isinstance(state.get("seenOffsets", []), list) or not isinstance(
        state.get("pendingUrls", []), list
    ):
        raise ValueError(f"历史回填断点格式无效: {path}")
    return state


def _indexed_identity(account: AccountConfig) -> IndexedIdentity:
    index = _load_json(INDEX_ROOT / f"{account.slug}.json")
    articles = index.get("articles", [])
    if not isinstance(articles, list):
        raise ValueError(f"{account.slug} 索引中的 articles 字段不是数组")

    urls: set[str] = set()
    title_dates: set[tuple[str, date]] = set()
    for item in articles:
        if not isinstance(item, dict):
            continue
        source_url = str(item.get("sourceUrl", "")).strip()
        if source_url:
            urls.add(_url_key(source_url))
        title = str(item.get("title", "")).strip()
        published = _published_date(item.get("publishedAt"))
        if title and published is not None:
            title_dates.add((title, published))
    return IndexedIdentity(urls=urls, title_dates=title_dates)


def _is_indexed(article: DiscoveredArticle, indexed: IndexedIdentity) -> bool:
    if _url_key(article.url) in indexed.urls:
        return True
    return bool(
        article.title
        and article.published_date is not None
        and (article.title, article.published_date) in indexed.title_dates
    )


def _discover_page(
    session: requests.Session,
    api_url: str,
    api_token: str,
    account: AccountConfig,
    offset: str,
) -> tuple[list[DiscoveredArticle], str]:
    try:
        response = session.post(
            api_url,
            data={
                "token": api_token,
                "ghid": account.gh_id,
                "offset": offset,
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        raise DiscoveryError(f"历史列表查询失败: {error}") from error

    code = str(payload.get("code", "")) if isinstance(payload, dict) else ""
    if code != "0":
        messages = {
            "100": "JUSTONE_API_TOKEN 无效或已失效",
            "301": "采集失败，请稍后从断点重试",
            "302": "接口触发频率限制，请稍后从断点重试",
            "303": "接口今日配额已用完",
            "600": "当前 token 没有该接口权限",
            "601": "Just One API 账户余额不足",
            "602": "当前 token 的累计消费上限已达到",
        }
        message = messages.get(
            code,
            str(payload.get("message", "未知错误")) if isinstance(payload, dict) else "无效响应",
        )
        raise DiscoveryError(f"历史列表查询失败: {message} (code {code or 'unknown'})")

    data = payload.get("data", {})
    return _extract_articles(data), _extract_next_offset(data)


def _import_pending(
    account: AccountConfig,
    state_path: Path,
    state: dict[str, Any],
    *,
    delay_seconds: float,
) -> int:
    pending = [str(url) for url in state.get("pendingUrls", []) if str(url).strip()]
    if not pending:
        return 0
    print(f"先重试断点中保存的 {len(pending)} 个原文链接")
    imported = 0
    failed_urls: list[str] = []
    for position, url in enumerate(pending):
        succeeded, skipped, failed = import_urls(
            account,
            [url],
            delay_seconds=0,
        )
        imported += succeeded
        if failed or not (succeeded or skipped):
            failed_urls.append(url)

        # Persist after every URL so an interruption resumes from the exact item.
        state["pendingUrls"] = failed_urls + pending[position + 1 :]
        _save_state(state_path, state)
        if position + 1 < len(pending) and delay_seconds:
            time.sleep(delay_seconds)
    return imported


def backfill(
    account: AccountConfig,
    *,
    api_token: str,
    api_base_url: str,
    max_pages: int,
    delay_seconds: float,
    discover_only: bool,
    reset_state: bool,
) -> tuple[int, int]:
    if not account.gh_id:
        raise ValueError(f"公众号 {account.slug} 未配置 gh_id")
    state_path = STATE_ROOT / f"{account.slug}.json"
    if reset_state:
        state_path.unlink(missing_ok=True)
    state = _load_state(state_path, account)
    _save_state(state_path, state)

    imported = 0
    if not discover_only:
        imported += _import_pending(
            account,
            state_path,
            state,
            delay_seconds=delay_seconds,
        )
    if state.get("complete"):
        print("历史游标已经遍历完成")
        return imported, len(state.get("pendingUrls", []))

    session = requests.Session()
    session.headers.update({"User-Agent": "Gator-Investment-Research/1.0"})
    api_url = f"{api_base_url.rstrip('/')}{API_PATH}"
    indexed = _indexed_identity(account)
    pages_used = 0

    while pages_used < max_pages and not state.get("complete"):
        offset = str(state.get("offset", ""))
        print(f"[{pages_used + 1}/{max_pages}] 查询历史游标页")
        articles, next_offset = _discover_page(
            session,
            api_url,
            api_token,
            account,
            offset,
        )
        if not articles and not next_offset and not state.get("pagesCompleted"):
            raise DiscoveryError(
                "历史接口未返回可识别的文章或下一页游标，请保留断点并检查接口响应"
            )
        pages_used += 1
        new_articles = [article for article in articles if not _is_indexed(article, indexed)]
        pending = [str(url) for url in state.get("pendingUrls", [])]
        pending_keys = {_url_key(url) for url in pending}
        for article in new_articles:
            if _url_key(article.url) not in pending_keys:
                pending.append(article.url)
                pending_keys.add(_url_key(article.url))

        seen_offsets = [str(value) for value in state.get("seenOffsets", [])]
        if offset not in seen_offsets:
            seen_offsets.append(offset)
        state["seenOffsets"] = seen_offsets
        state["pendingUrls"] = pending
        state["pagesCompleted"] = int(state.get("pagesCompleted", 0)) + 1
        if not next_offset or next_offset in seen_offsets:
            state["complete"] = True
        else:
            state["offset"] = next_offset
        _save_state(state_path, state)

        print(
            f"  返回 {len(articles)} 篇，发现 {len(new_articles)} 篇未入库文章"
        )
        if new_articles and not discover_only:
            imported += _import_pending(
                account,
                state_path,
                state,
                delay_seconds=delay_seconds,
            )
            indexed = _indexed_identity(account)

        if pages_used < max_pages and not state.get("complete") and delay_seconds:
            time.sleep(delay_seconds)

    pending_count = len(state.get("pendingUrls", []))
    if state.get("complete"):
        print("历史游标已经遍历完成")
    else:
        print("本轮页数已用完，下次从保存的游标继续")
    return imported, pending_count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="通过游标分页发现并回填中转列表遗漏的微信公众号历史文章"
    )
    parser.add_argument("--account", help="目标公众号 slug")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help="本轮最多查询的历史游标页数，默认 20",
    )
    parser.add_argument("--delay", type=float, default=2.0, help="请求间隔秒数")
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="只发现链接并写入本地断点，不下载正文",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="清除当前账号的本地历史游标后重新开始",
    )
    parser.add_argument(
        "--save-token",
        action="store_true",
        help="隐藏输入并保存本地 API token 后退出",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.save_token:
        try:
            _save_api_token(DEFAULT_TOKEN_PATH)
        except (OSError, ValueError) as error:
            print(f"保存 token 失败: {error}", file=sys.stderr)
            return 1
        print(f"token 已保存到 Git 忽略文件: {DEFAULT_TOKEN_PATH}")
        return 0
    if not args.account:
        print("正常回填时必须提供 --account", file=sys.stderr)
        return 2
    if args.max_pages < 1 or args.max_pages > 100:
        print("--max-pages 必须在 1 到 100 之间", file=sys.stderr)
        return 2
    if args.delay < 0:
        print("--delay 不能小于 0", file=sys.stderr)
        return 2
    api_token = _load_api_token(DEFAULT_TOKEN_PATH)
    if not api_token:
        print(
            "未找到 Just One API token；请先运行 "
            "python -m wechat_sync.history_backfill --save-token",
            file=sys.stderr,
        )
        return 2
    api_base_url = os.environ.get(
        "JUSTONE_API_BASE_URL",
        DEFAULT_API_BASE_URL,
    ).strip()
    if not api_base_url.startswith("https://"):
        print("JUSTONE_API_BASE_URL 必须使用 HTTPS", file=sys.stderr)
        return 2
    try:
        account = _load_accounts({args.account})[0]
        imported, pending = backfill(
            account,
            api_token=api_token,
            api_base_url=api_base_url,
            max_pages=args.max_pages,
            delay_seconds=args.delay,
            discover_only=args.discover_only,
            reset_state=args.reset_state,
        )
    except (DiscoveryError, OSError, ValueError) as error:
        print(f"历史回填失败: {error}", file=sys.stderr)
        return 1

    print(f"历史回填完成：本轮新增 {imported} 篇，断点待导入 {pending} 篇")
    return 1 if pending and not args.discover_only else 0


if __name__ == "__main__":
    raise SystemExit(main())
