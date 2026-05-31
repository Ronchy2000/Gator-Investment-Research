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

import json

from config import (
    ARTICLE_CATEGORIES,
    CATEGORY_DEFINITIONS,
    DOCS_DIR,
    category_slug,
    ensure_structure,
)
from scripts.article_metadata import build_legacy_filename, parse_article_metadata
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
    file_list = list(files)
    lines = [ARTICLES_START, "", "## 📄 文章列表", ""]
    
    if not file_list:
        lines.append("> 暂无内容，稍后再来看看吧。")
        lines.append("")
        lines.append(ARTICLES_END)
        return "\n".join(lines)
    
    # 按日期分组展示（从新到旧）
    for idx, file_path in enumerate(file_list, 1):
        metadata = parse_article_metadata(file_path)
        date_part = metadata.date or ""
        title_part = metadata.title
        rel_path = f"{category_slug(category_name)}/{file_path.name}"
        
        # 格式化输出
        if date_part:
            lines.append(f"{idx}. **[{title_part}]({rel_path})** - `{date_part}`")
        else:
            lines.append(f"{idx}. **[{title_part}]({rel_path})**")
    
    lines.append("")
    lines.append(f"> 共 {len(file_list)} 篇研报")
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


def normalize_internal_links(content: str) -> str:
    replacements = {
        "(/全部研报/)": "(all-reports/README.md)",
        "(/宏观分析/)": "(macro-analysis/README.md)",
        "(/行业分析/)": "(industry-analysis/README.md)",
    }
    for legacy, current in replacements.items():
        content = content.replace(legacy, current)
    return content


def update_category_readme(stats: Dict[str, object]) -> None:
    category_counts: Dict[str, int] = stats.get("categories", {})

    # 提取文章 ID 的辅助函数
    def extract_article_id(file_path: Path) -> int:
        metadata = parse_article_metadata(file_path)
        return metadata.article_id if metadata.article_id is not None else -1

    for category, path in ARTICLE_CATEGORIES.items():
        readme_path = path / "README.md"
        if not readme_path.exists():
            continue

        files: List[Path] = sorted(
            list_markdown_files(path),
            key=extract_article_id,  # 改为按文章 ID 排序
            reverse=True,
        )
        last_update = (
            stats["last_update"]
            if category == "全部研报"
            else get_last_update_from_files(files)
        )
        content = readme_path.read_text(encoding="utf-8")
        content = normalize_internal_links(content)
        block = render_stats_block(category_counts.get(category, 0), last_update)
        content = replace_block(content, block)
        articles_block = render_articles_block(files, category)
        content = replace_articles_block(content, articles_block)
        readme_path.write_text(content, encoding="utf-8")
        
        print(f"✅ 更新 {category} README: {len(list(files))} 篇文章")


def update_homepage(stats: Dict[str, object]) -> None:
    """更新 HOME.md 的统计块和最新收录列表"""
    homepage = DOCS_DIR / "HOME.md"
    if not homepage.exists():
        return

    content = homepage.read_text(encoding="utf-8")
    
    # 更新统计块
    stats_block = render_stats_block(stats["total_articles"], stats["last_update"])
    content = replace_block(content, stats_block)
    
    # 更新最新收录列表
    all_files = list(list_markdown_files(ARTICLE_CATEGORIES["全部研报"]))

    def extract_article_id(file_path: Path) -> int:
        metadata = parse_article_metadata(file_path)
        return metadata.article_id if metadata.article_id is not None else -1

    # 获取最新 8 篇文章
    recent_files = sorted(all_files, key=extract_article_id, reverse=True)[:8]
    
    latest_lines = [
        "### 🆕 最新收录",
        "",
        "<!-- latest:start -->",
        "",
        "以下是最近收录的 8 篇研报（按文章 ID 降序排列）：",
        "",
    ]
    
    for file_path in recent_files:
        metadata = parse_article_metadata(file_path)
        rel_path = f"all-reports/{file_path.name}"
        title = metadata.title
        article_id = metadata.article_id or -1
        if article_id > 0:
            latest_lines.append(f"- [{title}]({rel_path}) - **文章ID: {article_id}**")
        else:
            latest_lines.append(f"- [{title}]({rel_path})")
    
    latest_lines.extend([
        "",
        f"[查看所有 {stats['total_articles']} 篇研报 →](all-reports/README.md)",
        "",
        "<!-- latest:end -->",
    ])
    
    latest_block = "\n".join(latest_lines)
    
    # 替换最新收录块
    LATEST_START = "<!-- latest:start -->"
    LATEST_END = "<!-- latest:end -->"
    
    if LATEST_START in content and LATEST_END in content:
        start = content.index(LATEST_START)
        # 找到前面的标题行
        title_start = content.rfind("### 🆕 最新收录", 0, start)
        if title_start != -1:
            start = title_start
        end = content.index(LATEST_END) + len(LATEST_END)
        content = content[:start] + latest_block + content[end:]
    
    homepage.write_text(content, encoding="utf-8")
    print("✅ 更新 HOME.md (统计 + 最新收录)")


