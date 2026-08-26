"""RapidAPI client with product-aware and API-key-aware failover."""

from __future__ import annotations

import hashlib
import html as html_module
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence, TypeVar
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KEY_FILE = PROJECT_ROOT / "data" / "wechat" / "rapidapi-keys.json"
DEFAULT_API_HOST = "weixin-wechat-official-accounts-platform.p.rapidapi.com"
DEFAULT_API_URL = f"https://{DEFAULT_API_HOST}"
HISTORY_PATH = "/api/weixin/get-account-history-articles/v2"
DETAIL_PATH = "/api/weixin/get-article-detail/v4"
WECHAT_DATA_HOST = "wechat-data.p.rapidapi.com"
WECHAT_DATA_INFO_PATH = "/weixin/getinfo"
WECHAT_DATA_HISTORY_PATH = "/weixin/getps"
WECHAT_DATA_DETAIL_PATH = "/weixin/artinfo"
SIAN_HOST = (
    "wechat-Wei-Xin-Gong-Zhong-Hao-official-accounts-data-api.p.rapidapi.com"
)
SIAN_ACCOUNT_SEARCH_PATH = "/wechat-accounts/keyword-search"
SIAN_HISTORY_PATH = "/wechat-accounts/user-posts"
SIAN_DETAIL_PATH = "/wechat-accounts/article-detail"
SWITCHABLE_CODES = {100, 302, 303, 500, 600, 601, 602}
CURSOR_PREFIX = "rapidapi:"
ResponseValue = TypeVar("ResponseValue")


class RapidAPIError(RuntimeError):
    """No configured RapidAPI product could return usable data."""


class RapidAPIKeyError(RapidAPIError):
    """One API key cannot use one specific RapidAPI product."""


class RapidAPINetworkError(RapidAPIError):
    """A RapidAPI product failed before returning usable data."""


class RapidAPIProviderUnavailable(RapidAPIError):
    """A product lacks a usable key or required account identifier."""


@dataclass(frozen=True)
class APIKeyPool:
    keys: tuple[str, ...]

    @property
    def size(self) -> int:
        return len(self.keys)


@dataclass(frozen=True)
class AccountReference:
    name: str
    article_url: str
    biz: str = ""
    wechat_data_wxid: str = ""
    wechat_id: str = ""


@dataclass(frozen=True)
class HistoryPage:
    rows: list[dict[str, Any]]
    next_offset: str
    is_end: bool


@dataclass(frozen=True)
class _Provider:
    name: str
    label: str
    host: str
    base_url: str


PROVIDERS = (
    _Provider("justone", "Official Accounts Platform", DEFAULT_API_HOST, DEFAULT_API_URL),
    _Provider(
        "wechat-data",
        "WeChat Data",
        WECHAT_DATA_HOST,
        f"https://{WECHAT_DATA_HOST}",
    ),
    _Provider("sian", "SIAN WeChat Data", SIAN_HOST, f"https://{SIAN_HOST}"),
)
PROVIDER_BY_NAME = {provider.name: provider for provider in PROVIDERS}
KEY_ERROR_TERMS = (
    "not subscribed",
    "not subscribe",
    "subscription",
    "invalid api key",
    "invalid key",
    "unauthorized",
    "forbidden",
    "quota",
    "rate limit",
    "too many requests",
    "exceeded",
    "订阅",
    "套餐",
    "额度",
    "限流",
    "鉴权",
    "无权限",
)
URL_FIELDS = (
    "url",
    "link",
    "art_url",
    "article_url",
    "article_link",
    "content_url",
)
TITLE_FIELDS = ("title", "name", "article_title")
COVER_FIELDS = (
    "cover",
    "cover_url",
    "cover_img_url",
    "pic",
    "pic_url",
    "image",
    "image_url",
)
PUBLISHED_FIELDS = (
    "publish_time",
    "publish_timestamp",
    "pub_time",
    "post_time",
    "post_date",
    "published_at",
    "published",
    "create_time",
    "create_timestamp",
    "update_time",
    "datetime",
    "timestamp",
    "date",
    "time",
)
ARTICLE_ID_FIELDS = ("appmsgid", "article_id", "msg_id", "id")
POSITION_FIELDS = ("position", "item_index", "idx")
HTML_FIELDS = (
    "html",
    "content_html",
    "article_html",
    "content",
    "article_content",
)
SOURCE_NAME_FIELDS = (
    "nickname",
    "source_name",
    "account_name",
    "wx_name",
)
DESCRIPTION_FIELDS = ("description", "desc", "digest", "summary")
ACCOUNT_ID_FIELDS = (
    "wxid",
    "wechat_id",
    "original_id",
    "originalid",
    "gh_id",
    "ghid",
    "username",
    "user_name",
    "alias",
    "account_id",
)


