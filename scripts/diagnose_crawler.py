"""
爬虫诊断和修复工具
检查 index.json 的完整性并提供修复建议
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


def count_actual_files() -> dict[str, int]:
    """统计实际存在的文件数量（去重）"""
    counts = {}
    all_files = set()  # 用于去重
    
    for category, path in ARTICLE_CATEGORIES.items():
        if path.exists():
            files = [
                f.name for f in path.iterdir()
                if f.suffix == ".md" and f.name.lower() != "readme.md"
            ]
            counts[category] = len(files)
            all_files.update(files)
        else:
            counts[category] = 0
    
    # 去重后的总数
    counts["total"] = len(all_files)
    counts["total_with_duplicates"] = sum(counts[k] for k in counts if k != "total")
    return counts


def diagnose():
    """诊断爬虫状态"""
    print("🔍 开始诊断爬虫状态...\n")
    
    # 1. 检查 index.json
    if not INDEX_FILE.exists():
        print("❌ index.json 文件不存在！")
        return
    
    with open(INDEX_FILE, encoding="utf-8") as f:
        index_data = json.load(f)
    
    saved_ids = set(index_data.get("saved_ids", []))
    downloaded_ids = set(index_data.get("downloaded_ids", []))
    missing_ids = set(index_data.get("missing_ids", []))
    pending_ids = set(index_data.get("pending_ids", []))
    
    print("📊 Index.json 状态:")
    print(f"   已探测文章: {len(saved_ids)} 篇")
    print(f"   已下载文章: {len(downloaded_ids)} 篇")
    print(f"   缺失记录: {len(missing_ids)} 个")
    print(f"   待下载: {len(pending_ids)} 个")
    print(f"   上次探测 ID: {index_data.get('last_probed_id', 0)}")
    print(f"   下次探测起点: {index_data.get('next_probe_id', 1)}")
    
    if saved_ids:
        print(f"   ID 范围: {min(saved_ids)} - {max(saved_ids)}")
    
    # 2. 统计实际文件
    print("\n📁 实际文件统计:")
    file_counts = count_actual_files()
    for category, count in file_counts.items():
        if category not in ("total", "total_with_duplicates"):
            print(f"   {category}: {count} 篇")
    print(f"   各分类总计: {file_counts['total_with_duplicates']} 篇 (含重复)")
    print(f"   去重后总计: {file_counts['total']} 篇")
    
    unique_count = file_counts['total']
    
    # 3. 分析问题
    print("\n🔎 问题分析:")
    
    # 问题1: 已探测但未下载
    not_downloaded = saved_ids - downloaded_ids
    if not_downloaded:
        print(f"   ⚠️  有 {len(not_downloaded)} 篇已探测但未下载")
        print(f"      ID: {sorted(list(not_downloaded))[:20]}{'...' if len(not_downloaded) > 20 else ''}")
    else:
        print("   ✅ 所有已探测的文章都已下载")
    
    # 问题2: 下载数量不匹配
    if len(downloaded_ids) != unique_count:
        diff = unique_count - len(downloaded_ids)
        if diff > 0:
            print(f"   ⚠️  实际文件比下载记录多 {diff} 篇")
            print(f"      可能原因: 同一文章保存到多个分类，或手动添加了文件")
        else:
            print(f"   ⚠️  下载记录比实际文件多 {-diff} 篇（文件可能被删除）")
    else:
        print("   ✅ 下载记录与去重后文件数量一致")
    
    # 问题3: ID 间隙
    if saved_ids:
        max_id = max(saved_ids)
        expected_count = max_id - len(missing_ids)
        actual_count = len(saved_ids)
        gap = expected_count - actual_count
        
        if gap > 50:
            print(f"   ⚠️  ID 范围内有大量间隙 (约 {gap} 个)")
            print(f"      建议运行扫描模式填补间隙")
    
    # 问题4: 待下载队列
    if pending_ids:
        print(f"   ⚠️  有 {len(pending_ids)} 篇文章在待下载队列")
        print(f"      建议运行爬虫完成下载")
    else:
        print("   ✅ 待下载队列为空")
    
    # 4. 建议
    print("\n💡 建议操作:")
    
    if not_downloaded:
        print("   1. 初始化 downloaded_ids (如果这些文章确实已存在):")
        print("      python scripts/fix_index.py --init-downloaded")
    
    if pending_ids:
        print("   2. 完成待下载队列:")
        print("      python crawler/fetch_reports.py")
    
    next_probe = index_data.get('next_probe_id', 1)
    if next_probe < 1000:  # 假设应该有更多文章
        print(f"   3. 继续探测新文章 (当前准备从 ID {next_probe} 开始):")
        print("      python crawler/fetch_reports.py --batch-size 100")
    
    if len(saved_ids) < 500:  # 如果总数少于预期
        print("   4. 考虑扫描历史区间填补缺失:")
        print("      python crawler/fetch_reports.py --start-id 1 --end-id 500")
    
    print("\n" + "=" * 60)
    print(f"诊断完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    diagnose()
