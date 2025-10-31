"""
Update category README statistics blocks based on the latest crawl results.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import ARTICLE_CATEGORIES, DOCS_DIR, ensure_structure
from scripts.generate_stats import (
    generate_stats,
    list_markdown_files,
    get_last_update_from_files,
)

STATS_START = "<!-- stats:start -->"
STATS_END = "<!-- stats:end -->"


def render_stats_block(total: int, last_update: str) -> str:
    return "\n".join(
        [
            STATS_START,
            "",
            f"- **总计**: {total} 篇研报",
            f"- **最后更新**: {last_update}",
            "",
            STATS_END,
        ]
    )


def replace_block(content: str, block: str) -> str:
    if STATS_START in content and STATS_END in content:
        start = content.index(STATS_START)
        end = content.index(STATS_END) + len(STATS_END)
        return content[:start] + block + content[end:]
    # Append if markers do not exist yet.
    if content.endswith("\n"):
        return content + "\n" + block + "\n"
    return content + "\n\n" + block + "\n"


def update_category_readme(stats: Dict[str, object]) -> None:
    category_counts: Dict[str, int] = stats.get("categories", {})

    for category, path in ARTICLE_CATEGORIES.items():
        readme_path = path / "README.md"
        if not readme_path.exists():
            continue

        files = list_markdown_files(path)
        last_update = (
            stats["last_update"]
            if category == "全部研报"
            else get_last_update_from_files(files)
        )
        content = readme_path.read_text(encoding="utf-8")
        block = render_stats_block(category_counts.get(category, 0), last_update)
        readme_path.write_text(replace_block(content, block), encoding="utf-8")


def update_homepage(stats: Dict[str, object]) -> None:
    homepage = DOCS_DIR / "README.md"
    if not homepage.exists():
        return

    content = homepage.read_text(encoding="utf-8")
    block = render_stats_block(stats["total_articles"], stats["last_update"])
    homepage.write_text(replace_block(content, block), encoding="utf-8")


def generate_index_page(stats: Dict[str, object]) -> None:
    index_path = DOCS_DIR / "index.md"

    recent_files = sorted(
        list_markdown_files(ARTICLE_CATEGORIES["全部研报"]),
        key=lambda p: p.stem,
        reverse=True,
    )[:8]

    recent_lines = []
    for file_path in recent_files:
        rel_path = file_path.relative_to(DOCS_DIR).as_posix()
        title = file_path.stem
        recent_lines.append(f"- [{title}]({rel_path})")

    stats_block = render_stats_block(stats["total_articles"], stats["last_update"])

    content = "\n".join(
        [
            "# 🐊 鳄鱼派投资研报指数站",
            "",
            "> 每日自动收录最新研报，宏观与行业动向一站掌握",
            "",
            stats_block,
            "",
            "## 📚 快速导航",
            "- [📑 全部研报](全部研报/README.md)",
            "- [📈 宏观分析](宏观分析/README.md)",
            "- [🏭 行业分析](行业分析/README.md)",
            "",
            "## 🆕 最新收录",
        ]
        + (recent_lines or ["- 暂无最新内容，稍后再来看看吧。"])
        + [
            "",
            "## 🚀 使用建议",
            "- 使用左侧侧边栏快速切换分类",
            "- 利用搜索框按关键词定位研报",
            "- 每篇文章顶部会标注更新日期和阅读字数",
        ]
    )

    index_path.write_text(content + "\n", encoding="utf-8")


def main() -> None:
    ensure_structure()
    stats = generate_stats()
    update_category_readme(stats)
    update_homepage(stats)
    generate_index_page(stats)


if __name__ == "__main__":
    main()
