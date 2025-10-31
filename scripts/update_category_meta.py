"""
Update category README statistics blocks based on the latest crawl results.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Iterable, List

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
ARTICLES_START = "<!-- articles:start -->"
ARTICLES_END = "<!-- articles:end -->"


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


def render_articles_block(files: Iterable[Path], category_name: str) -> str:
    """生成文章列表区块，带清晰的标题和结构"""
    from urllib.parse import quote
    
    lines = [ARTICLES_START, "", "## 📄 文章列表", ""]
    
    if not files:
        lines.append("> 暂无内容，稍后再来看看吧。")
        lines.append("")
        lines.append(ARTICLES_END)
        return "\n".join(lines)
    
    # 按日期分组展示（从新到旧）
    for idx, file_path in enumerate(files, 1):
        title = file_path.stem
        
        # 提取日期和标题
        if len(title) > 11 and title[4] == "." and title[7] == "." and title[10] == "-":
            date_part = title[:10]
            title_part = title[11:]
        else:
            date_part = ""
            title_part = title
        
        # 构建相对路径（从当前分类目录，只需文件名）
        # URL 编码文件名以支持中文和空格
        rel_path = quote(file_path.name)
        
        # 格式化输出
        if date_part:
            lines.append(f"{idx}. **[{title_part}]({rel_path})** - `{date_part}`")
        else:
            lines.append(f"{idx}. **[{title_part}]({rel_path})**")
    
    lines.append("")
    lines.append(f"> 共 {len(list(files))} 篇研报")
    lines.append("")
    lines.append(ARTICLES_END)
    return "\n".join(lines)


def replace_articles_block(content: str, block: str) -> str:
    if ARTICLES_START in content and ARTICLES_END in content:
        start = content.index(ARTICLES_START)
        end = content.index(ARTICLES_END) + len(ARTICLES_END)
        return content[:start] + block + content[end:]
    if content.endswith("\n"):
        return content + block + "\n"
    return content + "\n" + block + "\n"


def update_category_readme(stats: Dict[str, object]) -> None:
    category_counts: Dict[str, int] = stats.get("categories", {})

    for category, path in ARTICLE_CATEGORIES.items():
        readme_path = path / "README.md"
        if not readme_path.exists():
            continue

        files: List[Path] = sorted(
            list_markdown_files(path),
            key=lambda p: p.stem,
            reverse=True,
        )
        last_update = (
            stats["last_update"]
            if category == "全部研报"
            else get_last_update_from_files(files)
        )
        content = readme_path.read_text(encoding="utf-8")
        block = render_stats_block(category_counts.get(category, 0), last_update)
        content = replace_block(content, block)
        articles_block = render_articles_block(files, category)
        content = replace_articles_block(content, articles_block)
        readme_path.write_text(content, encoding="utf-8")
        
        print(f"✅ 更新 {category} README: {len(list(files))} 篇文章")


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
