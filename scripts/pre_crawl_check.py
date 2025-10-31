"""
爬虫前置检查和修复脚本
确保 index.json 结构完整，自动修复常见问题
用于 GitHub Actions 自动化流程
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import INDEX_FILE, ARTICLE_CATEGORIES


def ensure_index_structure(data: dict) -> tuple[dict, bool]:
    """确保 index.json 有所有必需的字段"""
    modified = False
    required_fields = {
        "saved_ids": [],
        "downloaded_ids": [],
        "missing_ids": [],
        "pending_ids": [],
        "last_probed_id": 0,
        "next_probe_id": 1,
        "probe_history": [],
    }
    
    for field, default_value in required_fields.items():
        if field not in data:
            data[field] = default_value
            modified = True
            print(f"   🔧 添加缺失字段: {field}")
    
    return data, modified


def sync_downloaded_with_files(data: dict) -> tuple[dict, bool]:
    """同步 downloaded_ids 与实际文件"""
    modified = False
    
    # 收集所有实际存在的文件名（去重）
    existing_files = set()
    for category, path in ARTICLE_CATEGORIES.items():
        if path.exists():
            for file in path.iterdir():
                if file.suffix == ".md" and file.name.lower() != "readme.md":
                    existing_files.add(file.stem)
    
    saved_ids = set(data.get("saved_ids", []))
    downloaded_ids = set(data.get("downloaded_ids", []))
    
    # 如果 downloaded_ids 为空，但有已保存的 ID，初始化它
    if not downloaded_ids and saved_ids:
        print(f"   🔧 初始化 downloaded_ids: {len(saved_ids)} 篇")
        data["downloaded_ids"] = sorted(list(saved_ids))
        modified = True
    
    # 检查 saved_ids 和 downloaded_ids 的一致性
    not_downloaded = saved_ids - downloaded_ids
    if not_downloaded and len(not_downloaded) == len(saved_ids):
        # 所有已探测的都未标记为已下载，自动同步
        print(f"   🔧 同步 downloaded_ids: {len(saved_ids)} 篇")
        data["downloaded_ids"] = sorted(list(saved_ids))
        modified = True
    
    return data, modified


def validate_and_clean(data: dict) -> tuple[dict, bool]:
    """验证和清理数据"""
    modified = False
    
    # 确保所有 ID 列表都是排序的
    for field in ["saved_ids", "downloaded_ids", "missing_ids", "pending_ids"]:
        if field in data and isinstance(data[field], list):
            original = data[field]
            cleaned = sorted(set(int(x) for x in original))
            if cleaned != original:
                data[field] = cleaned
                modified = True
                print(f"   🔧 清理并排序 {field}")
    
    # 验证 probe_history 长度
    if len(data.get("probe_history", [])) > 50:
        data["probe_history"] = data["probe_history"][-20:]
        modified = True
        print("   🔧 清理过长的 probe_history")
    
    # 验证 next_probe_id 的合理性
    saved_ids = data.get("saved_ids", [])
    if saved_ids:
        max_id = max(saved_ids)
        next_probe = data.get("next_probe_id", 1)
        if next_probe < max_id:
            data["next_probe_id"] = max_id + 1
            modified = True
            print(f"   🔧 修正 next_probe_id: {max_id + 1}")
    
    return data, modified


def main():
    """主函数"""
    print("🔍 开始前置检查...\n")
    
    # 1. 检查 index.json 是否存在
    if not INDEX_FILE.exists():
        print("⚠️  index.json 不存在，创建新文件")
        data = {
            "saved_ids": [],
            "downloaded_ids": [],
            "missing_ids": [],
            "pending_ids": [],
            "last_probed_id": 0,
            "next_probe_id": 1,
            "probe_history": [],
        }
        INDEX_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("✅ 已创建默认 index.json\n")
        return 0
    
    # 2. 读取并验证
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"❌ index.json 格式错误: {e}")
        print("   尝试备份并重新创建...")
        backup = INDEX_FILE.with_suffix(".json.backup")
        INDEX_FILE.rename(backup)
        print(f"   备份保存至: {backup}")
        return 1
    
    print("📋 当前状态:")
    print(f"   已探测: {len(data.get('saved_ids', []))} 篇")
    print(f"   已下载: {len(data.get('downloaded_ids', []))} 篇")
    print(f"   缺失记录: {len(data.get('missing_ids', []))} 个")
    print(f"   待下载: {len(data.get('pending_ids', []))} 个")
    print(f"   下次探测起点: ID {data.get('next_probe_id', 1)}\n")
    
    # 3. 执行检查和修复
    total_modified = False
    
    print("🔧 执行检查和修复:")
    data, mod1 = ensure_index_structure(data)
    data, mod2 = sync_downloaded_with_files(data)
    data, mod3 = validate_and_clean(data)
    
    total_modified = mod1 or mod2 or mod3
    
    if not total_modified:
        print("   ✅ 所有检查通过，无需修复")
    
    # 4. 保存修改
    if total_modified:
        INDEX_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print("\n💾 已保存修复后的 index.json")
    
    # 5. 最终报告
    print("\n" + "=" * 60)
    print("✅ 前置检查完成")
    print(f"   已探测: {len(data.get('saved_ids', []))} 篇")
    print(f"   已下载: {len(data.get('downloaded_ids', []))} 篇")
    print(f"   准备开始爬取...")
    print("=" * 60 + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
