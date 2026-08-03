"""Minimal client for the WeRead relay used by wechat-mp-tools."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def load_credentials(path: Path = DEFAULT_CREDENTIAL_FILE) -> Credentials:
    """Load credentials from Actions secrets or the ignored local file."""
    env_vid = os.environ.get("WEREAD_VID", "").strip()
    env_token = os.environ.get("WEREAD_TOKEN", "").strip()
    env_platform = os.environ.get("WEREAD_PLATFORM_URL", "").strip()
    if env_vid and env_token:
        return Credentials(
            vid=env_vid,
            token=env_token,
            platform_url=env_platform or DEFAULT_PLATFORM_URL,
        )

    if not path.exists():
        raise WeReadRelayError(
            "未找到微信读书凭证，请先运行 python -m wechat_sync.auth"
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    vid = str(payload.get("vid", "")).strip()
    token = str(payload.get("token", "")).strip()
    platform_url = str(payload.get("platform_url", "")).strip()
    if not vid or not token:
        raise WeReadRelayError("本地凭证缺少 vid 或 token，请重新扫码")

    return Credentials(
        vid=vid,
        token=token,
        platform_url=platform_url or DEFAULT_PLATFORM_URL,
    )


class WeReadClient:
    def __init__(self, credentials: Credentials, timeout_seconds: int = 30):
        self._credentials = credentials
        self._timeout_seconds = timeout_seconds
        self._session = requests.Session()
        self._session.headers.update(
            {
                "xid": credentials.vid,
                "Authorization": f"Bearer {credentials.token}",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

    def _request_json(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        url = f"{self._credentials.platform_url.rstrip('/')}{path}"
        response = self._session.request(
            method,
            url,
            timeout=self._timeout_seconds,
            **kwargs,
        )
        if response.status_code == 401:
            raise CredentialsExpiredError("微信读书登录凭证已失效，请重新扫码")
        if response.status_code == 429:
            raise RateLimitedError("微信读书中转服务触发频率限制，请稍后再试")
        if response.status_code != 200:
            detail = (response.text or "").strip()[:300]
            raise WeReadRelayError(
                f"微信读书中转服务返回 HTTP {response.status_code}: {detail}"
            )
        try:
            return response.json()
        except ValueError as error:
            raise WeReadRelayError("微信读书中转服务返回了无效 JSON") from error

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

    def fetch_articles(self, mp_id: str, page: int = 1) -> list[dict[str, Any]]:
        payload = self._request_json(
            "GET",
            f"/api/v2/platform/mps/{mp_id}/articles",
            params={"page": page},
        )
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("articles", "items", "list", "data"):
                items = payload.get(key)
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)]
        return []