def generate_index_page(stats: Dict[str, object]) -> None:
    index_path = DOCS_DIR / "index.md"
    
    # 获取所有文章
    all_files = list(list_markdown_files(ARTICLE_CATEGORIES["全部研报"]))
    
    # 提取每个文件的 ID
    def extract_article_id(file_path: Path) -> int:
        metadata = parse_article_metadata(file_path)
        return metadata.article_id if metadata.article_id is not None else -1
    
    # 按 ID 倒序排序（ID 越大越新）
    recent_files = sorted(
        all_files,
        key=extract_article_id,
        reverse=True,
    )[:8]

    recent_lines = []
    for file_path in recent_files:
        rel_path = f"all-reports/{file_path.name}"
        metadata = parse_article_metadata(file_path)
        title = metadata.title
        article_id = metadata.article_id if metadata.article_id is not None else -1
        # 显示 ID 方便调试
        if article_id > 0:
            recent_lines.append(f"- [{title}]({rel_path}) `#{article_id}`")
        else:
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
            "- [📑 全部研报](all-reports/README.md)",
            "- [📈 宏观分析](macro-analysis/README.md)",
            "- [🏭 行业分析](industry-analysis/README.md)",
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


def generate_legacy_route_map() -> None:
    legacy_map: Dict[str, str] = {}
    legacy_dirs = {item["label"]: item["legacy_dir"] for item in CATEGORY_DEFINITIONS}

    for category, path in ARTICLE_CATEGORIES.items():
        slug = category_slug(category)
        legacy_dir = legacy_dirs[category]

        for file_path in list_markdown_files(path):
            metadata = parse_article_metadata(file_path)
            legacy_filename = build_legacy_filename(metadata.title, metadata.date)
            new_path = f"/{slug}/{file_path.stem}"

            legacy_map[f"/{legacy_dir}/{Path(legacy_filename).stem}"] = new_path
            legacy_map[f"/{legacy_dir}/{legacy_filename}"] = new_path
            if file_path.name.lower() == "readme.md":
                legacy_map[f"/{legacy_dir}/"] = f"/{slug}/README"

        legacy_map[f"/{legacy_dir}/README"] = f"/{slug}/README"
        legacy_map[f"/{legacy_dir}/README.md"] = f"/{slug}/README"
        legacy_map[f"/{legacy_dir}"] = f"/{slug}/README"

    route_map_path = DOCS_DIR / "legacy-routes.json"
    route_map_path.write_text(
        json.dumps(legacy_map, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✅ 更新旧路径映射: {route_map_path}")


def main() -> None:
    ensure_structure()
    stats = generate_stats()
    update_category_readme(stats)
    update_homepage(stats)
    generate_legacy_route_map()
    # generate_index_page(stats)  # 不再需要 index.md，HOME.md 已包含最新收录


if __name__ == "__main__":
    main()
