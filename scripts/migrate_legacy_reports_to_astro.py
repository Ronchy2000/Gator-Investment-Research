"""Migrate the unique legacy Docsify reports into the Astro content collection."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
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
SUMMARY_SECTION_KEYWORDS = (
    "核心摘要",
    "核心观点",
    "核心结论",
    "投资要点",
    "投资亮点",
    "主要观点",
    "本周观点",
    "投资建议",
    "摘要",
    "结论",
    "简析",
)
SECTION_LABELS = SUMMARY_SECTION_KEYWORDS + (
    "风险提示",
    "事件概述",
    "事件",
    "行业观点",
    "行情回顾",
    "市场回顾",
    "投资分析",
    "行业动态",
    "公司动态",
    "数据跟踪",
    "相关标的",
)
SUMMARY_SIGNAL_WORDS = (
    "核心",
    "预计",
    "有望",
    "看好",
    "建议",
    "关注",
    "驱动",
    "受益",
    "增长",
    "改善",
    "回暖",
    "拐点",
    "机会",
    "趋势",
    "壁垒",
)
COMPLETE_SENTENCE_ENDINGS = ("。", "！", "？", "!", "?", "；", ";")


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
    value = re.sub(r"^\s{0,3}#{1,6}\s+", "", value, flags=re.MULTILINE)
    value = re.sub(r"^\s*>\s?", "", value, flags=re.MULTILINE)
    value = re.sub(r"^\s*[-+*]\s+", "", value, flags=re.MULTILINE)
    value = re.sub(r"^\s*\d+[.、]\s+", "", value, flags=re.MULTILINE)
    value = re.sub(r"[*_~`]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def split_leading_blurb(markdown: str) -> tuple[str, str]:
    """Remove the legacy template quote while preserving its text for summarization."""
    lines = markdown.strip().splitlines()
    blurb_lines: list[str] = []
    index = 0
    while index < len(lines) and lines[index].lstrip().startswith(">"):
        blurb_lines.append(lines[index].lstrip().removeprefix(">").strip())
        index += 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    return plain_text(" ".join(blurb_lines)), "\n".join(lines[index:]).strip()


def expand_collapsed_table(line: str) -> str:
    """Restore tables whose row newlines were lost by the legacy converter."""
    if "||" not in line or "|" not in line:
        return line

    first_row, *remaining_rows = line.split("||")
    title = ""
    if not first_row.lstrip().startswith("|"):
        prefix, separator, cells = first_row.partition("|")
        if not separator:
            return line
        title = re.sub(r"^0{2,}\d+[.]\s*", "", prefix).strip().rstrip("：:")
        first_row = f"| {cells.strip()}"

    rows = [first_row, *remaining_rows]
    rendered_rows = []
    trailing_note = ""
    for row in rows:
        value = row.strip()
        if not value:
            continue
        note_match = re.match(r"^(.*?\|)\s*([（(]注.+)$", value)
        if note_match:
            value, trailing_note = note_match.groups()
        if not value.startswith("|"):
            value = "| " + value
        if not value.endswith("|"):
            value += " |"
        rendered_rows.append(value)

    parts = []
    if title:
        parts.append(title)
    if rendered_rows:
        parts.append("\n".join(rendered_rows))
    if trailing_note:
        parts.append(trailing_note)
    return "\n\n".join(parts)


def normalize_body(markdown: str) -> tuple[str, str]:
    blurb, body = split_leading_blurb(markdown)
    normalized_lines: list[str] = []
    labels = "|".join(re.escape(label) for label in SECTION_LABELS)
    label_pattern = re.compile(
        rf"^(?P<prefix>[一二三四五六七八九十]+[、.]\s*)?"
        rf"(?P<label>{labels})(?P<suffix>[：:]?)\s*(?P<content>.*)$"
    )

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if re.fullmatch(r"\s*\d+[.]\s*", line):
            continue
        line = re.sub(r"^\s*0{2,}\d+[.]\s*", "- ", line)
        line = re.sub(r"^\s*[·•]\s+", "- ", line)
        line = re.sub(r"^(#{2,6})\s+\*\*(.+?)\*\*\s*$", r"\1 \2", line)
        if re.fullmatch(r"\s*#{2,6}\s*", line):
            continue
        line = expand_collapsed_table(line)

        if "\n" not in line and not line.lstrip().startswith(("#", "-", "|")):
            label_match = label_pattern.match(line.strip())
            if label_match and (label_match.group("suffix") or not label_match.group("content")):
                heading = f"{label_match.group('prefix') or ''}{label_match.group('label')}"
                content = label_match.group("content").strip()
                normalized_lines.append(f"## {heading}")
                if content:
                    normalized_lines.extend(["", content])
                continue
        normalized_lines.append(line)

    normalized = "\n".join(normalized_lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    return blurb, normalized


def improve_body_structure(markdown: str) -> str:
    lines: list[str] = []
    for line in markdown.splitlines():
        label_match = re.fullmatch(r"\s*\*\*(.{2,80}?)\*\*[：:]?\s*", line)
        if label_match and not label_match.group(1).endswith(("。", "！", "？", "!", "?")):
            lines.append(f"#### {label_match.group(1).strip()}")
        else:
            lines.append(line)
    return "\n".join(lines)


def sentence_chunks(markdown: str) -> list[str]:
    if markdown.lstrip().startswith("|"):
        return []
    text = plain_text(markdown)
    text = re.sub(r"^(?:\d+[.、]|[一二三四五六七八九十]+[、.])\s*", "", text)
    if not text or "风险提示" in text[:12] or text.endswith(("？", "?")):
        return []
    if 12 <= len(text) <= 220 and text.endswith(COMPLETE_SENTENCE_ENDINGS):
        return [text]
    if 18 <= len(text) <= 220 and not text.endswith(("：", ":")):
        is_list_item = bool(re.match(r"^\s*(?:[-*+]|\d+[.、])\s+", markdown))
        if is_list_item or "：" in text or any(word in text for word in SUMMARY_SIGNAL_WORDS):
            return [text + "。"]
    chunks = [part.strip() for part in re.findall(r".+?(?:[。！？!?；;]|$)", text)]
    return [
        chunk
        for chunk in chunks
        if 12 <= len(chunk) <= 280
        and chunk.endswith(COMPLETE_SENTENCE_ENDINGS)
        and not chunk.endswith(("？", "?"))
    ]


def prose_sentence_count(markdown: str) -> int:
    return max(1, len(re.findall(r"[。！？!?；;]", plain_text(markdown))))


def markdown_sections(markdown: str) -> list[tuple[str, list[tuple[int, str]]]]:
    sections: list[tuple[str, list[tuple[int, str]]]] = []
    heading = ""
    blocks: list[tuple[int, str]] = []
    for position, block in enumerate(re.split(r"\n\s*\n", markdown)):
        value = block.strip()
        if not value:
            continue
        heading_match = re.fullmatch(r"#{2,6}\s+(.+)", value)
        if heading_match:
            if blocks:
                sections.append((heading, blocks))
            heading = plain_text(heading_match.group(1))
            blocks = []
            continue
        blocks.append((position, value))
    if blocks:
        sections.append((heading, blocks))
    return sections


def is_duplicate_summary(candidate: str, selected: list[str]) -> bool:
    compact = re.sub(r"\W+", "", candidate)
    for existing in selected:
        other = re.sub(r"\W+", "", existing)
        if compact in other or other in compact:
            return True
        if SequenceMatcher(None, compact, other).ratio() >= 0.72:
            return True
    return False


def finish_summary_sentence(value: str) -> str:
    value = value.strip()
    if value.endswith(("；", ";")):
        return value[:-1] + "。"
    return value


def summary_points_for(report: LegacyReport, blurb: str, body: str) -> list[str]:
    """Build a conservative extractive summary without inventing report conclusions."""
    sections = markdown_sections(body)
    preferred_sections = [
        blocks
        for heading, blocks in sections
        if any(keyword in heading for keyword in SUMMARY_SECTION_KEYWORDS)
    ]
    preferred_blocks: list[tuple[int, str]] = []
    for blocks in preferred_sections:
        preferred_blocks.extend(blocks)
        if len(preferred_blocks) >= 2:
            break

    selected: list[str] = []
    if preferred_blocks:
        extracted = [
            (position, sentence_chunks(block), prose_sentence_count(block))
            for position, block in preferred_blocks
        ]
        extracted = [item for item in extracted if item[1]]

        if len(extracted) == 1:
            ordered = [
                (extracted[0][0], [chunk], 1) for chunk in extracted[0][1][:4]
            ]
            point_limit = len(ordered)
        elif len(extracted) <= 6:
            ordered = extracted
            point_limit = len(extracted)
        else:
            # Long sections often alternate a thesis sentence and supporting detail.
            ordered = extracted[:1]
            ordered.extend(item for item in extracted[1:] if item[2] == 1)
            ordered.extend(item for item in extracted[1:] if item[2] > 1)
            point_limit = 5
        for _, chunks, _ in ordered:
            candidate = finish_summary_sentence(chunks[0])
            if not is_duplicate_summary(candidate, selected):
                selected.append(candidate)
            if len(selected) == point_limit:
                break
    else:
        if (
            12 <= len(blurb) <= 280
            and blurb.endswith(COMPLETE_SENTENCE_ENDINGS)
            and not blurb.endswith(("？", "?"))
        ):
            selected.append(finish_summary_sentence(blurb))

        for _, blocks in sections:
            overview = next(
                (
                    finish_summary_sentence(candidate)
                    for _, block in blocks
                    for candidate in sentence_chunks(block)[:1]
                    if not is_duplicate_summary(candidate, selected)
                ),
                None,
            )
            if overview:
                selected.append(overview)
                break

        candidates: list[tuple[int, int, str]] = []
        for heading, blocks in sections:
            if "风险" in heading or "数据" in heading:
                continue
            heading_bonus = 8 if any(word in heading for word in SUMMARY_SIGNAL_WORDS) else 0
            for position, block in blocks:
                for candidate in sentence_chunks(block)[:1]:
                    score = heading_bonus + sum(
                        2 for keyword in SUMMARY_SIGNAL_WORDS if keyword in candidate
                    )
                    if 35 <= len(candidate) <= 180:
                        score += 3
                    candidates.append((score, position, finish_summary_sentence(candidate)))

        for _, _, candidate in sorted(candidates, key=lambda item: (-item[0], item[1])):
            if is_duplicate_summary(candidate, selected):
                continue
            selected.append(candidate)
            if len(selected) == 4:
                break

    if len(selected) < 2:
        fallback = sentence_chunks(body)
        for candidate in fallback:
            candidate = finish_summary_sentence(candidate)
            if not is_duplicate_summary(candidate, selected):
                selected.append(candidate)
            if len(selected) == 2:
                break
    if not selected:
        raise ValueError(f"无法为历史研报生成摘要: {report.legacy_stem}")
    return selected


def description_for(summary_points: list[str]) -> str:
    selected = [summary_points[0]]
    if len(summary_points) > 1 and len(summary_points[0]) + len(summary_points[1]) <= 220:
        selected.append(summary_points[1])
    return " ".join(selected)


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


def localize_images(session: requests.Session, report: LegacyReport, body: str) -> str:
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
        existing_placeholder = ASSET_ROOT / str(report.report_id) / f"missing-{image_number:03d}.svg"
        if existing_placeholder.exists():
            local_image = f"/report-assets/{report.report_id}/{existing_placeholder.name}"
            return f"[![历史图片暂不可用]({local_image})]({url})"
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

    return IMAGE_PATTERN.sub(replace_image, body)


def render_report(report: LegacyReport, body: str, summary_points: list[str]) -> str:
    published_at = report.published_at.strftime("%Y-%m-%dT00:00:00+08:00")
    frontmatter = [
        "---",
        f"title: {yaml_string(report.title)}",
        f"publishedAt: {yaml_string(published_at)}",
        f"source: {yaml_string('历史公开研报')}",
        f"sourceUrl: {yaml_string(report.source_url)}",
        f"description: {yaml_string(description_for(summary_points))}",
        "summary:",
        *(f"  - {yaml_string(point)}" for point in summary_points),
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
        blurb, normalized_body = normalize_body(report.body)
        summary_points = summary_points_for(report, blurb, normalized_body)
        structured_body = improve_body_structure(normalized_body)
        body = localize_images(session, report, structured_body)
        destination = DESTINATION_ROOT / f"{report.report_id}.md"
        temporary = destination.with_suffix(".md.tmp")
        temporary.write_text(render_report(report, body, summary_points), encoding="utf-8")
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
    print("已移除旧模板导语引用，并为每篇生成完整句的结构化摘要")
    print(f"分类统计: {json.dumps(categories, ensure_ascii=False, sort_keys=True)}")
    print(f"已转换 {route_count} 条旧 Docsify 路由")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
