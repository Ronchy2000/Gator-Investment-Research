"""Validate the committed article archive before publishing it."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = Path(__file__).resolve().parent / "index.json"
CONTENT_ROOT = PROJECT_ROOT / "src" / "content" / "articles"
PUBLIC_ROOT = PROJECT_ROOT / "public"
IMAGE_SOURCE_RE = re.compile(
    r"<(?:img|image)\b[^>]*(?:src|href)=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
CSS_URL_RE = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", re.IGNORECASE)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _local_public_path(value: str) -> Path | None:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None
    return PUBLIC_ROOT / parsed.path.lstrip("/")


def validate() -> list[str]:
    errors: list[str] = []
    try:
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"无法读取同步索引: {error}"]

    entries = index.get("articles")
    pending = index.get("pendingArticles", [])
    if not isinstance(entries, list):
        return ["index.json 的 articles 必须是数组"]
    if not isinstance(pending, list):
        errors.append("index.json 的 pendingArticles 必须是数组")

    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    seen_paths: set[Path] = set()

    for position, entry in enumerate(entries, start=1):
        label = f"articles[{position - 1}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} 必须是对象")
            continue

        article_id = str(entry.get("articleId", "")).strip()
        source_url = str(entry.get("sourceUrl", "")).strip()
        markdown_value = str(entry.get("markdownPath", "")).strip()
        if not article_id or article_id in seen_ids:
            errors.append(f"{label} 的 articleId 缺失或重复: {article_id or '<empty>'}")
        if not source_url or source_url in seen_urls:
            errors.append(f"{label} 的 sourceUrl 缺失或重复")
        seen_ids.add(article_id)
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
        if "<div class=\"wechat-article\">" not in markdown:
            errors.append(f"{markdown_value} 缺少微信正文容器")

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

    indexed_files = set(CONTENT_ROOT.glob("*.md"))
    for orphan in sorted(indexed_files - seen_paths):
        errors.append(f"文章未进入同步索引: {orphan.relative_to(PROJECT_ROOT)}")

    for position, item in enumerate(pending if isinstance(pending, list) else []):
        if not isinstance(item, dict) or not str(item.get("articleId", "")).strip():
            errors.append(f"pendingArticles[{position}] 结构无效")
            continue
        if str(item["articleId"]).strip() in seen_ids:
            errors.append(f"pendingArticles[{position}] 已存在于完成索引")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("归档完整性检查失败:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("归档完整性检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
