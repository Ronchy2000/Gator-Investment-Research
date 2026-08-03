"""Resolve a seed article and upsert its non-secret account configuration."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from wechat_sync.client import WeChatAccount, WeReadClient, WeReadRelayError, load_credentials


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ACCOUNT_FILE = PROJECT_ROOT / "wechat_sync" / "accounts.json"
DEFAULT_INDEX_ROOT = PROJECT_ROOT / "wechat_sync" / "indexes"
DEFAULT_ACCOUNT_SLUG = "huode-xinxicha"
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


def _save_account(
    path: Path,
    slug: str,
    account: WeChatAccount,
    seed_url: str,
    earliest_date: str,
) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        payload = {"version": 1, "accounts": []}
    if not isinstance(payload, dict) or not isinstance(payload.get("accounts"), list):
        raise WeReadRelayError("accounts.json 结构无效")

    configured_account = {
        "slug": slug,
        "name": account.name or DEFAULT_ACCOUNT_NAME,
        "mp_id": account.mp_id,
        "intro": account.intro,
        "seed_article_url": seed_url,
        "earliest_date": earliest_date,
    }
    accounts = [
        item
        for item in payload["accounts"]
        if not isinstance(item, dict) or str(item.get("slug", "")) != slug
    ]
    accounts.append(configured_account)
    payload = {"version": 1, "accounts": accounts}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="新增或更新微信公众号同步配置")
    parser.add_argument("--slug", default=DEFAULT_ACCOUNT_SLUG)
    parser.add_argument("--name", default=DEFAULT_ACCOUNT_NAME)
    parser.add_argument("--seed-url", default=DEFAULT_SEED_URL)
    parser.add_argument("--earliest-date", default=DEFAULT_EARLIEST_DATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_ACCOUNT_FILE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.slug):
        raise SystemExit("slug 只能包含小写字母、数字和单个连字符")
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
        _save_account(
            args.output.resolve(),
            args.slug,
            account,
            args.seed_url,
            args.earliest_date,
        )
        index_path = DEFAULT_INDEX_ROOT / f"{args.slug}.json"
        if not index_path.exists():
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(
                json.dumps(
                    {
                        "version": 3,
                        "account": {
                            "slug": args.slug,
                            "mpId": account.mp_id,
                            "name": account.name or args.name,
                        },
                        "earliestDate": args.earliest_date,
                        "updatedAt": datetime.now().astimezone().isoformat(),
                        "backfillComplete": False,
                        "backfillNextPage": 1,
                        "pendingArticles": [],
                        "articles": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
    except (OSError, ValueError, WeReadRelayError) as error:
        print(f"初始化失败：{error}")
        return 1

    print(f"公众号初始化成功：{account.name or args.name}")
    print(f"非敏感配置已更新：{args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
