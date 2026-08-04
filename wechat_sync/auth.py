#!/usr/bin/env python3
"""Obtain and store a WeRead relay credential through a one-time QR login.

Protocol adapted from x554960766/wechat-mp-tools v1.7.0 at commit
d8d83225f12d3baec20f943498716883aae8fe8a. See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import time
import webbrowser
from pathlib import Path

import qrcode
import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "wechat"
DEFAULT_PLATFORM_URL = "https://weread.111965.xyz"


def _read_existing_credentials(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"无法读取现有凭据，已停止以免覆盖: {error}") from error

    if not isinstance(payload, dict):
        raise RuntimeError("现有凭据不是 JSON 对象，已停止以免覆盖")
    raw_accounts = payload.get("accounts")
    if raw_accounts is None:
        raw_accounts = [payload]
    if not isinstance(raw_accounts, list) or any(
        not isinstance(item, dict) for item in raw_accounts
    ):
        raise RuntimeError("现有账号池格式无效，已停止以免覆盖")
    return [dict(item) for item in raw_accounts]


def _write_credentials(
    path: Path,
    credential: dict[str, object],
    reset_pool: bool = False,
) -> int:
    accounts = [] if reset_pool else _read_existing_credentials(path)
    credential_key = (
        str(credential.get("vid", "")).strip(),
        str(credential.get("platform_url", "")).strip().rstrip("/"),
    )
    replaced = False
    for position, existing in enumerate(accounts):
        existing_key = (
            str(existing.get("vid", "")).strip(),
            str(existing.get("platform_url", "")).strip().rstrip("/"),
        )
        if existing_key == credential_key:
            accounts[position] = credential
            replaced = True
            break
    if not replaced:
        accounts.append(credential)

    payload = {"version": 2, "accounts": accounts}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    temporary_path.replace(path)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return len(accounts)


def _create_qr_image(scan_url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = qrcode.make(scan_url)
    image.save(path)


def login(
    *,
    platform_url: str,
    credential_path: Path,
    reset_pool: bool = False,
    timeout_seconds: int = 300,
) -> bool:
    platform_url = platform_url.rstrip("/")
    print("正在获取微信读书扫码登录二维码...")

    no_cache_headers = {
        "Cache-Control": "no-cache, no-store, max-age=0",
        "Pragma": "no-cache",
    }
    response = requests.get(
        f"{platform_url}/api/v2/login/platform",
        params={"_": time.time_ns()},
        headers=no_cache_headers,
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    login_id = payload.get("uuid")
    scan_url = payload.get("scanUrl")
    if not login_id or not scan_url:
        raise RuntimeError("中转服务未返回有效的扫码凭证")

    qr_path = credential_path.parent / "login-qrcode.png"
    _create_qr_image(str(scan_url), qr_path)

    print(f"二维码已保存至：{qr_path}")
    print("请使用手机微信扫码并确认登录。")
    try:
        webbrowser.open(qr_path.as_uri())
    except Exception:
        pass

    started_at = time.monotonic()
    try:
        while time.monotonic() - started_at < timeout_seconds:
            time.sleep(3)
            poll_response = requests.get(
                f"{platform_url}/api/v2/login/platform/{login_id}",
                params={"_": time.time_ns()},
                headers=no_cache_headers,
                timeout=30,
            )
            poll_response.raise_for_status()
            login_result = poll_response.json()
            vid = login_result.get("vid")
            token = login_result.get("token")
            if vid and token:
                credential = {
                    "vid": str(vid),
                    "token": str(token),
                    "nickname": login_result.get("username") or f"WeRead_{vid}",
                    "save_time": int(time.time()),
                    "platform_url": platform_url,
                }
                account_count = _write_credentials(
                    credential_path,
                    credential,
                    reset_pool=reset_pool,
                )
                print(f"登录成功，凭证已安全保存至：{credential_path}")
                print(f"当前本地账号池共 {account_count} 个账号，按保存顺序调用。")
                print("请勿提交 data/ 目录或在终端中打印 token。")
                return True

            message = login_result.get("message")
            if message:
                print(f"等待扫码：{message}")
    finally:
        qr_path.unlink(missing_ok=True)

    print("扫码登录已超时，请重新运行命令。")
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地微信读书扫码登录")
    parser.add_argument(
        "--platform-url",
        default=os.environ.get("WEREAD_PLATFORM_URL", DEFAULT_PLATFORM_URL),
        help="微信读书中转服务地址",
    )
    parser.add_argument(
        "--credential-file",
        type=Path,
        default=DEFAULT_DATA_DIR / "credentials.json",
        help="本地凭证保存路径（必须位于 Git 忽略目录）",
    )
    parser.add_argument(
        "--reset-pool",
        action="store_true",
        help="清空现有账号池后仅保存本次扫码账号（默认追加或原位更新）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    credential_path = args.credential_file.expanduser().resolve()
    ignored_data_root = (PROJECT_ROOT / "data").resolve()
    if ignored_data_root not in credential_path.parents:
        raise SystemExit("凭证文件必须保存在项目 data/ 目录内，避免被 Git 提交")

    try:
        return 0 if login(
            platform_url=args.platform_url,
            credential_path=credential_path,
            reset_pool=args.reset_pool,
        ) else 1
    except (requests.RequestException, ValueError, RuntimeError) as error:
        print(f"登录失败：{error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
