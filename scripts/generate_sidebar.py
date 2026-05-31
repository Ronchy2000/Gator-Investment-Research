"""
自动生成 docsify 侧边栏导航文件
扫描 docs/ 下的分类目录，生成 _sidebar.md
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import ARTICLE_CATEGORIES, SIDEBAR_FILE, DOCS_DIR, category_slug, ensure_structure
from scripts.article_metadata import parse_article_metadata
from scripts.generate_stats import get_last_update_from_files, list_markdown_files


def count_articles(category_path: Path) -> int:
    """统计指定分类目录下的文章数量"""
    if not category_path.exists():
        return 0
    return len(
        [
            f
            for f in category_path.iterdir()
            if f.suffix == ".md" and f.name.lower() != "readme.md"
        ]
    )


def get_article_list(category_path: Path) -> List[Tuple[str, str]]:
    """获取分类下所有文章的列表 (标题, 相对路径)"""
    articles: List[Tuple[str, str]] = []
    if not category_path.exists():
        return articles

    for file_path in sorted(category_path.iterdir()):
        if file_path.suffix != ".md" or file_path.name.lower() == "readme.md":
            continue

        title = parse_article_metadata(file_path).title
        rel_path = file_path.relative_to(DOCS_DIR).as_posix()
        articles.append((title, rel_path))

    return articles


def generate_sidebar(top_n: int = 10) -> None:
    """生成侧边栏导航文件"""
    ensure_structure()

    sidebar_lines = [
        "<!-- 侧边栏导航 - 自动生成 -->",
        "",
        "* [🏠 首页](HOME.md)",
        "* [📊 关于项目](about.md)",
        "",
    ]

    total_articles = 0
    all_files = []

    for category, path in ARTICLE_CATEGORIES.items():
        article_count = count_articles(path)
        total_articles += article_count
        all_files.extend(list_markdown_files(path))

        icon = {"宏观分析": "📈", "行业分析": "🏭"}.get(category, "📑")

        sidebar_lines.append(f"* {icon} **{category}({article_count})**")

        articles = get_article_list(path)
        for title, rel_path in articles[:top_n]:
            sidebar_lines.append(f"  * [{title}]({rel_path})")

        if len(articles) > top_n:
            readme_rel = f"{category_slug(category)}/README.md"
            sidebar_lines.append(
                f"  * [... 查看更多 {len(articles) - top_n} 篇]({readme_rel})"
            )

        sidebar_lines.append("")

    last_update = get_last_update_from_files(all_files)
    sidebar_lines.extend([
        "---",
        "",
        f"* 📚 **总计: {total_articles} 篇**",
        f"* 🔄 最后更新: {last_update}",
        "",
    ])

    SIDEBAR_FILE.write_text("\n".join(sidebar_lines), encoding="utf-8")

    print(f"✅ 侧边栏生成成功: {SIDEBAR_FILE}")
    print(f"   总计 {total_articles} 篇文章")
    for category, path in ARTICLE_CATEGORIES.items():
        print(f"   - {category}: {count_articles(path)} 篇")


if __name__ == "__main__":
    generate_sidebar()
