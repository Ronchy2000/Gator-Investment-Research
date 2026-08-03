"""Upload or copy the local WeRead account pool without printing secrets."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CREDENTIAL_FILE = PROJECT_ROOT / "data" / "wechat" / "credentials.json"
PRIMARY_SECRET = "WEREAD_ACCOUNTS"
LEGACY_SECRETS = ("WEREAD_VID", "WEREAD_TOKEN")
SECRET_NAMES = (PRIMARY_SECRET,) + LEGACY_SECRETS
COPY_ALIASES = {
    "accounts": PRIMARY_SECRET,
    "vid": "WEREAD_VID",
    "token": "WEREAD_TOKEN",
}


def _account_records(payload: Any) -> list[dict[str, str]]:
    if not isinstance(payload, dict):
        raise SystemExit("本地凭据必须是 JSON 对象")
    raw_accounts = payload.get("accounts")
    if not isinstance(raw_accounts, list):
        raw_accounts = [payload]
    default_platform_url = str(payload.get("platform_url", "")).strip()

    accounts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for position, item in enumerate(raw_accounts, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"本地账号池第 {position} 项格式无效")
        vid = str(item.get("vid", "")).strip()
        token = str(item.get("token", "")).strip()
        platform_url = str(item.get("platform_url", "")).strip()
        platform_url = platform_url or default_platform_url
        if not vid or not token:
            raise SystemExit(f"本地账号池第 {position} 项缺少 vid 或 token")
        key = (vid, platform_url.rstrip("/"))
        if key in seen:
            continue
        seen.add(key)
        record = {"vid": vid, "token": token}
        if platform_url:
            record["platform_url"] = platform_url
        accounts.append(record)

    if not accounts:
        raise SystemExit("本地账号池中没有可上传账号")
    return accounts


def _load(path: Path) -> tuple[dict[str, str], int]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SystemExit(f"无法读取本地凭据: {error}") from error
    accounts = _account_records(payload)
    pool_value = json.dumps(
        {"version": 2, "accounts": accounts},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    values = {
        PRIMARY_SECRET: pool_value,
        "WEREAD_VID": accounts[0]["vid"],
        "WEREAD_TOKEN": accounts[0]["token"],
    }
    return values, len(accounts)


def _normalize_secret_name(value: str) -> str:
    candidate = value.strip()
    if candidate in SECRET_NAMES:
        return candidate
    alias = COPY_ALIASES.get(candidate.lower())
    if alias:
        return alias
    expected = "、".join(SECRET_NAMES)
    raise argparse.ArgumentTypeError(f"Secret 名称必须是 {expected}")


def _copy(value: str, secret_name: str) -> None:
    pbcopy = shutil.which("pbcopy")
    if not pbcopy:
        raise SystemExit("当前系统没有 pbcopy，请使用 GitHub CLI 上传方式")
    subprocess.run([pbcopy], input=value, text=True, check=True)
    print(f"已将 {secret_name} 复制到剪贴板，未在终端显示凭据内容。")
    print(f"GitHub Repository Secret 的 Name 必须完整填写为：{secret_name}")


def _upload(value: str, repository: Optional[str]) -> None:
    gh = shutil.which("gh")
    if not gh:
        raise SystemExit(
            "未安装 GitHub CLI。可先运行 brew install gh && gh auth login，"
            "或使用 --copy WEREAD_ACCOUNTS 复制到 GitHub 网页。"
        )
    command = [gh, "secret", "set", PRIMARY_SECRET]
    if repository:
        command.extend(["--repo", repository])
    subprocess.run(command, input=value, text=True, check=True)
    print(f"已上传 {PRIMARY_SECRET}，旧版两项 Secret 可保留作为兼容后备。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="安全上传 GitHub Actions 微信读书账号池")
    parser.add_argument(
        "--credential-file",
        type=Path,
        default=DEFAULT_CREDENTIAL_FILE,
    )
    parser.add_argument("--repo", help="可选，OWNER/REPOSITORY")
    parser.add_argument(
        "--copy",
        type=_normalize_secret_name,
        metavar="WEREAD_ACCOUNTS",
        help="复制账号池 Secret；旧版 WEREAD_VID/WEREAD_TOKEN 仍可单独复制",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    values, account_count = _load(args.credential_file.expanduser().resolve())
    if args.copy:
        _copy(values[args.copy], args.copy)
    else:
        _upload(values[PRIMARY_SECRET], args.repo)
    print(f"账号池包含 {account_count} 个账号。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
