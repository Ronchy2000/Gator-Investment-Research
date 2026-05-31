from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import ARTICLE_CATEGORIES, LEGACY_CATEGORY_DIRS, ensure_structure
from scripts.article_metadata import build_storage_filename, parse_article_metadata


def migrate_category(category: str) -> None:
    target_dir = ARTICLE_CATEGORIES[category]
    legacy_dir = LEGACY_CATEGORY_DIRS[category]

    target_dir.mkdir(parents=True, exist_ok=True)

    source_dirs = []
    if legacy_dir.exists():
        source_dirs.append(legacy_dir)
    if target_dir.exists() and target_dir != legacy_dir:
        source_dirs.append(target_dir)

    moved = 0
    preserved = 0

    for source_dir in source_dirs:
        for file_path in sorted(source_dir.glob("*.md")):
            if file_path.name.lower() == "readme.md":
                target_path = target_dir / "README.md"
            else:
                metadata = parse_article_metadata(file_path)
                target_path = target_dir / build_storage_filename(
                    metadata.article_id,
                    metadata.date,
                )

            if file_path.resolve() == target_path.resolve():
                preserved += 1
                continue

            if target_path.exists():
                if target_path.read_text(encoding="utf-8") != file_path.read_text(encoding="utf-8"):
                    raise RuntimeError(f"冲突文件内容不一致: {file_path} -> {target_path}")
                file_path.unlink()
                preserved += 1
                continue

            file_path.replace(target_path)
            moved += 1

    if legacy_dir.exists() and legacy_dir != target_dir:
        leftovers = list(legacy_dir.iterdir())
        if not leftovers:
            legacy_dir.rmdir()

    print(f"✅ {category}: 迁移 {moved} 个文件，保留 {preserved} 个文件")


def main() -> None:
    ensure_structure()
    for category in ARTICLE_CATEGORIES:
        migrate_category(category)


if __name__ == "__main__":
    main()
