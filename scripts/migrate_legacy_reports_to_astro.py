"""Migrate the unique legacy Docsify reports into the Astro content collection."""

from __future__ import annotations

import json
import re
from html import escape
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Match
from urllib.parse import urlparse

import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = PROJECT_ROOT / "docs" / "all-reports"
DESTINATION_ROOT = PROJECT_ROOT / "src" / "content" / "reports"
ASSET_ROOT = PROJECT_ROOT / "public" / "report-assets"
LEGACY_ROUTES_PATH = PROJECT_ROOT / "docs" / "legacy-routes.json"
PUBLIC_ROUTES_PATH = PROJECT_ROOT / "public" / "legacy-routes.json"
EXPECTED_REPORT_COUNT = 913

TITLE_PATTERN = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
METADATA_PATTERN = re.compile(r"^- (分类|日期|文章ID|来源):\s*(.*?)\s*$", re.MULTILINE)
IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\((https?://[^)]+)\)")
REPORT_ID_PATTERN = re.compile(r"-(\d+)$")
UNAVAILABLE_IMAGE_HOSTS: set[str] = set()


@dataclass(frozen=True)
class LegacyReport:
    title: str
    category: str
    published_at: datetime
    report_id: int
    source_url: str
    legacy_stem: str
    body: str


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def normalize_category(value: str) -> str:
    if value in {"宏观分析", "行业分析"}:
        return value
    if value == "全部研报":
        return "其他"
    raise ValueError(f"无法识别的历史研报分类: {value}")


def parse_report(path: Path) -> LegacyReport:
    content = path.read_text(encoding="utf-8")
    title_match = TITLE_PATTERN.search(content)
    metadata = dict(METADATA_PATTERN.findall(content))
    separator = content.find("\n---\n")
    required_fields = {"分类", "日期", "文章ID", "来源"}
    missing_fields = required_fields.difference(metadata)
    if title_match is None or separator < 0 or missing_fields:
        raise ValueError(f"历史研报格式不完整: {path}，缺少 {sorted(missing_fields)}")

    published_at = datetime.strptime(metadata["日期"], "%Y.%m.%d")
    report_id = int(metadata["文章ID"])
    filename_id = REPORT_ID_PATTERN.search(path.stem)
    if filename_id is None or int(filename_id.group(1)) != report_id:
        raise ValueError(f"文件名和文章 ID 不一致: {path}")

    body = content[separator + len("\n---\n") :].strip()
    if not body:
        raise ValueError(f"历史研报正文为空: {path}")
    return LegacyReport(
        title=title_match.group(1).strip(),
        category=normalize_category(metadata["分类"].strip()),
        published_at=published_at,
        report_id=report_id,
        source_url=metadata["来源"].strip(),
        legacy_stem=path.stem,
        body=body,
    )


def plain_text(markdown: str) -> str:
    value = IMAGE_PATTERN.sub(" ", markdown)
    value = re.sub(r"```.*?```", " ", value, flags=re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"^[#>*+\-\d.\s]+", "", value, flags=re.MULTILINE)
    value = re.sub(r"[*_~`]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def description_for(report: LegacyReport) -> str:
    return plain_text(report.body)[:180]


def download_image(session: requests.Session, url: str, destination: Path) -> None:
    host = urlparse(url).hostname or ""
    if host in UNAVAILABLE_IMAGE_HOSTS:
        raise RuntimeError(f"图片源站此前已确认不可用: {host}")
    candidates = [url]
    if url.startswith("http://"):
        candidates.insert(0, "https://" + url.removeprefix("http://"))

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            response = session.get(candidate, timeout=45)
            response.raise_for_status()
            if not response.content:
                raise ValueError("图片内容为空")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(response.content)
            return
        except (requests.RequestException, ValueError) as error:
            last_error = error
    UNAVAILABLE_IMAGE_HOSTS.add(host)
    raise RuntimeError(f"历史研报图片下载失败: {url}: {last_error}")


def write_missing_image_placeholder(destination: Path, report_id: int, image_number: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    label = escape(f"REPORT {report_id} / IMAGE {image_number}")
    destination.write_text(
        "\n".join(
            [
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 675" role="img" aria-label="历史图片暂不可用">',
                '<rect width="1200" height="675" fill="#eceae2"/>',
                '<path d="M90 92h1020M90 583h1020" stroke="#1b1d1a" stroke-width="3"/>',
                f'<text x="90" y="150" fill="#0d7d58" font-family="monospace" font-size="24">{label}</text>',
                '<text x="90" y="335" fill="#1b1d1a" font-family="serif" font-size="60">历史图片暂不可用</text>',
                '<text x="90" y="405" fill="#676b63" font-family="sans-serif" font-size="28">原站图片资源已失效，点击占位图可尝试访问原地址。</text>',
                "</svg>",
                "",
            ]
        ),
        encoding="utf-8",
    )


def localize_images(session: requests.Session, report: LegacyReport) -> str:
    image_number = 0

    def replace_image(match: Match[str]) -> str:
        nonlocal image_number
        image_number += 1
        alt_text, url = match.groups()
        suffix = Path(url.split("?", 1)[0]).suffix.lower()
        if suffix not in {".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}:
            suffix = ".bin"
        filename = f"image-{image_number:03d}{suffix}"
        destination = ASSET_ROOT / str(report.report_id) / filename
        try:
            download_image(session, url, destination)
        except RuntimeError as error:
            filename = f"missing-{image_number:03d}.svg"
            destination = ASSET_ROOT / str(report.report_id) / filename
            write_missing_image_placeholder(destination, report.report_id, image_number)
            print(f"警告: {error}")
            local_image = f"/report-assets/{report.report_id}/{filename}"
            return f"[![历史图片暂不可用]({local_image})]({url})"
        return f"![{alt_text}](/report-assets/{report.report_id}/{filename})"

    return IMAGE_PATTERN.sub(replace_image, report.body)


def render_report(report: LegacyReport, body: str) -> str:
    published_at = report.published_at.strftime("%Y-%m-%dT00:00:00+08:00")
    frontmatter = [
        "---",
        f"title: {yaml_string(report.title)}",
        f"publishedAt: {yaml_string(published_at)}",
        f"source: {yaml_string('历史公开研报')}",
        f"sourceUrl: {yaml_string(report.source_url)}",
        f"description: {yaml_string(description_for(report))}",
        f"category: {yaml_string(report.category)}",
        f"reportId: {report.report_id}",
        f"legacyStem: {yaml_string(report.legacy_stem)}",
        "---",
        "",
    ]
    return "\n".join(frontmatter) + body.strip() + "\n"


def migrate_reports() -> list[LegacyReport]:
    source_paths = sorted(SOURCE_ROOT.glob("*.md"))
    source_paths = [path for path in source_paths if path.name != "README.md"]
    if len(source_paths) != EXPECTED_REPORT_COUNT:
        raise RuntimeError(
            f"历史研报数量异常，预期 {EXPECTED_REPORT_COUNT}，实际 {len(source_paths)}"
        )

    reports = [parse_report(path) for path in source_paths]
    report_ids = {report.report_id for report in reports}
    if len(report_ids) != EXPECTED_REPORT_COUNT:
        raise RuntimeError("历史研报存在重复文章 ID")

    DESTINATION_ROOT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
        }
    )

    for report in reports:
        body = localize_images(session, report)
        destination = DESTINATION_ROOT / f"{report.report_id}.md"
        temporary = destination.with_suffix(".md.tmp")
        temporary.write_text(render_report(report, body), encoding="utf-8")
        temporary.replace(destination)
    return reports


def migrate_legacy_routes() -> int:
    source_routes = json.loads(LEGACY_ROUTES_PATH.read_text(encoding="utf-8"))
    destination_routes: dict[str, str] = {}
    for legacy_path, current_path in source_routes.items():
        match = REPORT_ID_PATTERN.search(str(current_path).removesuffix(".md"))
        if match:
            destination_routes[str(legacy_path)] = f"/reports/{int(match.group(1))}/"
    PUBLIC_ROUTES_PATH.write_text(
        json.dumps(destination_routes, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return len(destination_routes)


def main() -> int:
    reports = migrate_reports()
    route_count = migrate_legacy_routes()
    categories: dict[str, int] = {}
    for report in reports:
        categories[report.category] = categories.get(report.category, 0) + 1
    print(f"已迁移 {len(reports)} 篇唯一历史研报")
    print(f"分类统计: {json.dumps(categories, ensure_ascii=False, sort_keys=True)}")
    print(f"已转换 {route_count} 条旧 Docsify 路由")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
