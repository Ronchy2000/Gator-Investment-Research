"""Upload or copy local WeRead credentials without printing their values."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CREDENTIAL_FILE = PROJECT_ROOT / "data" / "wechat" / "credentials.json"
SECRET_NAMES = {
    "vid": "WEREAD_VID",
    "token": "WEREAD_TOKEN",
}


def _load(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SystemExit(f"无法读取本地凭据: {error}") from error
    values = {key: str(payload.get(key, "")).strip() for key in SECRET_NAMES}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise SystemExit(f"本地凭据缺少字段: {', '.join(missing)}")
    return values


def _copy(value: str, field: str) -> None:
    pbcopy = shutil.which("pbcopy")
    if not pbcopy:
        raise SystemExit("当前系统没有 pbcopy，请使用 GitHub CLI 上传方式")
    subprocess.run([pbcopy], input=value, text=True, check=True)
    print(f"已将 {SECRET_NAMES[field]} 复制到剪贴板，未在终端显示凭据内容。")


def _upload(values: dict[str, str], repository: Optional[str]) -> None:
    gh = shutil.which("gh")
    if not gh:
        raise SystemExit(
            "未安装 GitHub CLI。可先运行 brew install gh && gh auth login，"
            "或使用 --copy vid/token 逐项复制到 GitHub 网页。"
        )
    for field, secret_name in SECRET_NAMES.items():
        command = [gh, "secret", "set", secret_name]
        if repository:
            command.extend(["--repo", repository])
        subprocess.run(command, input=values[field], text=True, check=True)
        print(f"已上传 {secret_name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="安全上传 GitHub Actions 微信读书凭据")
    parser.add_argument(
        "--credential-file",
        type=Path,
        default=DEFAULT_CREDENTIAL_FILE,
    )
    parser.add_argument("--repo", help="可选，OWNER/REPOSITORY")
    parser.add_argument("--copy", choices=tuple(SECRET_NAMES), help="仅复制指定字段")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    values = _load(args.credential_file.expanduser().resolve())
    if args.copy:
        _copy(values[args.copy], args.copy)
    else:
        _upload(values, args.repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
