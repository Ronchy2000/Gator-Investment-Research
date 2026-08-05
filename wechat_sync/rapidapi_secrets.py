"""Store and upload a RapidAPI key pool without printing key values."""

from __future__ import annotations

import argparse
import getpass
import json
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KEY_FILE = PROJECT_ROOT / "data" / "wechat" / "rapidapi-keys.json"
SECRET_NAME = "RAPIDAPI_KEYS"


def _load_keys(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SystemExit(f"无法读取本地 RapidAPI Key 池: {error}") from error
    if isinstance(payload, dict):
        payload = payload.get("keys")
    if not isinstance(payload, list):
        raise SystemExit("本地 RapidAPI Key 池必须是 JSON 数组或包含 keys 的对象")
    keys: list[str] = []
    for value in payload:
        key = str(value).strip()
        if key and key not in keys:
            keys.append(key)
    return keys


def _save_keys(path: Path, keys: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps({"version": 1, "keys": keys}, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    temporary_path.replace(path)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _secret_value(keys: list[str]) -> str:
    if not keys:
        raise SystemExit("本地 Key 池为空，请先使用 --add")
    return json.dumps(keys, separators=(",", ":"))


def _add(path: Path) -> None:
    key = getpass.getpass("RapidAPI Key（输入不回显）: ").strip()
    if not key:
        raise SystemExit("Key 不能为空")
    keys = _load_keys(path)
    if key not in keys:
        keys.append(key)
        _save_keys(path, keys)
    print(f"本地 Key 池现有 {len(keys)} 个 Key；文件已被 Git 忽略。")


def _remove(path: Path) -> None:
    key = getpass.getpass("要移除的 RapidAPI Key（输入不回显）: ").strip()
    keys = _load_keys(path)
    filtered = [item for item in keys if item != key]
    if len(filtered) == len(keys):
        print("本地 Key 池中没有该 Key，未修改文件。")
        return
    _save_keys(path, filtered)
    print(f"Key 已移除；本地 Key 池剩余 {len(filtered)} 个 Key。")


def _copy(value: str) -> None:
    pbcopy = shutil.which("pbcopy")
    if not pbcopy:
        raise SystemExit("当前系统没有 pbcopy，请使用 --upload 或手动配置 Secret")
    subprocess.run([pbcopy], input=value, text=True, check=True)
    print(f"已将 {SECRET_NAME} 的值复制到剪贴板，终端未显示 Key。")


def _upload(value: str, repository: Optional[str]) -> None:
    gh = shutil.which("gh")
    if not gh:
        raise SystemExit(
            "未安装 GitHub CLI；请使用 --copy 后在 GitHub 网页创建 RAPIDAPI_KEYS。"
        )
    command = [gh, "secret", "set", SECRET_NAME]
    if repository:
        command.extend(["--repo", repository])
    subprocess.run(command, input=value, text=True, check=True)
    print(f"已上传 GitHub Repository Secret：{SECRET_NAME}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="安全维护 RapidAPI Key 池")
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--repo", help="可选，OWNER/REPOSITORY")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--add", action="store_true", help="隐藏输入并追加一个 Key")
    actions.add_argument("--remove", action="store_true", help="隐藏输入并移除一个 Key")
    actions.add_argument("--copy", action="store_true", help="复制 RAPIDAPI_KEYS")
    actions.add_argument("--upload", action="store_true", help="通过 gh 上传 Secret")
    actions.add_argument("--count", action="store_true", help="只显示本地 Key 数量")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    path = args.key_file.expanduser().resolve()
    if args.add:
        _add(path)
        return 0
    if args.remove:
        _remove(path)
        return 0

    keys = _load_keys(path)
    if args.count:
        print(f"本地 Key 池包含 {len(keys)} 个 Key。")
        return 0

    value = _secret_value(keys)
    if args.copy:
        _copy(value)
    else:
        _upload(value, args.repo)
    print(f"上传内容包含 {len(keys)} 个 Key。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
