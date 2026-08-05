"""Download a WeChat article and localize its image assets."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTENT_DIR = PROJECT_ROOT / "src" / "content" / "articles"
DEFAULT_ASSET_ROOT = PROJECT_ROOT / "public" / "article-assets"
MAX_ASSET_BYTES = 25 * 1024 * 1024
CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)", re.IGNORECASE)
PUBLISHED_AT_RE = re.compile(
    r"(?:var\s+(?:ct|create_time)\s*=|[\"'](?:ct|create_time)[\"']\s*:)"
    r"\s*[\"']?(\d{10,13})",
    re.IGNORECASE,
)
SHANGHAI = ZoneInfo("Asia/Shanghai")


class ArticleDownloadError(RuntimeError):
    """The article or one of its required assets could not be downloaded."""


@dataclass(frozen=True)
class ArticleSummary:
    article_id: str
    title: str
    url: str
    cover_url: str
    published_at: datetime


@dataclass(frozen=True)
class DownloadedArticle:
    article_id: str
    title: str
    source_url: str
    description: str
    published_at: datetime
    cover_path: str
    body_html: str
    markdown_path: Path
    asset_count: int


def _canonical_url(url: str) -> str:
    return url.split("#", 1)[0].strip()


def _safe_article_id(article_id: str, url: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", article_id).strip("-")
    if safe_id:
        return safe_id[:80]
    return hashlib.sha256(_canonical_url(url).encode("utf-8")).hexdigest()[:16]


def _absolute_url(url: str, base_url: str) -> str:
    value = url.strip()
    if value.startswith("//"):
        return "https:" + value
    return urljoin(base_url, value)


def _extension_for(response: requests.Response, url: str) -> str:
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
    known_types = {
        "image/avif": ".avif",
        "image/gif": ".gif",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/svg+xml": ".svg",
        "image/webp": ".webp",
    }
    if content_type in known_types:
        return known_types[content_type]

    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix

    guessed = mimetypes.guess_extension(content_type)
    return guessed or ".bin"


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


class WeChatArticleDownloader:
    def __init__(
        self,
        content_dir: Path = DEFAULT_CONTENT_DIR,
        asset_root: Path = DEFAULT_ASSET_ROOT,
        timeout_seconds: int = 45,
    ) -> None:
        self._content_dir = content_dir
        self._asset_root = asset_root
        self._timeout_seconds = timeout_seconds
        self._session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        self._session.mount("https://", HTTPAdapter(max_retries=retry))
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
        )

    def download(self, summary: ArticleSummary, source_name: str) -> DownloadedArticle:
        response = self._get(summary.url, referer="https://mp.weixin.qq.com/")
        return self._download_response(summary, source_name, response)

    def download_detail(
        self,
        summary: ArticleSummary,
        source_name: str,
        detail: dict[str, Any],
    ) -> DownloadedArticle:
        """Archive HTML returned by the RapidAPI article-detail endpoint."""
        actual_source = str(detail.get("sourceName") or "").strip()
        if actual_source != source_name:
            raise ArticleDownloadError(
                f"公众号不匹配，期望“{source_name}”，实际“{actual_source or '无法识别'}”"
            )

        html = str(detail.get("html") or "").strip()
        soup = BeautifulSoup(html, "html.parser")
        content = soup.select_one("#js_content, .rich_media_content") or soup.body
        if content is None:
            raise ArticleDownloadError("RapidAPI 文章详情不包含可归档的正文节点")

        return self._archive_content(
            summary=summary,
            source_name=source_name,
            content=content,
            title=str(detail.get("title") or summary.title).strip(),
            description=str(detail.get("description") or "").strip(),
            cover_url=str(detail.get("coverUrl") or summary.cover_url).strip(),
        )

    def download_url(
        self,
        url: str,
        source_name: str,
        *,
        verify_source: bool = True,
    ) -> DownloadedArticle:
        """Inspect and download a known public WeChat article URL in one request."""
        response = self._get(url, referer="https://mp.weixin.qq.com/")
        response.encoding = response.apparent_encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")
        actual_source = self._source_name(soup)
        if verify_source and actual_source != source_name:
            raise ArticleDownloadError(
                f"公众号不匹配，期望“{source_name}”，实际“{actual_source or '无法识别'}”"
            )

        title = self._metadata(soup, "og:title")
        published_at = self._published_at(response.text)
        if not title or published_at is None:
            page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
            raise ArticleDownloadError(
                "无法从微信页面识别标题或发布时间，页面可能要求验证："
                f"{page_title or '未知页面'}"
            )

        canonical_url = self._metadata(soup, "og:url") or response.url or url
        canonical_url = _canonical_url(canonical_url)
        article_id = self._article_id(canonical_url)
        summary = ArticleSummary(
            article_id=article_id,
            title=title,
            url=canonical_url,
            cover_url=self._metadata(soup, "og:image"),
            published_at=published_at,
        )
        return self._download_response(summary, source_name, response)

    def _download_response(
        self,
        summary: ArticleSummary,
        source_name: str,
        response: requests.Response,
    ) -> DownloadedArticle:
        response.encoding = response.apparent_encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")
        content = soup.select_one("#js_content, .rich_media_content")
        if content is None:
            page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
            raise ArticleDownloadError(
                f"正文节点不存在，微信返回页面标题：{page_title or '未知'}"
            )
        return self._archive_content(
            summary=summary,
            source_name=source_name,
            content=content,
            title=self._metadata(soup, "og:title") or summary.title,
            description=self._metadata(soup, "og:description"),
            cover_url=summary.cover_url or self._metadata(soup, "og:image"),
        )

    def _archive_content(
        self,
        summary: ArticleSummary,
        source_name: str,
        content: Tag,
        title: str,
        description: str,
        cover_url: str,
    ) -> DownloadedArticle:
        article_key = _safe_article_id(summary.article_id, summary.url)
        final_asset_dir = self._asset_root / article_key
        temporary_asset_dir = self._asset_root / f".{article_key}.tmp"
        markdown_path = (
            self._content_dir
            / f"{summary.published_at.date().isoformat()}-{article_key}.md"
        )

        shutil.rmtree(temporary_asset_dir, ignore_errors=True)
        temporary_asset_dir.mkdir(parents=True, exist_ok=True)

        try:
            visible_text = content.get_text(" ", strip=True)
            has_background_image = any(
                CSS_URL_RE.search(str(node.get("style", "")))
                for node in content.find_all(style=True)
            )
            if (
                not visible_text
                and content.find(["img", "image"]) is None
                and not has_background_image
            ):
                raise ArticleDownloadError("正文节点不包含文本或图片")

            self._sanitize(content)
            asset_count, usable_image_count = self._localize_content_images(
                content,
                summary.url,
                article_key,
                temporary_asset_dir,
            )
            if not visible_text and usable_image_count == 0:
                raise ArticleDownloadError("纯图片正文未能解析出可用图片")
            if not description:
                description = (
                    visible_text[:180]
                    if visible_text
                    else f"图片文章，共 {usable_image_count} 张正文图片。"
                )

            cover_path = ""
            if cover_url:
                cover_path = self._download_asset(
                    _absolute_url(cover_url, summary.url),
                    "cover",
                    article_key,
                    temporary_asset_dir,
                    summary.url,
                )
                asset_count += 1

            body_html = content.decode_contents().strip()
            if not body_html:
                raise ArticleDownloadError("正文解析后为空")

            self._replace_directory(temporary_asset_dir, final_asset_dir)
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown = self._render_markdown(
                summary=summary,
                source_name=source_name,
                title=title,
                description=description,
                cover_path=cover_path,
                body_html=body_html,
            )
            temporary_markdown = markdown_path.with_suffix(".md.tmp")
            temporary_markdown.write_text(markdown, encoding="utf-8")
            temporary_markdown.replace(markdown_path)
        except Exception:
            shutil.rmtree(temporary_asset_dir, ignore_errors=True)
            raise

        return DownloadedArticle(
            article_id=summary.article_id,
            title=title,
            source_url=_canonical_url(summary.url),
            description=description,
            published_at=summary.published_at,
            cover_path=cover_path,
            body_html=body_html,
            markdown_path=markdown_path,
            asset_count=asset_count,
        )

    @staticmethod
    def _article_id(url: str) -> str:
        parsed = urlparse(url)
        if parsed.netloc.lower() != "mp.weixin.qq.com":
            raise ArticleDownloadError(f"不是微信公众号文章链接: {url}")
        path_parts = [part for part in parsed.path.split("/") if part]
        if (
            len(path_parts) == 2
            and path_parts[0] == "s"
            and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", path_parts[1])
        ):
            return path_parts[1]
        if parsed.path.rstrip("/") == "/s":
            query = parse_qs(parsed.query)
            biz = str((query.get("__biz") or [""])[0]).strip()
            mid = str((query.get("mid") or [""])[0]).strip()
            idx = str((query.get("idx") or [""])[0]).strip()
            if biz and mid.isdigit() and idx.isdigit():
                digest = hashlib.sha256(f"{biz}:{mid}:{idx}".encode("utf-8"))
                return f"wechat-{digest.hexdigest()[:20]}"
        raise ArticleDownloadError(f"不支持的微信公众号文章链接格式: {url}")

    @staticmethod
    def _published_at(source: str) -> Optional[datetime]:
        match = PUBLISHED_AT_RE.search(source)
        if match is None:
            return None
        timestamp = int(match.group(1))
        if timestamp > 10_000_000_000:
            timestamp //= 1000
        return datetime.fromtimestamp(timestamp, tz=SHANGHAI)

    @staticmethod
    def _source_name(soup: BeautifulSoup) -> str:
        for selector in ("#js_name", "#js_account_name"):
            element = soup.select_one(selector)
            if isinstance(element, Tag):
                value = element.get_text(" ", strip=True)
                if value:
                    return value
        return ""

    def _get(self, url: str, referer: str) -> requests.Response:
        response = self._session.get(
            url,
            headers={"Referer": referer},
            timeout=self._timeout_seconds,
            stream=False,
        )
        if response.status_code != 200:
            raise ArticleDownloadError(f"下载失败 HTTP {response.status_code}: {url}")
        return response

    @staticmethod
    def _metadata(soup: BeautifulSoup, property_name: str) -> str:
        element = soup.find("meta", attrs={"property": property_name})
        if not isinstance(element, Tag):
            element = soup.find("meta", attrs={"name": property_name})
        return str(element.get("content", "")).strip() if isinstance(element, Tag) else ""

    @staticmethod
    def _sanitize(content: Tag) -> None:
        for node in content.select("script, style, noscript, form, button"):
            node.decompose()

        for node in content.find_all(True):
            for attribute in list(node.attrs):
                if attribute.lower().startswith("on"):
                    del node.attrs[attribute]
            if node.name == "a":
                href = str(node.get("href", "")).strip()
                if href.startswith("javascript:"):
                    node.attrs.pop("href", None)
                elif href:
                    node["rel"] = "noopener noreferrer"

    def _localize_content_images(
        self,
        content: Tag,
        article_url: str,
        article_key: str,
        asset_dir: Path,
    ) -> tuple[int, int]:
        downloaded: dict[str, str] = {}
        asset_count = 0
        usable_image_count = 0
        for image_index, image in enumerate(
            content.find_all(["img", "image"]),
            start=1,
        ):
            raw_url = str(
                image.get("data-src")
                or image.get("data-original")
                or image.get("src")
                or image.get("href")
                or image.get("xlink:href")
                or ""
            ).strip()
            if not raw_url:
                image.decompose()
                continue
            if raw_url.startswith("data:"):
                usable_image_count += 1
                image["loading"] = "lazy"
                continue
            asset_url = _absolute_url(raw_url, article_url)
            local_path = downloaded.get(asset_url)
            if local_path is None:
                local_path = self._download_asset(
                    asset_url,
                    f"image-{image_index:03d}",
                    article_key,
                    asset_dir,
                    article_url,
                )
                downloaded[asset_url] = local_path
                asset_count += 1
            if image.name == "image":
                image["href"] = local_path
                image.attrs.pop("xlink:href", None)
            else:
                image["src"] = local_path
            image.attrs.pop("data-src", None)
            image.attrs.pop("data-original", None)
            image.attrs.pop("srcset", None)
            image.attrs.pop("data-srcset", None)
            image["loading"] = "lazy"
            usable_image_count += 1

        background_index = 0
        for node in content.find_all(style=True):
            style = str(node.get("style", ""))

            def replace_background(match: re.Match[str]) -> str:
                nonlocal asset_count, background_index, usable_image_count
                raw_url = match.group(2).strip()
                if raw_url.startswith("data:"):
                    usable_image_count += 1
                    return match.group(0)
                if not raw_url or raw_url.startswith("#"):
                    return match.group(0)
                asset_url = _absolute_url(raw_url, article_url)
                local_path = downloaded.get(asset_url)
                if local_path is None:
                    background_index += 1
                    local_path = self._download_asset(
                        asset_url,
                        f"background-{background_index:03d}",
                        article_key,
                        asset_dir,
                        article_url,
                    )
                    downloaded[asset_url] = local_path
                    asset_count += 1
                usable_image_count += 1
                return f"url('{local_path}')"

            node["style"] = CSS_URL_RE.sub(replace_background, style)
        return asset_count, usable_image_count

    def _download_asset(
        self,
        url: str,
        stem: str,
        article_key: str,
        asset_dir: Path,
        article_url: str,
    ) -> str:
        response = self._get(url, referer=article_url)
        content_length = int(response.headers.get("Content-Length", "0") or 0)
        if content_length > MAX_ASSET_BYTES or len(response.content) > MAX_ASSET_BYTES:
            raise ArticleDownloadError(f"图片超过 25 MiB 限制: {url}")
        if not response.content:
            raise ArticleDownloadError(f"图片内容为空: {url}")

        extension = _extension_for(response, url)
        filename = f"{stem}{extension}"
        destination = asset_dir / filename
        destination.write_bytes(response.content)
        return f"/article-assets/{article_key}/{filename}"

    @staticmethod
    def _replace_directory(source: Path, destination: Path) -> None:
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)

    @staticmethod
    def _render_markdown(
        summary: ArticleSummary,
        source_name: str,
        title: str,
        description: str,
        cover_path: str,
        body_html: str,
    ) -> str:
        fields = [
            "---",
            f"title: {_yaml_string(title)}",
            f"publishedAt: {_yaml_string(summary.published_at.isoformat())}",
            f"source: {_yaml_string(source_name)}",
            f"sourceUrl: {_yaml_string(_canonical_url(summary.url))}",
            f"description: {_yaml_string(description)}",
            f"cover: {_yaml_string(cover_path)}",
            f"articleId: {_yaml_string(summary.article_id)}",
            "---",
            "",
            '<div class="wechat-article">',
            body_html,
            "</div>",
            "",
        ]
        return "\n".join(fields)
