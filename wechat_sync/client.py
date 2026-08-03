"""Minimal client for the WeRead relay used by wechat-mp-tools."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence, Union

import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CREDENTIAL_FILE = PROJECT_ROOT / "data" / "wechat" / "credentials.json"
DEFAULT_PLATFORM_URL = "https://weread.111965.xyz"


class WeReadRelayError(RuntimeError):
    """Base error for the WeRead relay."""


class CredentialsExpiredError(WeReadRelayError):
    """The stored WeRead credential is no longer accepted."""


class RateLimitedError(WeReadRelayError):
    """The relay rejected the request because of rate limiting."""


class RelayServerError(WeReadRelayError):
    """The relay failed for the current credential with a server error."""


@dataclass(frozen=True)
class Credentials:
    vid: str
    token: str
    platform_url: str


@dataclass(frozen=True)
class WeChatAccount:
    mp_id: str
    name: str
    cover_url: str
    intro: str


def _credentials_from_payload(payload: Any) -> list[Credentials]:
    if isinstance(payload, list):
        raw_accounts = payload
        default_platform_url = DEFAULT_PLATFORM_URL
    elif isinstance(payload, dict):
        raw_accounts = payload.get("accounts")
        if not isinstance(raw_accounts, list):
            raw_accounts = [payload]
        default_platform_url = str(payload.get("platform_url", "")).strip()
    else:
        raise WeReadRelayError("微信读书账号池必须是 JSON 对象或数组")

    credentials: list[Credentials] = []
    seen: set[tuple[str, str]] = set()
    for position, item in enumerate(raw_accounts, start=1):
        if not isinstance(item, dict):
            raise WeReadRelayError(f"微信读书账号池第 {position} 项格式无效")
        vid = str(item.get("vid", "")).strip()
        token = str(item.get("token", "")).strip()
        platform_url = str(item.get("platform_url", "")).strip()
        platform_url = platform_url or default_platform_url or DEFAULT_PLATFORM_URL
        if not vid or not token:
            raise WeReadRelayError(
                f"微信读书账号池第 {position} 项缺少 vid 或 token"
            )
        key = (vid, platform_url.rstrip("/"))
        if key in seen:
            continue
        seen.add(key)
        credentials.append(
            Credentials(vid=vid, token=token, platform_url=platform_url)
        )

    if not credentials:
        raise WeReadRelayError("微信读书账号池中没有可用凭据")
    return credentials


def load_local_credentials_pool(
    path: Path = DEFAULT_CREDENTIAL_FILE,
) -> list[Credentials]:
    """Load the ordered credential pool from the ignored local file."""
    if not path.exists():
        raise WeReadRelayError(
            "未找到微信读书凭据，请先运行 python -m wechat_sync.auth"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise WeReadRelayError(f"无法读取本地微信读书账号池: {error}") from error
    return _credentials_from_payload(payload)


def load_credentials_pool(
    path: Path = DEFAULT_CREDENTIAL_FILE,
) -> list[Credentials]:
    """Load an ordered pool from Actions secrets or the ignored local file."""
    env_pool = os.environ.get("WEREAD_ACCOUNTS", "").strip()
    if env_pool:
        try:
            return _credentials_from_payload(json.loads(env_pool))
        except ValueError as error:
            raise WeReadRelayError(
                "WEREAD_ACCOUNTS 不是有效 JSON，请重新上传账号池 Secret"
            ) from error

    env_vid = os.environ.get("WEREAD_VID", "").strip()
    env_token = os.environ.get("WEREAD_TOKEN", "").strip()
    env_platform = os.environ.get("WEREAD_PLATFORM_URL", "").strip()
    if env_vid and env_token:
        return [
            Credentials(
                vid=env_vid,
                token=env_token,
                platform_url=env_platform or DEFAULT_PLATFORM_URL,
            )
        ]

    return load_local_credentials_pool(path)


def load_credentials(path: Path = DEFAULT_CREDENTIAL_FILE) -> Credentials:
    """Load the first credential for backward-compatible callers."""
    return load_credentials_pool(path)[0]


def _error_code(payload: Any) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    for key in ("ret", "errCode", "err_code", "code"):
        try:
            return int(payload[key])
        except (KeyError, TypeError, ValueError):
            continue
    return None


class WeReadClient:
    def __init__(
        self,
        credentials: Union[Credentials, Sequence[Credentials]],
        timeout_seconds: int = 30,
    ):
        if isinstance(credentials, Credentials):
            pool = [credentials]
        else:
            pool = list(credentials)
        if not pool:
            raise WeReadRelayError("微信读书账号池为空")

        self._credentials = pool
        self._timeout_seconds = timeout_seconds
        self._active_index = 0
        self._sessions: list[requests.Session] = []
        for credential in pool:
            session = requests.Session()
            session.headers.update(
                {
                    "xid": credential.vid,
                    "Authorization": f"Bearer {credential.token}",
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                }
            )
            self._sessions.append(session)

    @property
    def credential_count(self) -> int:
        return len(self._credentials)

    def _credential_order(self) -> list[int]:
        count = self.credential_count
        return [(self._active_index + offset) % count for offset in range(count)]

    def _request_json_with_credential(
        self,
        credential_index: int,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        credential = self._credentials[credential_index]
        session = self._sessions[credential_index]
        url = f"{credential.platform_url.rstrip('/')}{path}"
        response = session.request(
            method,
            url,
            timeout=self._timeout_seconds,
            **kwargs,
        )
        response_text = (response.text or "").strip()
        if response.status_code == 401 or "WeReadError401" in response_text:
            raise CredentialsExpiredError("微信读书登录凭据已失效，请重新扫码")
        if response.status_code == 429 or "WeReadError429" in response_text:
            raise RateLimitedError("微信读书中转服务触发频率限制，请稍后再试")
        if 500 <= response.status_code < 600:
            raise RelayServerError(
                f"微信读书中转服务返回 HTTP {response.status_code}"
            )
        if response.status_code != 200:
            detail = response_text[:300]
            raise WeReadRelayError(
                f"微信读书中转服务返回 HTTP {response.status_code}: {detail}"
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise WeReadRelayError("微信读书中转服务返回了无效 JSON") from error

        code = _error_code(payload)
        if code == 200003:
            raise CredentialsExpiredError("微信读书登录凭据已失效，请重新扫码")
        if code == 200013:
            raise RateLimitedError("微信读书中转服务触发频率限制，请稍后再试")
        return payload

    def _request_json(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        last_switchable_error: Optional[WeReadRelayError] = None
        for credential_index in self._credential_order():
            try:
                payload = self._request_json_with_credential(
                    credential_index,
                    method,
                    path,
                    **kwargs,
                )
            except (
                CredentialsExpiredError,
                RateLimitedError,
                RelayServerError,
            ) as error:
                last_switchable_error = error
                print(
                    f"账号池第 {credential_index + 1}/{self.credential_count} 个账号"
                    f"不可用（{error}），尝试下一个账号"
                )
                continue
            self._active_index = credential_index
            return payload

        if last_switchable_error is not None:
            raise last_switchable_error
        raise WeReadRelayError("微信读书账号池中没有可用账号")

    def resolve_account(self, article_url: str) -> list[WeChatAccount]:
        payload = self._request_json(
            "POST",
            "/api/v2/platform/wxs2mp",
            json={"url": article_url},
            headers={"Content-Type": "application/json"},
        )
        raw_accounts = payload if isinstance(payload, list) else [payload]
        accounts = []
        for item in raw_accounts:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            cover_url = str(item.get("cover", "")).strip()
            if cover_url.startswith("http://"):
                cover_url = "https://" + cover_url.removeprefix("http://")
            elif cover_url.startswith("//"):
                cover_url = "https:" + cover_url
            accounts.append(
                WeChatAccount(
                    mp_id=str(item["id"]),
                    name=str(item.get("name", "")).strip(),
                    cover_url=cover_url,
                    intro=str(item.get("intro", "")).strip(),
                )
            )
        return accounts

    @staticmethod
    def _extract_articles(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("articles", "items", "list", "data"):
                items = payload.get(key)
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)]
        return []

    def fetch_articles(self, mp_id: str, page: int = 1) -> list[dict[str, Any]]:
        last_switchable_error: Optional[WeReadRelayError] = None
        received_empty_response = False
        for credential_index in self._credential_order():
            try:
                payload = self._request_json_with_credential(
                    credential_index,
                    "GET",
                    f"/api/v2/platform/mps/{mp_id}/articles",
                    params={"page": page},
                )
            except (
                CredentialsExpiredError,
                RateLimitedError,
                RelayServerError,
            ) as error:
                last_switchable_error = error
                print(
                    f"账号池第 {credential_index + 1}/{self.credential_count} 个账号"
                    f"不可用（{error}），尝试下一个账号"
                )
                continue

            articles = self._extract_articles(payload)
            if articles:
                self._active_index = credential_index
                return articles
            received_empty_response = True
            if self.credential_count > 1:
                print(
                    f"账号池第 {credential_index + 1}/{self.credential_count} 个账号"
                    f"返回第 {page} 页空列表，尝试下一个账号"
                )

        if received_empty_response:
            return []
        if last_switchable_error is not None:
            raise last_switchable_error
        return []