def _deduplicate_keys(values: Sequence[Any]) -> tuple[str, ...]:
    keys: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = str(value).strip()
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    if not keys:
        raise RapidAPIKeyError("RapidAPI Key 池为空")
    return tuple(keys)


def _parse_key_pool(value: str) -> APIKeyPool:
    raw = value.strip()
    if not raw:
        raise RapidAPIKeyError("RapidAPI Key 池为空")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = [item for line in raw.splitlines() for item in line.split(",")]

    if isinstance(payload, dict):
        payload = payload.get("keys")
    if isinstance(payload, str):
        payload = [payload]
    if not isinstance(payload, list):
        raise RapidAPIKeyError("RAPIDAPI_KEYS 必须是 JSON 数组或包含 keys 的对象")
    return APIKeyPool(keys=_deduplicate_keys(payload))


def load_api_key_pool(path: Path = DEFAULT_KEY_FILE) -> APIKeyPool:
    """Load keys from Actions secrets or an ignored local file."""
    env_pool = os.environ.get("RAPIDAPI_KEYS", "").strip()
    if env_pool:
        return _parse_key_pool(env_pool)

    env_key = os.environ.get("RAPIDAPI_KEY", "").strip()
    if env_key:
        return APIKeyPool(keys=(env_key,))

    if not path.exists():
        raise RapidAPIKeyError(
            "未找到 RapidAPI Key；请配置 RAPIDAPI_KEYS，或运行 "
            "python -m wechat_sync.rapidapi_secrets --add"
        )
    try:
        return _parse_key_pool(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise RapidAPIKeyError(f"无法读取本地 RapidAPI Key 池: {error}") from error


def _field_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _direct_value(item: dict[str, Any], names: Iterable[str]) -> Any:
    normalized = {_field_name(key): value for key, value in item.items()}
    for name in names:
        key = _field_name(name)
        if key in normalized and normalized[key] is not None:
            return normalized[key]
    return None


def _recursive_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _recursive_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _recursive_dicts(child)


def _deep_value(value: Any, names: Iterable[str]) -> Any:
    for item in _recursive_dicts(value):
        candidate = _direct_value(item, names)
        if candidate is not None:
            return candidate
    return None


def _text(value: Any) -> str:
    if isinstance(value, (dict, list)) or value is None:
        return ""
    return str(value).strip()


def _business_code(payload: Any) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    try:
        return int(payload.get("code"))
    except (TypeError, ValueError):
        return None


def _error_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "未知错误"
    error = payload.get("error")
    values = [payload.get("message"), payload.get("msg"), payload.get("detail")]
    if isinstance(error, dict):
        values.extend((error.get("message"), error.get("code")))
    else:
        values.append(error)
    return next((_text(value) for value in values if _text(value)), "未知错误")


def _is_key_error(message: str) -> bool:
    normalized = message.casefold()
    return any(term in normalized for term in KEY_ERROR_TERMS)


def _validate_payload(provider: _Provider, payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    if provider.name == "justone":
        code = _business_code(payload)
        if code == 0:
            return
        message = _error_message(payload)
        if code == 301:
            raise RapidAPINetworkError(f"业务错误 {code}: {message}")
        if code in SWITCHABLE_CODES:
            raise RapidAPIKeyError(f"业务错误 {code}: {message}")
        raise RapidAPIError(f"业务错误 {code}: {message}")

    success = _direct_value(payload, ("ok", "success"))
    code_value = _direct_value(payload, ("code", "status_code"))
    message = _error_message(payload)
    if _is_key_error(message):
        raise RapidAPIKeyError(message)
    if success is False or str(success).strip().lower() == "false":
        raise RapidAPIError(message)
    if code_value is not None:
        normalized_code = str(code_value).strip().lower()
        has_data = _direct_value(payload, ("data", "result", "results")) is not None
        if normalized_code not in {"0", "200", "ok", "success"} and not has_data:
            raise RapidAPIError(f"业务错误 {code_value}: {message}")


def _https_url(value: Any) -> str:
    url = _text(value)
    if url.startswith("http://"):
        return "https://" + url.removeprefix("http://")
    if url.startswith("//"):
        return "https:" + url
    return url


def _stable_article_id(url: str, item: dict[str, Any]) -> str:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    message_id = _text(query.get("mid", [""])[0] or item.get("appmsgid"))
    position = _text(query.get("idx", [""])[0] or item.get("position") or "1")
    if message_id:
        account_id = _text(query.get("__biz", [""])[0])
        account_basis = account_id or parsed.path
        account_hash = hashlib.sha256(account_basis.encode("utf-8")).hexdigest()[:8]
        return f"wx-{account_hash}-{message_id}-{position or '1'}"
    return "wx-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


def _canonical_article_url(value: Any) -> str:
    url = _https_url(value)
    parsed = urlsplit(url)
    if parsed.netloc.lower() != "mp.weixin.qq.com":
        return url
    allowed = {"__biz", "mid", "idx", "sn"}
    query = [
        (key, item)
        for key, values in parse_qs(parsed.query).items()
        if key in allowed
        for item in values
    ]
    if parsed.path.rstrip("/") == "/s" and query:
        return urlunsplit(("https", "mp.weixin.qq.com", "/s", urlencode(query), ""))
    return urlunsplit(("https", "mp.weixin.qq.com", parsed.path, "", ""))


def _deep_article_url(value: Any) -> str:
    for item in _recursive_dicts(value):
        url = _canonical_article_url(_direct_value(item, URL_FIELDS))
        parsed = urlsplit(url)
        if parsed.netloc.lower() == "mp.weixin.qq.com" and parsed.path.startswith("/s"):
            return url
    return ""


def _extract_history_page(payload: Any) -> HistoryPage:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise RapidAPIError("历史文章响应缺少 data 对象")

    data = payload["data"]
    message_list = data.get("MsgList")
    messages = message_list.get("Msg", []) if isinstance(message_list, dict) else []
    if isinstance(messages, dict):
        messages = [messages]
    if not isinstance(messages, list):
        raise RapidAPIError("历史文章响应缺少 MsgList.Msg 数组")

    rows: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        base_info = message.get("BaseInfo")
        app_message = message.get("AppMsg")
        if not isinstance(base_info, dict) or not isinstance(app_message, dict):
            continue
        published = base_info.get("DateTime")
        details = app_message.get("DetailInfo", [])
        if isinstance(details, dict):
            details = [details]
        if not isinstance(details, list):
            continue
        for position, detail in enumerate(details, start=1):
            if not isinstance(detail, dict):
                continue
            url = _canonical_article_url(detail.get("ContentUrl"))
            if not url or published is None:
                continue
            identity = {
                "appmsgid": base_info.get("MsgId"),
                "position": detail.get("ItemIndex") or position,
            }
            rows.append(
                {
                    "id": _stable_article_id(url, identity),
                    "title": _text(detail.get("Title")),
                    "url": url,
                    "coverUrl": _https_url(detail.get("CoverImgUrl")),
                    "publishTime": published,
                }
            )

    paging_info = data.get("PagingInfo")
    if not isinstance(paging_info, dict) and isinstance(message_list, dict):
        paging_info = message_list.get("PagingInfo")
    if not isinstance(paging_info, dict):
        paging_info = {}
    next_offset = _text(paging_info.get("Offset"))
    is_end = _text(paging_info.get("IsEnd") or "0").lower() in {"1", "true"}
    return HistoryPage(rows=rows, next_offset=next_offset, is_end=is_end)


def _article_rows(payload: Any) -> list[dict[str, Any]]:
    rows_by_url: dict[str, dict[str, Any]] = {}

    def visit(value: Any, context: dict[str, Any]) -> None:
        if isinstance(value, list):
            for child in value:
                visit(child, context)
            return
        if not isinstance(value, dict):
            return

        next_context = dict(context)
        for context_name, fields in (
            ("title", TITLE_FIELDS),
            ("cover", COVER_FIELDS),
            ("published", PUBLISHED_FIELDS),
            ("appmsgid", ARTICLE_ID_FIELDS),
            ("position", POSITION_FIELDS),
        ):
            candidate = _direct_value(value, fields)
            if candidate is not None and _text(candidate):
                next_context[context_name] = candidate

        direct_url = _direct_value(value, URL_FIELDS)
        url = _canonical_article_url(direct_url)
        parsed = urlsplit(url)
        published = next_context.get("published")
        if (
            parsed.netloc.lower() == "mp.weixin.qq.com"
            and parsed.path.startswith("/s")
            and published is not None
        ):
            identity = {
                "appmsgid": next_context.get("appmsgid"),
                "position": next_context.get("position"),
            }
            rows_by_url[url] = {
                "id": _stable_article_id(url, identity),
                "title": _text(next_context.get("title")),
                "url": url,
                "coverUrl": _https_url(next_context.get("cover")),
                "publishTime": published,
            }

        for child in value.values():
            visit(child, next_context)

    visit(payload, {})
    return list(rows_by_url.values())


def _boolean_value(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    normalized = _text(value).lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    return None


def _reported_row_count(payload: Any) -> int:
    for item in _recursive_dicts(payload):
        count = _direct_value(item, ("count", "total", "total_count"))
        try:
            if count is not None and int(count) > 0:
                return int(count)
        except (TypeError, ValueError):
            pass
        rows = _direct_value(item, ("list", "articles", "items", "rows"))
        if isinstance(rows, list) and rows:
            return len(rows)
    return 0


def _extract_generic_history_page(
    payload: Any,
    provider: _Provider,
    current_cursor: str,
) -> HistoryPage:
    rows = _article_rows(payload)
    reported_row_count = _reported_row_count(payload)
    if not rows and reported_row_count:
        raise RapidAPIError(
            f"{provider.label} 返回了 {reported_row_count} 条记录，但未能解析文章字段"
        )
    end_value = _boolean_value(_deep_value(payload, ("is_end", "isend", "end")))
    has_more = _boolean_value(
        _deep_value(payload, ("has_more", "hasmore", "more"))
    )

    if provider.name == "wechat-data":
        next_cursor = _text(
            _deep_value(
                payload,
                ("next_cursor", "nextcursor", "next_buffer", "buffer", "cursor"),
            )
        )
        if next_cursor == current_cursor:
            next_cursor = ""
        is_end = end_value is True or has_more is False or not next_cursor
        return HistoryPage(rows=rows, next_offset=next_cursor, is_end=is_end)

    current_page = int(current_cursor or "1")
    is_end = end_value is True or has_more is False or not rows
    next_page = "" if is_end else str(current_page + 1)
    return HistoryPage(rows=rows, next_offset=next_page, is_end=is_end)


def _extract_detail(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RapidAPIError("文章详情响应不是 JSON 对象")
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    if not isinstance(data, dict):
        raise RapidAPIError("文章详情缺少 data 对象")

    detail = {
        "title": _text(data.get("title")),
        "sourceName": _text(data.get("nickname")),
        "sourceUrl": _canonical_article_url(data.get("article_url") or data.get("url")),
        "description": _text(data.get("desc")),
        "coverUrl": _https_url(data.get("cover_url")),
        "html": _text(data.get("html")),
    }
    missing = [key for key in ("title", "sourceName", "html") if not detail[key]]
    if missing:
        raise RapidAPIError("文章详情缺少必要字段: " + ", ".join(missing))
    return detail


def _extract_generic_detail(
    payload: Any,
    article_url: str,
    provider: _Provider,
    expected_source_name: str = "",
) -> dict[str, Any]:
    best_item: Optional[dict[str, Any]] = None
    best_html = ""
    best_score = -1
    for item in _recursive_dicts(payload):
        html_value = _text(_direct_value(item, HTML_FIELDS))
        if not html_value:
            continue
        score = len(html_value)
        if _text(_direct_value(item, TITLE_FIELDS)):
            score += 10_000
        if _text(_direct_value(item, SOURCE_NAME_FIELDS)):
            score += 10_000
        if score > best_score:
            best_item = item
            best_html = html_value
            best_score = score

    if best_item is None:
        raise RapidAPIError(f"{provider.label} 文章详情缺少正文 HTML")

    title = _text(_direct_value(best_item, TITLE_FIELDS)) or _text(
        _deep_value(payload, TITLE_FIELDS)
    )
    source_name = (
        _text(_direct_value(best_item, SOURCE_NAME_FIELDS))
        or _text(_deep_value(payload, SOURCE_NAME_FIELDS))
        or expected_source_name.strip()
    )
    if "<" not in best_html and ">" not in best_html:
        best_html = f"<p>{html_module.escape(best_html)}</p>"
    if "js_content" not in best_html and "rich_media_content" not in best_html:
        best_html = f'<div id="js_content">{best_html}</div>'
    source_url = _canonical_article_url(_direct_value(best_item, URL_FIELDS))
    parsed_source_url = urlsplit(source_url)
    if not (
        parsed_source_url.netloc.lower() == "mp.weixin.qq.com"
        and parsed_source_url.path.startswith("/s")
    ):
        source_url = _deep_article_url(payload) or article_url

    detail = {
        "title": title,
        "sourceName": source_name,
        "sourceUrl": _canonical_article_url(source_url),
        "description": _text(_direct_value(best_item, DESCRIPTION_FIELDS))
        or _text(_deep_value(payload, DESCRIPTION_FIELDS)),
        "coverUrl": _https_url(
            _direct_value(best_item, COVER_FIELDS)
            or _deep_value(payload, COVER_FIELDS)
        ),
        "html": best_html,
    }
    missing = [key for key in ("title", "sourceName", "html") if not detail[key]]
    if missing:
        raise RapidAPIError(
            f"{provider.label} 文章详情缺少必要字段: " + ", ".join(missing)
        )
    return detail


def _extract_original_id(payload: Any) -> str:
    candidates = [
        _text(_direct_value(item, ACCOUNT_ID_FIELDS))
        for item in _recursive_dicts(payload)
    ]
    return next((value for value in candidates if value.startswith("gh_")), "")


def _extract_account_id(payload: Any, account_name: str) -> str:
    normalized_name = account_name.strip().casefold()
    fallback: list[str] = []
    for item in _recursive_dicts(payload):
        identifier = _text(_direct_value(item, ACCOUNT_ID_FIELDS))
        if not identifier:
            continue
        fallback.append(identifier)
        candidate_name = _text(_direct_value(item, SOURCE_NAME_FIELDS + TITLE_FIELDS))
        if candidate_name.casefold() == normalized_name:
            return identifier
    unique = list(dict.fromkeys(fallback))
    return unique[0] if len(unique) == 1 else ""


def _encode_cursor(provider_name: str, cursor: str) -> str:
    return f"{CURSOR_PREFIX}{provider_name}:{cursor}" if cursor else ""


def _decode_cursor(cursor: str) -> tuple[Optional[str], str]:
    value = cursor.strip()
    if not value:
        return None, ""
    if not value.startswith(CURSOR_PREFIX):
        return "justone", value
    provider_name, separator, provider_cursor = value.removeprefix(
        CURSOR_PREFIX
    ).partition(":")
    if not separator or provider_name not in PROVIDER_BY_NAME:
        raise RapidAPIError("RapidAPI 列表游标格式无效")
    return provider_name, provider_cursor


class RapidAPIClient:
    def __init__(
        self,
        key_pool: APIKeyPool,
        timeout_seconds: int = 120,
        api_url: str = DEFAULT_API_URL,
    ) -> None:
        self._keys = key_pool.keys
        self._timeout_seconds = timeout_seconds
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "Gator-Investment-Research/rapidapi-sync",
            }
        )
        self._providers = tuple(
            _Provider(provider.name, provider.label, provider.host, api_url.rstrip("/"))
            if provider.name == "justone"
            else provider
            for provider in PROVIDERS
        )
        ordinal = date.today().toordinal()
        self._key_cursor = {
            provider.name: (ordinal + position) % len(self._keys)
            for position, provider in enumerate(self._providers)
        }
        self._provider_cursor = {
            "history": ordinal % len(self._providers),
            "detail": (ordinal + 1) % len(self._providers),
        }
        self._blocked_keys = {provider.name: set() for provider in self._providers}
        self._account_ids: dict[tuple[str, str], str] = {}

    @property
    def key_count(self) -> int:
        return len(self._keys)

    @property
    def provider_count(self) -> int:
        return len(self._providers)

    def _key_order(self, provider: _Provider) -> list[int]:
        start = self._key_cursor[provider.name]
        blocked = self._blocked_keys[provider.name]
        return [
            (start + offset) % self.key_count
            for offset in range(self.key_count)
            if (start + offset) % self.key_count not in blocked
        ]

    def _provider_order(self, capability: str) -> list[_Provider]:
        start = self._provider_cursor[capability]
        return [
            self._providers[(start + offset) % len(self._providers)]
            for offset in range(len(self._providers))
        ]

    def _request_json(
        self,
        provider: _Provider,
        key_index: int,
        method: str,
        path: str,
        params: dict[str, Any],
        body_mode: str = "query",
    ) -> Any:
        request_arguments: dict[str, Any]
        if body_mode == "form":
            request_arguments = {"data": params}
            content_type = "application/x-www-form-urlencoded"
        elif body_mode == "json":
            request_arguments = {"json": params}
            content_type = "application/json"
        else:
            request_arguments = {"params": params}
            content_type = "application/json"

        try:
            response = self._session.request(
                method,
                f"{provider.base_url}{path}",
                **request_arguments,
                headers={
                    "Content-Type": content_type,
                    "x-rapidapi-host": provider.host,
                    "x-rapidapi-key": self._keys[key_index],
                },
                timeout=self._timeout_seconds,
            )
        except requests.Timeout as error:
            raise RapidAPINetworkError(f"{provider.label} 请求超时") from error
        except requests.RequestException as error:
            raise RapidAPINetworkError(
                f"{provider.label} 网络请求失败: {type(error).__name__}"
            ) from error

        quota_headers = [
            f"{name.removeprefix('x-ratelimit-')}={value}"
            for name, value in sorted(
                (header.lower(), header_value)
                for header, header_value in response.headers.items()
                if header.lower().startswith("x-ratelimit-")
                and (
                    header.lower().endswith("-limit")
                    or header.lower().endswith("-remaining")
                )
            )
        ]
        if quota_headers:
            endpoint = path.rsplit("/", 1)[-1]
            print(
                f"RapidAPI {provider.label}/{endpoint} 配额（Key {key_index + 1}/"
                f"{self.key_count}）：{', '.join(quota_headers)}"
            )

        response_text = (response.text or "").strip()
        if response.status_code in {401, 403, 429}:
            raise RapidAPIKeyError(
                f"{provider.label} 返回 HTTP {response.status_code}"
            )
        if 500 <= response.status_code < 600:
            raise RapidAPINetworkError(
                f"{provider.label} 返回 HTTP {response.status_code}"
            )
        if response.status_code != 200:
            raise RapidAPIError(
                f"{provider.label} 返回 HTTP {response.status_code}: "
                f"{response_text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise RapidAPIError(f"{provider.label} 返回了无效 JSON") from error

        _validate_payload(provider, payload)
        return payload

    def _with_key_failover(
        self,
        provider: _Provider,
        request: Callable[[int], ResponseValue],
    ) -> ResponseValue:
        key_order = self._key_order(provider)
        if not key_order:
            raise RapidAPIProviderUnavailable(
                f"{provider.label} 没有剩余的已订阅 Key"
            )

        last_error: Optional[RapidAPIKeyError] = None
        for key_index in key_order:
            try:
                result = request(key_index)
            except RapidAPIKeyError as error:
                last_error = error
                self._blocked_keys[provider.name].add(key_index)
                print(
                    f"RapidAPI {provider.label} 的 Key {key_index + 1}/"
                    f"{self.key_count} 不可用（{error}），仅在该产品中跳过"
                )
                continue
            self._key_cursor[provider.name] = (key_index + 1) % self.key_count
            return result

        raise RapidAPIProviderUnavailable(
            f"{provider.label} 的所有 Key 均未订阅、无权限或额度耗尽"
        ) from last_error

    def _with_provider_failover(
        self,
        capability: str,
        request: Callable[[_Provider], ResponseValue],
        provider_name: Optional[str] = None,
    ) -> tuple[_Provider, ResponseValue]:
        providers = self._provider_order(capability)
        if provider_name is not None:
            providers = [
                provider
                for provider in self._providers
                if provider.name == provider_name
            ]
        errors: list[str] = []
        for provider in providers:
            try:
                result = request(provider)
            except RapidAPIError as error:
                errors.append(f"{provider.label}: {error}")
                if provider_name is None:
                    print(f"RapidAPI {provider.label} 暂不可用（{error}），切换产品")
                continue

            if provider_name is None:
                provider_index = next(
                    index
                    for index, item in enumerate(self._providers)
                    if item.name == provider.name
                )
                self._provider_cursor[capability] = (
                    provider_index + 1
                ) % len(self._providers)
            return provider, result

        detail = "；".join(errors) if errors else "没有可用产品"
        raise RapidAPIError(f"RapidAPI 三套产品均未返回可用数据：{detail}")

    def _resolve_wechat_data_id(
        self,
        provider: _Provider,
        key_index: int,
        reference: AccountReference,
    ) -> str:
        if reference.wechat_data_wxid:
            return reference.wechat_data_wxid
        cache_key = (provider.name, reference.biz)
        if reference.biz and cache_key in self._account_ids:
            return self._account_ids[cache_key]
        if not reference.biz:
            raise RapidAPIProviderUnavailable(
                f"{provider.label} 列表接口缺少公众号 biz"
            )
        payload = self._request_json(
            provider,
            key_index,
            "POST",
            WECHAT_DATA_INFO_PATH,
            {"biz": reference.biz},
            body_mode="json",
        )
        identifier = _extract_original_id(payload)
        if not identifier:
            raise RapidAPIError(f"{provider.label} 未返回 gh_* 原始 ID")
        self._account_ids[cache_key] = identifier
        return identifier

    def _resolve_sian_id(
        self,
        provider: _Provider,
        key_index: int,
        reference: AccountReference,
    ) -> str:
        if reference.wechat_id:
            return reference.wechat_id
        cache_key = (provider.name, reference.name)
        if reference.name and cache_key in self._account_ids:
            return self._account_ids[cache_key]
        if not reference.name:
            raise RapidAPIProviderUnavailable(
                f"{provider.label} 列表接口缺少公众号名称或微信号"
            )
        payload = self._request_json(
            provider,
            key_index,
            "GET",
            SIAN_ACCOUNT_SEARCH_PATH,
            {
                "keyword": reference.name,
                "searchType": "accounts",
                "sortType": "_0",
                "page": 1,
            },
        )
        identifier = _extract_account_id(payload, reference.name)
        if not identifier:
            raise RapidAPIError(
                f"{provider.label} 未能为“{reference.name}”唯一匹配微信号"
            )
        self._account_ids[cache_key] = identifier
        return identifier

    def _fetch_history_from_provider(
        self,
        provider: _Provider,
        reference: AccountReference,
        cursor: str,
    ) -> HistoryPage:
        if provider.name == "justone":
            return self._with_key_failover(
                provider,
                lambda key_index: _extract_history_page(
                    self._request_json(
                        provider,
                        key_index,
                        "POST",
                        HISTORY_PATH,
                        {"url": reference.article_url, "offset": cursor},
                        body_mode="form",
                    )
                ),
            )
        if provider.name == "wechat-data":
            def fetch_wechat_data(key_index: int) -> HistoryPage:
                identifier = self._resolve_wechat_data_id(
                    provider, key_index, reference
                )
                payload = self._request_json(
                    provider,
                    key_index,
                    "POST",
                    WECHAT_DATA_HISTORY_PATH,
                    {"wxid": identifier, "cursor": cursor},
                    body_mode="json",
                )
                return _extract_generic_history_page(payload, provider, cursor)

            return self._with_key_failover(provider, fetch_wechat_data)

        def fetch_sian(key_index: int) -> HistoryPage:
            identifier = self._resolve_sian_id(provider, key_index, reference)
            page = int(cursor or "1")
            payload = self._request_json(
                provider,
                key_index,
                "GET",
                SIAN_HISTORY_PATH,
                {"wxid": identifier, "page": page},
            )
            return _extract_generic_history_page(payload, provider, str(page))

        return self._with_key_failover(provider, fetch_sian)

    def fetch_history_page(
        self,
        reference: AccountReference | str,
        offset: str = "",
        preferred_provider: Optional[str] = None,
    ) -> HistoryPage:
        """Fetch one list page while preserving provider-specific cursors."""
        account_reference = (
            reference
            if isinstance(reference, AccountReference)
            else AccountReference(name="", article_url=reference)
        )
        cursor_provider, provider_cursor = _decode_cursor(offset)
        provider_name = preferred_provider or cursor_provider
        provider, page = self._with_provider_failover(
            "history",
            lambda item: self._fetch_history_from_provider(
                item, account_reference, provider_cursor
            ),
            provider_name=provider_name,
        )
        next_offset = page.next_offset
        if preferred_provider is None:
            next_offset = _encode_cursor(provider.name, next_offset)
        return HistoryPage(
            rows=page.rows,
            next_offset=next_offset,
            is_end=page.is_end,
        )

    def _fetch_detail_from_provider(
        self,
        provider: _Provider,
        article_url: str,
        expected_source_name: str = "",
    ) -> dict[str, Any]:
        if provider.name == "justone":
            return self._with_key_failover(
                provider,
                lambda key_index: _extract_detail(
                    self._request_json(
                        provider,
                        key_index,
                        "GET",
                        DETAIL_PATH,
                        {"articleUrl": article_url},
                    )
                ),
            )
        if provider.name == "wechat-data":
            return self._with_key_failover(
                provider,
                lambda key_index: _extract_generic_detail(
                    self._request_json(
                        provider,
                        key_index,
                        "POST",
                        WECHAT_DATA_DETAIL_PATH,
                        {"url": article_url},
                        body_mode="json",
                    ),
                    article_url,
                    provider,
                    expected_source_name,
                ),
            )
        return self._with_key_failover(
            provider,
            lambda key_index: _extract_generic_detail(
                self._request_json(
                    provider,
                    key_index,
                    "GET",
                    SIAN_DETAIL_PATH,
                    {"articleUrl": article_url},
                ),
                article_url,
                provider,
                expected_source_name,
            ),
        )

    def fetch_article_detail(
        self,
        article_url: str,
        expected_source_name: str = "",
    ) -> dict[str, Any]:
        """Fetch archive-ready HTML from all subscribed products in rotation."""
        _, detail = self._with_provider_failover(
            "detail",
            lambda provider: self._fetch_detail_from_provider(
                provider,
                article_url,
                expected_source_name,
            ),
        )
        return detail
