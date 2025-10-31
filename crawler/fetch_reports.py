"""
鳄鱼派研报爬虫 - 内容下载器

⚠️ 架构说明 (2025-11-01 重构):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
本脚本专注于下载文章内容,不再负责边界探测。

职责分工:
1. scripts/pre_crawl_check.py  → 边界探测 (轻量级,快速)
2. crawler/fetch_reports.py    → 内容下载 (重量级,完整)

工作流程:
1. 先运行 pre_crawl_check.py 探测边界,写入 last_probed_id
2. 再运行 fetch_reports.py 下载文章,读取 last_probed_id 作为边界
3. 自动跳过已下载的文章,实现增量更新

使用方法:
# 增量下载 (推荐)
python crawler/fetch_reports.py

# 限制单次下载数量
python crawler/fetch_reports.py --max-requests 100

# 手动下载指定范围
python crawler/fetch_reports.py --start-id 400 --end-id 500
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

        # 表格转换
        if name == "table":
            return convert_table(node)

        inner = "".join(convert(child) for child in node.children)
        return inner

    def convert_table(table_node) -> str:
        """将 HTML 表格转换为 Markdown 表格"""
        rows = []
        
        # 提取表头 (thead > tr > th 或第一行的 th)
        thead = table_node.find("thead")
        headers = []
        first_row_is_header = False
        
        if thead:
            header_row = thead.find("tr")
            if header_row:
                headers = [
                    "".join(convert(child) for child in th.children).strip()
                    for th in header_row.find_all(["th", "td"])
                ]
        
        # 如果没有 thead，检查第一行是否全是 th
        if not headers:
            first_row = table_node.find("tr")
            if first_row:
                ths = first_row.find_all("th")
                if ths:
                    headers = [
                        "".join(convert(child) for child in th.children).strip()
                        for th in ths
                    ]
                    first_row_is_header = True
        
        # 提取数据行 (tbody > tr > td 或所有 tr)
        tbody = table_node.find("tbody")
        data_rows = []
        
        if tbody:
            for tr in tbody.find_all("tr"):
                cells = [
                    "".join(convert(child) for child in td.children).strip()
                    for td in tr.find_all(["td", "th"])
                ]
                if cells:
                    data_rows.append(cells)
        else:
            # 没有 tbody，遍历所有 tr（跳过已处理的表头）
            all_trs = table_node.find_all("tr")
            start_idx = 1 if first_row_is_header else 0
            for tr in all_trs[start_idx:]:
                cells = [
                    "".join(convert(child) for child in td.children).strip()
                    for td in tr.find_all(["td", "th"])
                ]
                if cells:
                    # 跳过重复的表头行（内容与 headers 完全相同）
                    if headers and cells == headers:
                        continue
                    data_rows.append(cells)
        
        # 如果既没有表头也没有数据，返回空
        if not headers and not data_rows:
            return ""
        
        # 如果没有表头，使用第一行作为表头
        if not headers and data_rows:
            headers = data_rows[0]
            data_rows = data_rows[1:]
        
        # 构建 Markdown 表格
        if not headers:
            return ""
        
        # 确保所有行的列数一致
        col_count = len(headers)
        
        # 表头
        header_line = "| " + " | ".join(headers) + " |"
        separator = "|" + "|".join([" --- " for _ in range(col_count)]) + "|"
        
        # 数据行
        data_lines = []
        for row in data_rows:
            # 补齐或截断列数
            row = (row + [""] * col_count)[:col_count]
            data_lines.append("| " + " | ".join(row) + " |")
        
        # 组合表格
        table_md = "\n" + header_line + "\n" + separator + "\n"
        if data_lines:
            table_md += "\n".join(data_lines) + "\n"
        table_md += "\n"
        
        return table_md

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
    data.setdefault("downloaded_ids", [])  # 新增：追踪已下载的文章
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


def article_downloaded(article_id: int, index: Dict[str, Any]) -> bool:
    """检查文章是否已完成下载"""
    return int(article_id) in set(int(i) for i in index.get("downloaded_ids", []))


def add_downloaded_id(article_id: int, index: Dict[str, Any]) -> None:
    """标记文章已成功下载"""
    downloaded = set(int(i) for i in index.get("downloaded_ids", []))
    downloaded.add(int(article_id))
    index["downloaded_ids"] = sorted(downloaded)


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
    """[已弃用] 仅用于手动模式兼容"""
    saved_ids = list(index.get("saved_ids", []))
    max_saved = max(saved_ids) if saved_ids else 0
    next_cursor = int(index.get("next_probe_id", 1))
    last_probed = int(index.get("last_probed_id", 0))
    return max(1, max_saved, next_cursor, last_probed)


# ==================== 已弃用的探测函数 ====================
# 以下函数已由 pre_crawl_check.py 接管,保留仅用于手动模式
# =======================================================

def fetch_pending_articles(
    fetcher: "GatorFetcher",
    pending_ids: Sequence[int],
    index: Dict[str, Any],
) -> List[Article]:
    """[已弃用] 重试 pending 列表中的文章"""
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
    """
    [已弃用] 此函数已由 pre_crawl_check.py 接管
    
    新架构:
    - pre_crawl_check.py: 轻量级边界探测
    - fetch_reports.py: 只负责下载已知边界内的文章
    """
    print("\n⚠️  警告: probe_new_articles() 已弃用")
    print("   请使用 pre_crawl_check.py 进行边界探测")
    return []


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
    downloaded_ids = set(int(i) for i in index.get("downloaded_ids", []))
    pending_ids = set(int(i) for i in index.get("pending_ids", []))

    success = 0
    skipped = 0
    failed = 0

    for article in sorted(articles, key=lambda a: a.article_id):
        article_id = int(article.article_id)

        # 检查是否已下载（而非仅检查是否已保存）
        if article_id in downloaded_ids:
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
        add_downloaded_id(article_id, index)  # 标记为已下载
        clear_missing_id(article_id, index)
        pending_ids.discard(article_id)
        saved_ids.add(article_id)
        downloaded_ids.add(article_id)
        success += 1

        index["pending_ids"] = sorted(pending_ids)
        index["downloaded_ids"] = sorted(downloaded_ids)
        write_index(index)

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    index["pending_ids"] = sorted(pending_ids)
    index["saved_ids"] = sorted(saved_ids)
    index["downloaded_ids"] = sorted(downloaded_ids)
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
        """
        获取单篇文章的完整内容
        
        ⚠️ 关键：文章存在性判断 (2025-11-01 验证)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        1. 这是 SPA (单页应用)，需要等待 JS 动态加载内容
        2. 文章不存在时，页面只显示免责声明:
           "鳄鱼派声明：文章内容仅供参考，不构成投资建议。投资者据此操作，风险自担。"
        3. 文章存在时，页面会显示标题、日期、正文等完整内容 (通常 > 200 字符)
        4. 免责声明是判断文章不存在的关键标识！
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """
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

        # 检查文章是否存在：关键判断标识
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
    parser = argparse.ArgumentParser(
        description="下载鳄鱼派研报 (仅下载,不探测边界)",
        epilog="提示: 边界探测请使用 python scripts/pre_crawl_check.py"
    )
    parser.add_argument("--start-id", type=int, help="手动模式: 起始 ID")
    parser.add_argument("--end-id", type=int, help="手动模式: 结束 ID")
    parser.add_argument("--batch-size", type=int, help="[已弃用] 改用 --max-requests")
    parser.add_argument("--max-requests", type=int, help="单次最多下载多少篇文章 (默认: 全部)")
    parser.add_argument("--max-miss", type=int, default=25, help="手动模式: 连续缺失阈值 (默认 25)")
    parser.add_argument("--no-headless", action="store_true", help="显示浏览器窗口 (调试用)")
    parser.add_argument("--save-html", action="store_true", help="保存原始 HTML (调试用)")
    parser.add_argument("--sleep", type=float, default=1.0, help="请求间隔秒数 (默认 1.0)")
    return parser.parse_args(argv)


def determine_range(args: argparse.Namespace, index: Dict[str, Any]) -> Tuple[int, int]:
    if args.start_id is not None and args.end_id is not None:
        return args.start_id, args.end_id
    if args.start_id is not None and args.end_id is None:
        return args.start_id, args.start_id + args.batch_size - 1

    start = resolve_probe_start(index)
    end = start + args.batch_size - 1
    return start, end


def verify_downloaded_files(index: Dict[str, Any]) -> tuple[set[int], set[int], set[int]]:
    """
    验证 downloaded_ids 对应的文件是否实际存在
    
    返回: (实际存在的 ID, 文件丢失的 ID, 额外的 ID)
    
    ⚠️ 数据一致性保证 (2025-11-01):
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    问题 1: downloaded_ids 记录了 ID,但 MD 文件可能被手动删除
    问题 2: 手动添加的 MD 文件,但 downloaded_ids 没有记录
    解决: 启动时验证文件实际存在,双向同步 downloaded_ids
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """
    downloaded_ids = set(int(i) for i in index.get("downloaded_ids", []))
    
    # 扫描所有 MD 文件,提取 article_id
    existing_ids = set()
    for category_path in ARTICLE_CATEGORIES.values():
        if not category_path.exists():
            continue
        
        for md_file in category_path.glob("*.md"):
            if md_file.name.lower() == "readme.md":
                continue
            
            # 从文件内容中提取 article_id
            try:
                content = md_file.read_text(encoding="utf-8")
                match = re.search(r"^- 文章ID:\s*(\d+)", content, re.MULTILINE)
                if match:
                    existing_ids.add(int(match.group(1)))
            except Exception:
                continue
    
    # 计算差异
    missing_files = downloaded_ids - existing_ids  # JSON 有但文件不存在
    extra_files = existing_ids - downloaded_ids    # 文件存在但 JSON 没记录
    
    return existing_ids, missing_files, extra_files


def run_incremental_mode(args: argparse.Namespace, index: Dict[str, Any]) -> int:
    """
    增量下载模式 (不再探测,只下载)
    
    ⚠️ 职责分离 (2025-11-01 重构):
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    1. pre_crawl_check.py 负责边界探测,写入 last_probed_id
    2. fetch_reports.py 只负责下载,从 index.json 读取边界
    3. 下载范围: 从 1 到 last_probed_id (跳过已下载的)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """
    # 🆕 第一步: 验证文件实际存在并同步
    print("🔍 验证已下载文件...")
    existing_ids, missing_files, extra_files = verify_downloaded_files(index)
    
    sync_needed = False
    
    if missing_files:
        print(f"⚠️  发现 {len(missing_files)} 篇文件丢失 (JSON 有记录但文件不存在)")
        print(f"   丢失 ID: {sorted(list(missing_files))[:20]}{'...' if len(missing_files) > 20 else ''}")
        sync_needed = True
    
    if extra_files:
        print(f"📥 发现 {len(extra_files)} 篇额外文件 (文件存在但 JSON 未记录)")
        print(f"   额外 ID: {sorted(list(extra_files))[:20]}{'...' if len(extra_files) > 20 else ''}")
        sync_needed = True
    
    if sync_needed:
        # 双向同步: 以实际文件为准
        index["downloaded_ids"] = sorted(list(existing_ids))
        index["saved_ids"] = sorted(list(set(index.get("saved_ids", [])) | existing_ids))
        write_index(index)
        print(f"✅ 已同步 downloaded_ids: {len(index['downloaded_ids'])} 篇")
    else:
        print(f"✅ 文件验证通过: {len(existing_ids)} 篇")
    
    downloaded_ids = existing_ids  # 使用实际存在的 ID
    boundary = int(index.get("last_probed_id", 0))
    
    print("📊 当前索引状态:")
    print(f"   已下载: {len(downloaded_ids)} 篇")
    print(f"   探测边界: ID {boundary} (由 pre_crawl_check.py 写入)")
    
    if boundary == 0:
        print("\n❌ 错误: 边界未探测 (last_probed_id = 0)")
        print("   请先运行: python scripts/pre_crawl_check.py")
        return 1
    
    # 计算需要下载的 ID 列表 (1 到 boundary, 跳过已下载)
    all_ids = set(range(1, boundary + 1))
    known_missing = set(int(i) for i in index.get("missing_ids", []))
    to_download = sorted(all_ids - downloaded_ids - known_missing)
    
    if not to_download:
        print("\n✅ 所有文章已下载完成!")
        print(f"   边界内文章: {boundary} 篇")
        print(f"   已下载: {len(downloaded_ids)} 篇")
        print(f"   已知缺失: {len(known_missing)} 篇")
        return 0
    
    print(f"\n📥 待下载文章: {len(to_download)} 篇")
    print(f"   ID 范围: {to_download[0]} - {to_download[-1]}")
    print(f"   前 20 个: {to_download[:20]}")
    
    # 限制单次下载数量
    max_download = args.max_requests if args.max_requests else len(to_download)
    if args.batch_size:  # 兼容旧参数
        print(f"⚠️  --batch-size 已弃用，请使用 --max-requests")
        max_download = args.batch_size
    
    to_download_batch = to_download[:max_download]
    print(f"\n🚀 本次下载: {len(to_download_batch)} 篇 (剩余 {len(to_download) - len(to_download_batch)} 篇)")
    
    # 开始下载
    articles_to_save: List[Article] = []
    success_count = 0
    skip_count = 0
    fail_count = 0
    
    with GatorFetcher(headless=not args.no_headless, save_html=args.save_html) as fetcher:
        for idx, article_id in enumerate(to_download_batch, 1):
            print(f"\n📄 [{idx}/{len(to_download_batch)}] 下载 ID {article_id}...", end=" ")
            
            article = fetcher.fetch(article_id)
            if article:
                articles_to_save.append(article)
                success_count += 1
                print(f"✅ {article.title[:40]}...")
            else:
                record_missing_id(article_id, index)
                fail_count += 1
                print(f"❌ 未找到")
            
            if args.sleep > 0:
                time.sleep(args.sleep)
        
        # 批量保存
        if articles_to_save:
            print(f"\n💾 开始保存 {len(articles_to_save)} 篇文章...")
            saved, skipped, failed = download_articles(
                articles_to_save,
                index,
                sleep_seconds=0,  # 已经在下载时sleep了
            )
        else:
            print("\n⚠️  本次未成功下载任何文章")
            saved = skipped = failed = 0
    
    # 最终统计
    final_downloaded = len(index.get("downloaded_ids", []))
    final_missing = len(index.get("missing_ids", []))
    remaining = boundary - final_downloaded - final_missing
    
    print("\n" + "=" * 60)
    print("✅ 下载完成")
    print("=" * 60)
    print(f"本次结果:")
    print(f"   成功下载: {saved} 篇")
    print(f"   跳过: {skipped} 篇")
    print(f"   失败: {failed} 篇")
    print(f"\n总体进度:")
    print(f"   边界: ID {boundary}")
    print(f"   已下载: {final_downloaded} 篇")
    print(f"   已知缺失: {final_missing} 篇")
    print(f"   剩余待下载: {remaining} 篇")
    
    if remaining > 0:
        print(f"\n💡 提示: 再次运行本脚本可继续下载剩余 {remaining} 篇文章")
    else:
        print(f"\n🎉 恭喜! 边界内所有文章已下载完成!")
    
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
