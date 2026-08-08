"""RapidAPI client with ordered API-key failover for WeChat article lists."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, TypeVar
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KEY_FILE = PROJECT_ROOT / "data" / "wechat" / "rapidapi-keys.json"
DEFAULT_API_HOST = "weixin-wechat-official-accounts-platform.p.rapidapi.com"
DEFAULT_API_URL = f"https://{DEFAULT_API_HOST}"
HISTORY_PATH = "/api/weixin/get-account-history-articles/v2"
DETAIL_PATH = "/api/weixin/get-article-detail/v4"
SWITCHABLE_CODES = {100, 301, 302, 303, 500, 600, 601, 602}
ResponseValue = TypeVar("ResponseValue")


class RapidAPIError(RuntimeError):
    """The RapidAPI article-list service could not return usable data."""


class RapidAPIKeyError(RapidAPIError):
    """An API key is invalid, unauthorized, or out of quota."""


class RapidAPINetworkError(RapidAPIError):
    """The request failed before a usable API response was received."""


@dataclass(frozen=True)
class APIKeyPool:
    keys: tuple[str, ...]

    @property
    def size(self) -> int:
        return len(self.keys)


@dataclass(frozen=True)
class HistoryPage:
    rows: list[dict[str, Any]]
    next_offset: str
    is_end: bool


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


def _business_code(payload: Any) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    try:
        return int(payload.get("code"))
    except (TypeError, ValueError):
        return None


def _https_url(value: Any) -> str:
    url = str(value or "").strip()
    if url.startswith("http://"):
        return "https://" + url.removeprefix("http://")
    if url.startswith("//"):
        return "https:" + url
    return url


def _stable_article_id(url: str, item: dict[str, Any]) -> str:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    message_id = str(item.get("appmsgid") or query.get("mid", [""])[0]).strip()
    position = str(item.get("position") or query.get("idx", ["1"])[0]).strip()
    if message_id:
        account_id = str(query.get("__biz", [""])[0]).strip()
        account_hash = hashlib.sha256(account_id.encode("utf-8")).hexdigest()[:8]
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


def _extract_history_page(payload: Any) -> HistoryPage:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise RapidAPIError("RapidAPI 历史文章响应缺少 data 对象")

    data = payload["data"]
    message_list = data.get("MsgList")
    messages = message_list.get("Msg", []) if isinstance(message_list, dict) else []
    if isinstance(messages, dict):
        messages = [messages]
    if not isinstance(messages, list):
        raise RapidAPIError("RapidAPI 历史文章响应缺少 MsgList.Msg 数组")

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
                    "title": str(detail.get("Title") or "").strip(),
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
    next_offset = str(paging_info.get("Offset") or "").strip()
    is_end = str(paging_info.get("IsEnd") or "0").strip().lower() in {
        "1",
        "true",
    }
    return HistoryPage(rows=rows, next_offset=next_offset, is_end=is_end)


def _extract_detail(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RapidAPIError("RapidAPI 文章详情响应不是 JSON 对象")
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    if not isinstance(data, dict):
        raise RapidAPIError("RapidAPI 文章详情缺少 data 对象")

    detail = {
        "title": str(data.get("title") or "").strip(),
        "sourceName": str(data.get("nickname") or "").strip(),
        "sourceUrl": _canonical_article_url(
            data.get("article_url") or data.get("url")
        ),
        "description": str(data.get("desc") or "").strip(),
        "coverUrl": _https_url(data.get("cover_url")),
        "html": str(data.get("html") or "").strip(),
    }
    missing = [key for key in ("title", "sourceName", "html") if not detail[key]]
    if missing:
        raise RapidAPIError(
            "RapidAPI 文章详情缺少必要字段: " + ", ".join(missing)
        )
    return detail


class RapidAPIClient:
    def __init__(
        self,
        key_pool: APIKeyPool,
        timeout_seconds: int = 120,
        api_url: str = DEFAULT_API_URL,
    ) -> None:
        self._keys = key_pool.keys
        self._timeout_seconds = timeout_seconds
        self._api_url = api_url.rstrip("/")
        # Spread scheduled runs across accounts instead of exhausting key 1 first.
        self._active_index = date.today().toordinal() % len(self._keys)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "x-rapidapi-host": DEFAULT_API_HOST,
                "User-Agent": "Gator-Investment-Research/rapidapi-sync",
            }
        )

    @property
    def key_count(self) -> int:
        return len(self._keys)

    def _key_order(self) -> list[int]:
        return [
            (self._active_index + offset) % self.key_count
            for offset in range(self.key_count)
        ]

    def _request_json(
        self,
        key_index: int,
        method: str,
        path: str,
        params: dict[str, Any],
        form_encoded: bool = False,
    ) -> Any:
        request_arguments = {"data": params} if form_encoded else {"params": params}
        try:
            response = self._session.request(
                method,
                f"{self._api_url}{path}",
                **request_arguments,
                headers={"x-rapidapi-key": self._keys[key_index]},
                timeout=self._timeout_seconds,
            )
        except requests.Timeout as error:
            raise RapidAPINetworkError("RapidAPI 请求超时") from error
        except requests.RequestException as error:
            raise RapidAPINetworkError(
                f"RapidAPI 网络请求失败: {type(error).__name__}"
            ) from error

        response_text = (response.text or "").strip()
        if response.status_code in {401, 403, 429}:
            raise RapidAPIKeyError(f"RapidAPI 返回 HTTP {response.status_code}")
        if 500 <= response.status_code < 600:
            raise RapidAPINetworkError(f"RapidAPI 返回 HTTP {response.status_code}")
        if response.status_code != 200:
            raise RapidAPIError(
                f"RapidAPI 返回 HTTP {response.status_code}: {response_text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise RapidAPIError("RapidAPI 返回了无效 JSON") from error

        code = _business_code(payload)
        if code != 0:
            message = str(payload.get("message") or "未知错误")
            if code in SWITCHABLE_CODES:
                raise RapidAPIKeyError(f"RapidAPI 业务错误 {code}: {message}")
            raise RapidAPIError(f"RapidAPI 业务错误 {code}: {message}")
        return payload

    def _with_failover(
        self,
        request: Callable[[int], ResponseValue],
    ) -> ResponseValue:
        last_error: Optional[RapidAPIError] = None
        for key_index in self._key_order():
            try:
                result = request(key_index)
            except (RapidAPIKeyError, RapidAPINetworkError) as error:
                last_error = error
                print(
                    f"RapidAPI Key 池第 {key_index + 1}/{self.key_count} 个不可用"
                    f"（{error}），尝试下一个"
                )
                continue
            self._active_index = key_index
            return result

        if last_error is not None:
            raise last_error
        raise RapidAPIError("RapidAPI Key 池中没有可用 Key")

    def fetch_history_page(self, identifier: str, offset: str = "") -> HistoryPage:
        """Fetch one V2 article-list page using the previous response cursor."""
        return self._with_failover(
            lambda key_index: _extract_history_page(
                self._request_json(
                    key_index,
                    "POST",
                    HISTORY_PATH,
                    {"url": identifier, "offset": offset},
                    form_encoded=True,
                )
            )
        )

    def fetch_article_detail(self, article_url: str) -> dict[str, Any]:
        """Fetch archive-ready HTML instead of triggering WeChat's link captcha."""
        return self._with_failover(
            lambda key_index: _extract_detail(
                self._request_json(
                    key_index,
                    "GET",
                    DETAIL_PATH,
                    {"articleUrl": article_url},
                )
            )
        )
