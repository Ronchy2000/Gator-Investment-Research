"""Resolve and persist the non-secret configuration for one WeChat account."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from wechat_sync.client import WeChatAccount, WeReadClient, WeReadRelayError, load_credentials


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ACCOUNT_FILE = PROJECT_ROOT / "wechat_sync" / "account.json"
DEFAULT_ACCOUNT_NAME = "获得信息差"
DEFAULT_SEED_URL = "https://mp.weixin.qq.com/s/zmDm_g8Jh9M6gEI1R8xq7g"
DEFAULT_EARLIEST_DATE = "2026-06-15"


def _select_account(
    accounts: list[WeChatAccount],
    expected_name: str,
) -> WeChatAccount:
    exact_matches = [account for account in accounts if account.name == expected_name]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(accounts) == 1 and not accounts[0].name:
        return accounts[0]
    available_names = ", ".join(account.name or "未命名" for account in accounts)
    raise WeReadRelayError(
        f"种子链接未唯一解析为公众号“{expected_name}”，返回结果：{available_names or '空'}"
    )


def _save_account(path: Path, account: WeChatAccount, seed_url: str, earliest_date: str) -> None:
    payload = {
        "name": account.name or DEFAULT_ACCOUNT_NAME,
        "mp_id": account.mp_id,
        "cover_url": account.cover_url,
        "intro": account.intro,
        "seed_article_url": seed_url,
        "earliest_date": earliest_date,
        "sync_mode": "full_then_incremental",
        "initialized_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="初始化单公众号同步配置")
    parser.add_argument("--name", default=DEFAULT_ACCOUNT_NAME)
    parser.add_argument("--seed-url", default=DEFAULT_SEED_URL)
    parser.add_argument("--earliest-date", default=DEFAULT_EARLIEST_DATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_ACCOUNT_FILE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    parsed_url = urlparse(args.seed_url)
    if parsed_url.scheme != "https" or parsed_url.netloc != "mp.weixin.qq.com":
        raise SystemExit("种子链接必须是 https://mp.weixin.qq.com/ 公开文章链接")
    try:
        datetime.strptime(args.earliest_date, "%Y-%m-%d")
    except ValueError as error:
        raise SystemExit("earliest-date 必须使用 YYYY-MM-DD 格式") from error

    try:
        client = WeReadClient(load_credentials())
        account = _select_account(client.resolve_account(args.seed_url), args.name)
        _save_account(args.output.resolve(), account, args.seed_url, args.earliest_date)
    except WeReadRelayError as error:
        print(f"初始化失败：{error}")
        return 1

    print(f"公众号初始化成功：{account.name or args.name}")
    print(f"非敏感配置已保存至：{args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
