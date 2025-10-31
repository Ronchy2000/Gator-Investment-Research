"""
生成统计信息 JSON 文件
用于 GitHub badges 和网站统计展示
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import (
    ARTICLE_CATEGORIES,
    STATS_FILE,
    INDEX_FILE,
    ensure_structure,
)


def list_markdown_files(path: Path) -> List[Path]:
    return [
        file_path
        for file_path in path.glob("*.md")
        if file_path.name.lower() != "readme.md"
    ]


def get_last_update_from_files(paths: Iterable[Path]) -> str:
    timestamps = [p.stat().st_mtime for p in paths if p.exists()]
    if not timestamps:
        return datetime.now().strftime("%Y-%m-%d")
    latest = max(timestamps)
    return datetime.fromtimestamp(latest).strftime("%Y-%m-%d")


def ensure_index_defaults(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    data.setdefault("saved_ids", [])
    data.setdefault("missing_ids", [])
    data.setdefault("pending_ids", [])
    data.setdefault("last_probed_id", 0)
    data.setdefault("next_probe_id", 1)
    return data


def load_index_data() -> Dict[str, Any]:
    if not INDEX_FILE.exists():
        return ensure_index_defaults({})
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ensure_index_defaults({})
    return ensure_index_defaults(data)


def generate_stats() -> Dict[str, object]:
    ensure_structure()

    category_counts: Dict[str, int] = {}
    all_files: List[Path] = []

    for category, path in ARTICLE_CATEGORIES.items():
        files = list_markdown_files(path)
        category_counts[category] = len(files)
        if category == "全部研报":
            all_files = files

    index_data = load_index_data()
    saved_ids = {int(i) for i in index_data.get("saved_ids", [])}
    missing_count = len({int(i) for i in index_data.get("missing_ids", [])})
    pending_count = len({int(i) for i in index_data.get("pending_ids", [])})

    index_total = len(saved_ids)
    total_articles = index_total if index_total else len(all_files)

    stats = {
        "last_update": get_last_update_from_files(all_files),
        "total_articles": total_articles,
        "categories": category_counts,
        "version": "1.2.0",
        "index": {
            "saved_total": index_total,
            "missing_total": missing_count,
            "pending_total": pending_count,
            "last_probed_id": index_data.get("last_probed_id", 0),
            "next_probe_id": index_data.get("next_probe_id", 1),
        },
    }

    STATS_FILE.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"✅ 统计信息生成成功: {STATS_FILE}")
    print(f"   总计: {total_articles} 篇")
    for category, count in category_counts.items():
        print(f"   - {category}: {count} 篇")
    print(f"   更新时间: {stats['last_update']}")
    print(f"   索引: 已保存 {index_total} | 缺失 {missing_count} | 待下载 {pending_count}")

    return stats


if __name__ == "__main__":
    generate_stats()
