"""
Playwright-based crawler for Gator Investment Research articles.

This script replaces the Selenium implementation and works in headless environments
such as GitHub Actions without requiring a manually installed ChromeDriver.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import ARTICLE_CATEGORIES, INDEX_FILE, RAW_HTML_DIR, ensure_structure  # noqa: E402


BASE_URL = "http://h5.2025eyp.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

# 探测与索引维护的核心参数
PROBE_MAX_FETCHES = 80
PROBE_CONSECUTIVE_MISS = 25
MISSING_BUCKET_LIMIT = 800
PROBE_HISTORY_LIMIT = 20


@dataclass
class Article:
    article_id: int
    title: str
    category: str
    date: Optional[str]
    brief: Optional[str]
    markdown: str
    source_url: str


def sanitize_filename(name: str, max_len: int = 160) -> str:
    name = re.sub(r"[\\/*?:\"<>|]", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    if len(name) > max_len:
        name = name[:max_len].rstrip()
    return name or "article"


def extract_date(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})", text)
    if not match:
        return None
    y, m, d = re.split(r"[.\-/]", match.group(1))
    return f"{int(y):04d}.{int(m):02d}.{int(d):02d}"


def normalize_html(html: str) -> str:
    if not html:
        return html
    soup = BeautifulSoup(html, "html.parser")

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src:
            img["src"] = urljoin(BASE_URL, src)
        if img.has_attr("data-src"):
            del img["data-src"]

    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if href:
            anchor["href"] = urljoin(BASE_URL, href)

    return str(soup)


def html_to_markdown(html: str) -> str:
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    for br in soup.find_all(["br", "hr"]):
        br.replace_with("\n")

    def convert(node) -> str:
        if isinstance(node, str):
            return node
        name = node.name.lower() if node.name else ""

        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            prefix = "#" * level
            inner = "".join(convert(child) for child in node.children).strip()
            return f"\n{prefix} {inner}\n\n"

        if name == "p":
            inner = "".join(convert(child) for child in node.children).strip()
            return f"{inner}\n\n" if inner else ""

        if name in {"ul", "ol"}:
            items = []
            for li in node.find_all("li", recursive=False):
                content = "".join(convert(child) for child in li.children).strip()
                if content:
                    items.append(f"- {content}")
            return ("\n".join(items) + "\n\n") if items else ""

        if name == "li":
            inner = "".join(convert(child) for child in node.children).strip()
            return f"- {inner}\n"

        if name in {"strong", "b"}:
            inner = "".join(convert(child) for child in node.children)
            return f"**{inner}**"

        if name in {"em", "i"}:
            inner = "".join(convert(child) for child in node.children)
            return f"*{inner}*"

        if name == "a":
            text = "".join(convert(child) for child in node.children) or node.get("href", "")
            href = node.get("href", "")
            return f"[{text}]({href})" if href else text

        if name == "img":
            alt = node.get("alt", "")
            src = node.get("src", "")
            return f"![{alt}]({src})" if src else ""

        inner = "".join(convert(child) for child in node.children)
        return inner

    markdown = "".join(convert(child) for child in soup.body.children) if soup.body else convert(soup)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    return markdown + "\n"


def detect_category(title: str, preview: str, explicit: Optional[str] = None) -> str:
    if explicit and explicit in ARTICLE_CATEGORIES:
        return explicit

    text = "\n".join(filter(None, [explicit or "", title or "", preview or ""]))
    if re.search(r"宏观|政策|经济|大势|央行", text):
        return "宏观分析"
    if re.search(r"行业|产业|板块|赛道|公司|分析|专题|研究", text):
        return "行业分析"
    return "全部研报"


def build_filename(article: Article) -> str:
    prefix = f"{article.date}-" if article.date else ""
    return sanitize_filename(f"{prefix}{article.title}") + ".md"


def ensure_index_defaults(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    data.setdefault("saved_ids", [])
    data.setdefault("missing_ids", [])
    data.setdefault("pending_ids", [])
    data.setdefault("last_probed_id", 0)
    data.setdefault("next_probe_id", 1)
    data.setdefault("probe_history", [])
    return data


def read_index() -> Dict[str, Any]:
    if INDEX_FILE.exists():
        try:
            data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
            return ensure_index_defaults(data)
        except json.JSONDecodeError:
            pass
    return ensure_index_defaults({})


def write_index(data: Dict[str, Any]) -> None:
    # 清理调试用的临时字段
    dump_ready = {k: v for k, v in data.items() if not str(k).startswith("_")}
    INDEX_FILE.write_text(
        json.dumps(dump_ready, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_saved_id(article_id: int, index: Dict[str, Any]) -> None:
    saved = set(int(i) for i in index.get("saved_ids", []))
    saved.add(int(article_id))
    index["saved_ids"] = sorted(saved)


def article_already_saved(article_id: int, index: Dict[str, Any]) -> bool:
    return int(article_id) in set(int(i) for i in index.get("saved_ids", []))


def record_missing_id(article_id: int, index: Dict[str, Any]) -> None:
    missing = set(int(i) for i in index.get("missing_ids", []))
    missing.add(int(article_id))
    index["missing_ids"] = sorted(missing)[-MISSING_BUCKET_LIMIT:]


def clear_missing_id(article_id: int, index: Dict[str, Any]) -> None:
    missing = set(int(i) for i in index.get("missing_ids", []))
    if int(article_id) in missing:
        missing.discard(int(article_id))
        index["missing_ids"] = sorted(missing)


def update_probe_history(index: Dict[str, Any], start_id: int, stop_id: int, found_id: int) -> None:
    history = list(index.get("probe_history", []))
    history.append(
        {
            "start": int(start_id),
            "stop": int(stop_id),
            "found": int(found_id),
            "ts": int(time.time()),
        }
    )
    index["probe_history"] = history[-PROBE_HISTORY_LIMIT:]


def resolve_probe_start(index: Dict[str, Any]) -> int:
    saved_ids = list(index.get("saved_ids", []))
    max_saved = max(saved_ids) if saved_ids else 0
    next_cursor = int(index.get("next_probe_id", 1))
    last_probed = int(index.get("last_probed_id", 0))
    return max(1, max_saved, next_cursor, last_probed)


def fetch_pending_articles(
    fetcher: "GatorFetcher",
    pending_ids: Sequence[int],
    index: Dict[str, Any],
) -> List[Article]:
    """重试 pending 列表中的文章，返回成功的 Article 列表。"""
    results: Dict[int, Article] = {}

    for article_id in sorted({int(i) for i in pending_ids}):
        if article_already_saved(article_id, index):
            continue

        article = fetcher.fetch(article_id)
        if article:
            clear_missing_id(article_id, index)
            results[article.article_id] = article
        else:
            record_missing_id(article_id, index)

    return list(results.values())


def probe_new_articles(
    fetcher: "GatorFetcher",
    index: Dict[str, Any],
    max_fetches: int = PROBE_MAX_FETCHES,
    max_consecutive_missing: int = PROBE_CONSECUTIVE_MISS,
) -> List[Article]:
    """增量探测新文章，返回需要下载的 Article 列表"""
    saved = set(int(i) for i in index.get("saved_ids", []))
    known_missing = set(int(i) for i in index.get("missing_ids", []))

    start_id = resolve_probe_start(index)
    current_id = start_id
    fetched_count = 0
    consecutive_missing = 0
    last_found_id = int(index.get("last_probed_id", 0))

    new_articles: Dict[int, Article] = {}
    probed_ids: List[int] = []

    while fetched_count < max_fetches and consecutive_missing < max_consecutive_missing:
        if current_id in known_missing and current_id < index.get("next_probe_id", current_id):
            current_id += 1
            continue

        probed_ids.append(current_id)
        fetched_count += 1

        article = fetcher.fetch(current_id)
        if article:
            clear_missing_id(current_id, index)
            last_found_id = max(last_found_id, current_id)
            consecutive_missing = 0
            if current_id not in saved:
                new_articles[current_id] = article
        else:
            record_missing_id(current_id, index)
            consecutive_missing += 1

        current_id += 1

    index["next_probe_id"] = current_id
    index["last_probed_id"] = last_found_id
    update_probe_history(index, start_id, current_id - 1, last_found_id)
    index["_last_probe_ids"] = probed_ids

    return list(new_articles.values())


def manual_scan_range(
    fetcher: "GatorFetcher",
    start_id: int,
    end_id: int,
    index: Dict[str, Any],
    max_consecutive_missing: int,
) -> List[Article]:
    """按指定区间主动抓取文章，返回需要保存的文章列表"""
    new_articles: Dict[int, Article] = {}
    saved = set(int(i) for i in index.get("saved_ids", []))

    miss_streak = 0
    last_found = int(index.get("last_probed_id", 0))
    probed_ids: List[int] = []

    for article_id in range(start_id, end_id + 1):
        probed_ids.append(article_id)

        if article_already_saved(article_id, index):
            continue

        article = fetcher.fetch(article_id)
        if article:
            new_articles[article_id] = article
            clear_missing_id(article_id, index)
            miss_streak = 0
            last_found = max(last_found, article_id)
        else:
            record_missing_id(article_id, index)
            miss_streak += 1
            if miss_streak >= max_consecutive_missing:
                print("连续缺失达到阈值，提前结束扫描。")
                break

    stop_id = probed_ids[-1] if probed_ids else start_id - 1
    index["next_probe_id"] = max(index.get("next_probe_id", 1), stop_id + 1)
    index["last_probed_id"] = max(index.get("last_probed_id", 0), last_found)
    update_probe_history(index, start_id, stop_id, index["last_probed_id"])
    index["_last_probe_ids"] = probed_ids
    pending = set(int(i) for i in index.get("pending_ids", []))
    pending.update(
        article_id
        for article_id in new_articles
        if article_id not in saved
    )
    index["pending_ids"] = sorted(pending)
    write_index(index)

    return list(new_articles.values())


def save_article(article: Article) -> None:
    filename = build_filename(article)
    lines = [
        f"# {article.title}",
        "",
        f"- 分类: {article.category}",
        f"- 日期: {article.date or '未知'}",
        f"- 文章ID: {article.article_id}",
        f"- 来源: {article.source_url}",
        "",
        "---",
        "",
    ]

    if article.brief:
        lines.append(f"> {article.brief.strip()}")
        lines.append("")

    lines.append(article.markdown.rstrip())
    content = "\n".join(lines).rstrip() + "\n"

    # 保存到全部研报
    ARTICLE_CATEGORIES["全部研报"].mkdir(parents=True, exist_ok=True)
    target_all = ARTICLE_CATEGORIES["全部研报"] / filename
    target_all.write_text(content, encoding="utf-8")

    # 分类保存（宏观/行业）
    if article.category in ARTICLE_CATEGORIES and article.category != "全部研报":
        ARTICLE_CATEGORIES[article.category].mkdir(parents=True, exist_ok=True)
        ARTICLE_CATEGORIES[article.category].joinpath(filename).write_text(
            content, encoding="utf-8"
        )
    return target_all


def download_articles(
    articles: Sequence[Article],
    index: Dict[str, Any],
    sleep_seconds: float = 0.0,
) -> Tuple[int, int, int]:
    """保存文章并维护索引，返回 (新增, 跳过, 失败)"""
    saved_ids = set(int(i) for i in index.get("saved_ids", []))
    pending_ids = set(int(i) for i in index.get("pending_ids", []))

    success = 0
    skipped = 0
    failed = 0

    for article in sorted(articles, key=lambda a: a.article_id):
        article_id = int(article.article_id)

        if article_id in saved_ids:
            pending_ids.discard(article_id)
            skipped += 1
            continue

        try:
            save_article(article)
        except Exception as exc:  # noqa: BLE001 - 记录失败后继续
            print(f"[{article_id}] 保存失败: {exc}")
            record_missing_id(article_id, index)
            pending_ids.add(article_id)
            failed += 1
            continue

        add_saved_id(article_id, index)
        clear_missing_id(article_id, index)
        pending_ids.discard(article_id)
        saved_ids.add(article_id)
        success += 1

        index["pending_ids"] = sorted(pending_ids)
        write_index(index)

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    index["pending_ids"] = sorted(pending_ids)
    index["saved_ids"] = sorted(saved_ids)
    write_index(index)

    return success, skipped, failed


class GatorFetcher:
    def __init__(self, headless: bool = True, timeout: int = 20, save_html: bool = False):
        self.headless = headless
        self.timeout = timeout
        self.save_html = save_html
        self.driver: Optional[webdriver.Chrome] = None

    def __enter__(self) -> "GatorFetcher":
        ensure_structure()
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f"--user-agent={USER_AGENT}")
        options.add_argument("--disable-blink-features=AutomationControlled")

        try:
            self.driver = webdriver.Chrome(options=options)
        except WebDriverException as exc:  # noqa: BLE001
            raise RuntimeError(f"无法启动 Chrome WebDriver: {exc}") from exc

        self.driver.set_page_load_timeout(self.timeout)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass

    def _wait_for_content(self) -> None:
        assert self.driver is not None
        try:
            WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
            )
            WebDriverWait(self.driver, self.timeout).until(self._has_meaningful_text)
        except TimeoutException:
            pass

    @staticmethod
    def _has_meaningful_text(driver) -> bool:
        try:
            article = driver.find_element(By.CSS_SELECTOR, ".article")
            if article.text and len(article.text.strip()) > 40:
                return True
        except NoSuchElementException:
            pass
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            return len(body.text.strip()) > 200
        except NoSuchElementException:
            return False

    def fetch(self, article_id: int) -> Optional[Article]:
        assert self.driver is not None
        url = f"{BASE_URL}/articles/{article_id}"
        try:
            self.driver.get(url)
            self._wait_for_content()
        except TimeoutException:
            print(f"[{article_id}] 页面加载超时")
            return None
        except WebDriverException as exc:  # noqa: BLE001
            print(f"[{article_id}] 页面加载失败: {exc}")
            return None

        page_source = self.driver.page_source

        if self.save_html:
            RAW_HTML_DIR.joinpath(f"article_{article_id}.html").write_text(
                page_source, encoding="utf-8"
            )

        if "找不到页面" in page_source or "404" in page_source:
            return None

        soup = BeautifulSoup(page_source, "html.parser")

        def first_text(selectors: Iterable[str]) -> str:
            for selector in selectors:
                element = soup.select_one(selector)
                if element and element.get_text(strip=True):
                    return element.get_text(strip=True)
            return ""

        def first_html(selectors: Iterable[str]) -> str:
            for selector in selectors:
                element = soup.select_one(selector)
                if element and element.decode_contents():
                    return element.decode_contents()
            return ""

        title = first_text([".article .title", ".article-title", "article h1", "h1"])
        category_raw = first_text([".article .tags", ".article .category", ".article .cate"])
        date_text = first_text([".article .time", ".article .date", "time"])
        brief = first_text([".article .brief", ".article .summary"])
        content_html = first_html(
            [
                ".article .md-editor-preview",
                ".article .content",
                ".article-content",
                "article",
            ]
        )

        content_html = normalize_html(content_html)
        markdown = html_to_markdown(content_html) if content_html else ""

        if not markdown or len(markdown.strip()) < 40:
            body_text = first_text([".article", "body"])
            if not body_text or len(body_text) < 40:
                return None
            markdown = body_text.strip() + "\n"

        category = detect_category(title, markdown[:200], category_raw)
        date_fmt = extract_date(date_text) or extract_date(markdown)

        return Article(
            article_id=article_id,
            title=title or f"article_{article_id}",
            category=category,
            date=date_fmt,
            brief=brief,
            markdown=markdown,
            source_url=url,
        )


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Gator investment research articles.")
    parser.add_argument("--start-id", type=int, help="Start article ID (inclusive)")
    parser.add_argument("--end-id", type=int, help="End article ID (inclusive)")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size when auto-scanning for new IDs")
    parser.add_argument("--max-miss", type=int, default=15, help="Stop after this many consecutive missing articles")
    parser.add_argument("--no-headless", action="store_true", help="Run browser in headed mode for debugging")
    parser.add_argument("--save-html", action="store_true", help="Persist raw HTML snapshots for debugging")
    parser.add_argument("--sleep", type=float, default=1.0, help="Seconds to sleep between requests")
    return parser.parse_args(argv)


def determine_range(args: argparse.Namespace, index: Dict[str, Any]) -> Tuple[int, int]:
    if args.start_id is not None and args.end_id is not None:
        return args.start_id, args.end_id
    if args.start_id is not None and args.end_id is None:
        return args.start_id, args.start_id + args.batch_size - 1

    start = resolve_probe_start(index)
    end = start + args.batch_size - 1
    return start, end


def run_incremental_mode(args: argparse.Namespace, index: Dict[str, Any]) -> int:
    saved_count = len(index.get("saved_ids", []))
    missing_count = len(index.get("missing_ids", []))
    pending_count = len(index.get("pending_ids", []))

    print("📊 当前索引状态:")
    print(f"   已保存: {saved_count} 篇")
    print(f"   缺失记录: {missing_count} 个")
    print(f"   待下载: {pending_count} 个")
    print(f"   上次探测 ID: {index.get('last_probed_id', 0)}")
    print(f"   下一次探测起点: {index.get('next_probe_id', 1)}")

    with GatorFetcher(headless=not args.no_headless, save_html=args.save_html) as fetcher:
        pending_articles = fetch_pending_articles(fetcher, index.get("pending_ids", []), index)
        probed_articles = probe_new_articles(
            fetcher,
            index,
            max_fetches=max(1, args.batch_size),
            max_consecutive_missing=max(1, args.max_miss),
        )

        article_map: Dict[int, Article] = {
            article.article_id: article for article in pending_articles
        }
        for article in probed_articles:
            article_map[article.article_id] = article

        # 更新待下载列表（仅包含未保存的文章）
        pending_set = {
            int(article_id)
            for article_id in index.get("pending_ids", [])
            if not article_already_saved(article_id, index)
        }
        pending_set.update(
            article_id
            for article_id in article_map
            if not article_already_saved(article_id, index)
        )
        index["pending_ids"] = sorted(pending_set)
        write_index(index)

        probed_ids = index.get("_last_probe_ids", [])
        if probed_ids:
            print(
                f"\n🔍 本次探测 {len(probed_ids)} 个 ID，范围 {probed_ids[0]} - {probed_ids[-1]}"
            )
        else:
            print("\n🔍 本次未进行新的 ID 探测（可能全部命中缺失列表）。")

        if article_map:
            print(f"🎯 待保存文章 {len(article_map)} 篇，开始写入...")
            success, skipped, failed = download_articles(
                list(article_map.values()),
                index,
                sleep_seconds=max(0.0, args.sleep),
            )
        else:
            print("🎯 本次未发现需要下载的新文章。")
            success = skipped = failed = 0

    final_total = len(index.get("saved_ids", []))
    print("\n✅ 任务完成")
    print(f"   新增: {success} 篇，跳过: {skipped} 篇，失败: {failed} 篇")
    print(f"   当前总量: {final_total} 篇")
    print(f"   最新探测 ID: {index.get('last_probed_id', 0)}")
    print(f"   下一次探测将从 ID {index.get('next_probe_id', 1)} 开始")
    return 0


def run_manual_range_mode(args: argparse.Namespace, index: Dict[str, Any]) -> int:
    start_id, end_id = determine_range(args, index)
    print(f"🔧 手动模式：扫描 ID {start_id} ~ {end_id}")

    with GatorFetcher(headless=not args.no_headless, save_html=args.save_html) as fetcher:
        articles = manual_scan_range(
            fetcher,
            start_id,
            end_id,
            index,
            max_consecutive_missing=max(1, args.max_miss),
        )

    if articles:
        print(f"🎯 需要保存 {len(articles)} 篇文章...")
        success, skipped, failed = download_articles(
            articles,
            index,
            sleep_seconds=max(0.0, args.sleep),
        )
    else:
        print("🎯 手动扫描未发现可保存的新文章。")
        success = skipped = failed = 0

    final_total = len(index.get("saved_ids", []))
    print("\n✅ 手动扫描完成")
    print(f"   新增: {success} 篇，跳过: {skipped} 篇，失败: {failed} 篇")
    print(f"   当前总量: {final_total} 篇")
    print(f"   最新探测 ID: {index.get('last_probed_id', 0)}")
    print(f"   下一次探测将从 ID {index.get('next_probe_id', 1)} 开始")
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    ensure_structure()
    index = read_index()

    manual_mode = args.start_id is not None or args.end_id is not None
    if manual_mode:
        return run_manual_range_mode(args, index)
    return run_incremental_mode(args, index)


if __name__ == "__main__":
    sys.exit(main())
