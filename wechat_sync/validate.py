"""Validate every configured account index before publishing the archive."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "accounts.json"
INDEX_ROOT = Path(__file__).resolve().parent / "indexes"
CONTENT_ROOT = PROJECT_ROOT / "src" / "content" / "articles"
PUBLIC_ROOT = PROJECT_ROOT / "public"
IMAGE_SOURCE_RE = re.compile(
    r"<(?:img|image)\b[^>]*(?:src|href)=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
CSS_URL_RE = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", re.IGNORECASE)
MOJIBAKE_RE = re.compile(r"(?:’╝|ŃĆ|[ÕĶń][^\s<])")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _local_public_path(value: str) -> Optional[Path]:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None
    return PUBLIC_ROOT / parsed.path.lstrip("/")


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON 根节点必须是对象")
    return payload


def validate() -> list[str]:
    errors: list[str] = []
    try:
        config = _load_object(CONFIG_PATH)
    except (OSError, ValueError) as error:
        return [f"无法读取公众号配置: {error}"]

    raw_accounts = config.get("accounts")
    if not isinstance(raw_accounts, list) or not raw_accounts:
        return ["accounts.json 的 accounts 必须是非空数组"]

    configured_accounts: list[tuple[str, str]] = []
    for position, account in enumerate(raw_accounts):
        if not isinstance(account, dict):
            errors.append(f"accounts[{position}] 必须是对象")
            continue
        slug = str(account.get("slug", "")).strip()
        name = str(account.get("name", "")).strip()
        if not slug or not name:
            errors.append(f"accounts[{position}] 缺少 slug 或 name")
            continue
        configured_accounts.append((slug, name))

    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    seen_paths: set[Path] = set()

    for slug, source_name in configured_accounts:
        index_path = INDEX_ROOT / f"{slug}.json"
        try:
            index = _load_object(index_path)
        except (OSError, ValueError) as error:
            errors.append(f"无法读取 {index_path.relative_to(PROJECT_ROOT)}: {error}")
            continue

        entries = index.get("articles")
        pending = index.get("pendingArticles", [])
        if not isinstance(entries, list):
            errors.append(f"{index_path.name} 的 articles 必须是数组")
            continue
        if not isinstance(pending, list):
            errors.append(f"{index_path.name} 的 pendingArticles 必须是数组")
            pending = []

        account = index.get("account")
        if isinstance(account, dict):
            indexed_name = str(account.get("name", "")).strip()
            indexed_slug = str(account.get("slug", slug)).strip()
            if indexed_name and indexed_name != source_name:
                errors.append(f"{index_path.name} 的公众号名称与 accounts.json 不一致")
            if indexed_slug != slug:
                errors.append(f"{index_path.name} 的公众号 slug 与文件名不一致")

        account_ids: set[str] = set()
        for position, entry in enumerate(entries):
            label = f"{index_path.name}:articles[{position}]"
            if not isinstance(entry, dict):
                errors.append(f"{label} 必须是对象")
                continue

            article_id = str(entry.get("articleId", "")).strip()
            source_url = str(entry.get("sourceUrl", "")).strip()
            markdown_value = str(entry.get("markdownPath", "")).strip()
            if not article_id or article_id in seen_ids:
                errors.append(f"{label} 的 articleId 缺失或跨索引重复: {article_id or '<empty>'}")
            if not source_url or source_url in seen_urls:
                errors.append(f"{label} 的 sourceUrl 缺失或跨索引重复")
            seen_ids.add(article_id)
            account_ids.add(article_id)
            seen_urls.add(source_url)

            markdown_path = PROJECT_ROOT / markdown_value
            if not markdown_value or not _inside(markdown_path, CONTENT_ROOT):
                errors.append(f"{label} 的 markdownPath 超出文章目录: {markdown_value}")
                continue
            if markdown_path in seen_paths:
                errors.append(f"{label} 的 markdownPath 重复: {markdown_value}")
            seen_paths.add(markdown_path)
            if not markdown_path.is_file():
                errors.append(f"{label} 的 Markdown 不存在: {markdown_value}")
                continue

            markdown = markdown_path.read_text(encoding="utf-8")
            if f'articleId: "{article_id}"' not in markdown:
                errors.append(f"{markdown_value} 的 articleId 与索引不一致")
            expected_source = json.dumps(source_name, ensure_ascii=False)
            if f"source: {expected_source}" not in markdown:
                errors.append(f"{markdown_value} 的 source 与账号索引不一致")
            if '<div class="wechat-article">' not in markdown:
                errors.append(f"{markdown_value} 缺少微信正文容器")
            if len(MOJIBAKE_RE.findall(markdown)) >= 8:
                errors.append(f"{markdown_value} 疑似包含字符编码乱码")

            cover = str(entry.get("cover", "")).strip()
            if cover:
                cover_path = _local_public_path(cover)
                if cover_path is None or not cover_path.is_file():
                    errors.append(f"{markdown_value} 的本地封面不存在: {cover}")

            image_sources = IMAGE_SOURCE_RE.findall(markdown) + CSS_URL_RE.findall(markdown)
            for image_source in image_sources:
                if image_source.startswith("data:"):
                    continue
                image_path = _local_public_path(image_source)
                if image_path is None:
                    errors.append(f"{markdown_value} 仍包含远程正文图片: {image_source}")
                elif not image_path.is_file():
                    errors.append(f"{markdown_value} 引用的正文图片不存在: {image_source}")

        for position, item in enumerate(pending):
            if not isinstance(item, dict) or not str(item.get("articleId", "")).strip():
                errors.append(f"{index_path.name}:pendingArticles[{position}] 结构无效")
                continue
            if str(item["articleId"]).strip() in account_ids:
                errors.append(f"{index_path.name}:pendingArticles[{position}] 已存在于完成索引")

    indexed_files = set(CONTENT_ROOT.glob("*.md"))
    for orphan in sorted(indexed_files - seen_paths):
        errors.append(f"文章未进入任何账号索引: {orphan.relative_to(PROJECT_ROOT)}")

    configured_index_names = {f"{slug}.json" for slug, _ in configured_accounts}
    for index_path in INDEX_ROOT.glob("*.json"):
        if index_path.name not in configured_index_names:
            errors.append(f"存在未配置的公众号索引: {index_path.relative_to(PROJECT_ROOT)}")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("归档完整性检查失败:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("双公众号归档完整性检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
