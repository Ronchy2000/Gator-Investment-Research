"""
爬虫前置检查和边界探测脚本

核心功能：
1. 检查 index.json 结构完整性
2. 探测文章边界（粗探测 + 细探测）
3. 写入边界信息到 index.json
4. 供 fetch_reports.py 进行增量下载

探测策略：
- 粗探测：每隔 50 个 ID 采样，快速定位大致边界
- 细探测：在边界附近密集探测，确定精确边界
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import INDEX_FILE, ARTICLE_CATEGORIES

# 探测参数
COARSE_PROBE_STEP = 50      # 粗探测步长：每隔 50 个 ID 采样
COARSE_PROBE_MAX = 1500     # 粗探测上限：探测到 ID 1500
INITIAL_DENSE_PROBE_WINDOW = COARSE_PROBE_STEP  # 起点保护：先密集扫描首个区间，避免漏掉 852 这类非采样点
FINE_PROBE_RANGE = 50       # 细探测范围：从最后存在点往后探测 50 个 ID
FINE_PROBE_SAFETY = 3       # 细探测安全边界：往前回退 3 个 ID 作为起点
MAX_CONSECUTIVE_MISS = 25   # 连续缺失 25 个认为到达边界


def scan_existing_files() -> int:
    """
    扫描所有已下载文件，返回实际最大文章 ID
    
    用途：
    1. 验证文件与 JSON 一致性
    2. 决定是否需要进行边界探测
    3. 避免重复探测已知边界
    """
    max_id = 0
    for category_path in ARTICLE_CATEGORIES.values():
        if not category_path.exists():
            continue
        
        for md_file in category_path.glob("*.md"):
            if md_file.name.lower() == "readme.md":
                continue
            
            try:
                content = md_file.read_text(encoding="utf-8")
                match = re.search(r"^- 文章ID:\s*(\d+)", content, re.MULTILINE)
                if match:
                    max_id = max(max_id, int(match.group(1)))
            except Exception:
                continue
    
    return max_id


def should_skip_probe(index: dict) -> tuple[bool, str]:
    """
    判断是否需要跳过边界探测
    
    返回: (是否跳过, 原因说明)
    
    跳过条件：
    1. 实际文件最大 ID == 探测边界，且边界附近文件连续 → 无新文章
    2. 实际文件最大 ID < 探测边界 → 文件丢失，需要重新下载（但不需要探测）
       例外：若“探测边界本身”是 missing_ids（已知缺失边界），不能跳过，需继续向后探测
    
    需要探测：
    1. 首次运行（无历史边界）
    2. 边界内有缺失 ID
    3. 实际文件最大 ID > 探测边界（有手动添加的文件）
    """
    last_probed = int(index.get("last_probed_id", 0))
    
    # 首次运行，必须探测
    if last_probed == 0:
        return False, "首次探测"
    
    # 扫描实际文件
    actual_max_id = scan_existing_files()
    print(f"   实际文件最大 ID: {actual_max_id}")
    print(f"   上次探测边界: {last_probed}")
    
    # 情况 1: 实际文件最大 ID < 上次探测边界（文件丢失）
    if actual_max_id < last_probed:
        missing_ids = set(int(i) for i in index.get("missing_ids", []))

        # 关键修复：
        # 如果边界 ID 本身就是已知缺失（例如 last_probed=758, actual_max=757, missing_ids 含 758），
        # 继续跳过会导致后续新文章永远不再探测。
        if last_probed in missing_ids and actual_max_id == last_probed - 1:
            return False, (
                f"边界 ID {last_probed} 在 missing_ids 中（已知缺失），"
                f"继续从 ID {last_probed + 1} 探测新文章"
            )

        return True, f"实际文件最大 ID ({actual_max_id}) < 探测边界 ({last_probed})，文件可能丢失，请运行下载脚本补全"
    
    # 情况 2: 实际文件最大 ID == 上次探测边界（继续探测新文章）
    if actual_max_id == last_probed:
        downloaded_ids = set(int(i) for i in index.get("downloaded_ids", []))
        
        # 检查边界内是否有缺失的 ID 需要补全
        recent_range = range(max(1, last_probed - 9), last_probed + 1)
        missing_in_range = [i for i in recent_range if i not in downloaded_ids]
        
        if missing_in_range:
            return False, f"边界内有缺失 ID: {missing_in_range[:5]}{'...' if len(missing_in_range) > 5 else ''}，需要补全"
        
        # 边界内文章完整，但仍需探测是否有新文章 (last_probed + 1 往后)
        # 不能假设没有新文章，必须实际探测才能确认
        return False, f"边界内文章完整 (最大 ID {last_probed})，继续探测是否有新文章"
    
    # 情况 3: 实际文件最大 ID > 上次探测边界（有新文件）
    if actual_max_id > last_probed:
        print(f"   发现新文件: ID {last_probed + 1} - {actual_max_id}")
        # 更新边界到实际最大 ID
        index["last_probed_id"] = actual_max_id
        index["next_probe_id"] = actual_max_id + 1
        return False, f"发现手动添加的文件 (最大 ID {actual_max_id})，更新边界"
    
    return False, "需要探测"


def check_article_exists(article_id: int, driver) -> bool:
    """
    快速检查文章是否存在（不下载完整内容）
    使用 Selenium headless 模式，检查页面是否有实际内容
    
    ⚠️ 关键判断逻辑（2025-11-01 验证通过）：
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    1. 这是一个 SPA (单页应用)，所有页面返回相同的 HTML 框架
    2. 真实内容通过 JavaScript 异步加载，需要等待 3-4 秒
    3. 文章存在性判断依据：
       ✅ 存在: 页面加载后显示文章标题、日期、正文等内容 (长度 > 150 字符)
       ❌ 不存在: 页面只显示免责声明 "鳄鱼派声明：文章内容仅供参考，不构成投资建议。
                  投资者据此操作，风险自担。" (长度约 50 字符)
    4. 这个免责声明是判断文章不存在的关键标识！
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """
    url = f"http://h5.2025eyp.com/articles/{article_id}"
    
    try:
        driver.get(url)
        
        # 等待页面加载 (SPA 需要足够时间让 JS 执行完成)
        # 测试发现：2秒不够，3-4秒较稳定
        time.sleep(3.5)
        
        # 获取页面可见文本
        from selenium.webdriver.common.by import By
        body = driver.find_element(By.TAG_NAME, "body")
        visible_text = body.text.strip()
        
        # 判断逻辑：
        # 1. 如果内容很短 (< 150 字符) 且包含免责声明 → 文章不存在
        # 2. 如果只有免责声明 (长度约 50 字符) → 文章不存在
        # 3. 如果有较多内容 (> 150 字符) → 文章存在
        
        if "鳄鱼派声明" in visible_text and len(visible_text) < 150:
            # 只有免责声明，文章不存在
            return False
        
        # 有实际内容，文章存在
        return len(visible_text) > 150
        
    except Exception as e:
        print(f"    ⚠️  检查 ID {article_id} 时出错: {e}")
        return False


def coarse_probe_boundary(driver, start_id: int, max_id: int, step: int, original_boundary: int) -> int:
    """
    粗探测：快速定位边界范围
    返回：最后一个存在的采样点 ID
    
    ⚠️ 关键改进 (2025-11-01):
    - 如果没有找到任何存在的文章，返回原边界（避免回退）
    - 不允许边界回退到比原值更小的值
    """
    print(f"\n🔍 粗探测阶段 (步长 {step}，范围 {start_id}-{max_id})")
    print(f"   原边界: ID {original_boundary}")
    dense_end = min(max_id, start_id + INITIAL_DENSE_PROBE_WINDOW - 1)
    print(f"   起点保护: 先密集检查 ID {start_id}-{dense_end}")
    if dense_end < max_id:
        print(f"   后续采样: 从 ID {dense_end + 1} 起每隔 {step} 个 ID 采样")
    print("=" * 60)
    
    last_found_id = 0
    total_found = 0

    # 先把起点附近的首个区间顺扫一遍，避免仅检查 851/901/951... 这种固定采样线
    # 导致漏掉 852 这类“起点缺失、后一个 ID 存在”的新增文章。
    for article_id in range(start_id, dense_end + 1):
        exists = check_article_exists(article_id, driver)

        if exists:
            last_found_id = article_id
            total_found += 1
            print(f"  ✅ ID {article_id}: 存在 (起点密集扫描命中)")
        else:
            print(f"  ❌ ID {article_id}: 不存在")

        time.sleep(0.3)

    consecutive_miss = 0
    for article_id in range(dense_end + 1, max_id + 1, step):
        exists = check_article_exists(article_id, driver)
        
        if exists:
            last_found_id = article_id
            consecutive_miss = 0
            total_found += 1
            print(f"  ✅ ID {article_id}: 存在 (共找到 {total_found} 个采样点)")
        else:
            consecutive_miss += 1
            print(f"  ❌ ID {article_id}: 不存在 (连续缺失 {consecutive_miss})")
            
            # 连续 5 个采样点不存在 (约 250 个 ID 范围),认为接近边界
            if consecutive_miss >= 5:
                print(f"\n⚠️  连续 {consecutive_miss} 个采样点缺失 (约 {consecutive_miss * step} 个 ID)")
                break
        
        time.sleep(0.5)  # 避免请求过快
    
    # 关键改进：如果没找到任何存在的，保持原边界
    if last_found_id == 0:
        print(f"\n⚠️  粗探测未发现新文章，保持原边界 ID {original_boundary}")
        return original_boundary
    
    # 不允许边界回退
    if last_found_id < original_boundary:
        print(f"\n⚠️  新边界 ({last_found_id}) < 原边界 ({original_boundary})，保持原边界")
        return original_boundary
    
    print(f"\n📊 粗探测完成: 最后存在的采样点 ID {last_found_id}")
    return last_found_id


def fine_probe_boundary(driver, start_id: int, probe_range: int, original_boundary: int) -> int:
    """
    细探测：精确定位边界 ID
    从 start_id 开始往后探测 probe_range 个 ID
    返回：实际的最大文章 ID
    
    ⚠️ 关键改进 (2025-11-01):
    - 如果探测结果 < 原边界，保持原边界不变
    - 防止边界回退
    """
    print(f"\n🎯 细探测阶段 (范围 {start_id} - {start_id + probe_range})")
    print(f"   原边界: ID {original_boundary}")
    print("=" * 60)
    
    max_id = start_id - 1  # 初始化为起点前一个
    consecutive_miss = 0
    
    for article_id in range(start_id, start_id + probe_range + 1):
        exists = check_article_exists(article_id, driver)
        
        if exists:
            max_id = article_id
            consecutive_miss = 0
            print(f"  ✅ ID {article_id}: 存在")
        else:
            consecutive_miss += 1
            print(f"  ❌ ID {article_id}: 不存在 (连续缺失 {consecutive_miss})")
            
            # 连续 10 个 ID 不存在，认为已到达边界
            if consecutive_miss >= 10:
                print(f"\n✅ 连续 {consecutive_miss} 个 ID 缺失，确认边界在 ID {max_id}")
                break
        
        time.sleep(0.3)
    
    # 关键改进：防止边界回退
    if max_id < original_boundary:
        print(f"\n⚠️  新边界 ({max_id}) < 原边界 ({original_boundary})，保持原边界")
        return original_boundary
    
    print(f"\n🏁 细探测完成: 实际最大 ID {max_id}")
    return max_id


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
    
    # 4. 边界探测（核心功能）
    print("\n" + "=" * 60)
    print("🚀 开始边界探测")
    print("=" * 60)
    
    # 决定探测起点：从上次探测的边界继续 (增量探测)
    last_probed = int(data.get("last_probed_id", 0))
    
    # ⚠️ 新增：智能跳过逻辑
    should_skip, skip_reason = should_skip_probe(data)
    if should_skip:
        print(f"\n✅ 跳过边界探测: {skip_reason}")
        print(f"   当前边界: ID {last_probed}")
        print(f"   提示: 如有新文章更新，下次运行将自动探测")
        
        # 保存可能的修改（如手动文件导致的边界更新）
        if total_modified:
            INDEX_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        return 0
    
    print(f"\n📌 探测配置:")
    print(f"   原因: {skip_reason}")
    
    if last_probed > 0:
        # 增量模式：从上次边界继续
        probe_start = last_probed + 1
        print(f"   模式: 增量探测")
        print(f"   上次边界: ID {last_probed}")
        print(f"   本次起点: ID {probe_start}")
        print(f"   探测上限: ID {COARSE_PROBE_MAX}")
    else:
        # 首次探测：从头开始
        probe_start = 1
        print(f"   模式: 首次探测")
        print(f"   本次起点: ID {probe_start}")
        print(f"   探测上限: ID {COARSE_PROBE_MAX}")
    
    # 初始化 Selenium WebDriver
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    driver = webdriver.Chrome(options=options)
    
    try:
        # 粗探测：找到最后存在的采样点（传入原边界防止回退）
        coarse_boundary = coarse_probe_boundary(
            driver, 
            start_id=probe_start,
            max_id=COARSE_PROBE_MAX,
            step=COARSE_PROBE_STEP,
            original_boundary=last_probed
        )
        
        # 如果粗探测返回原边界，说明没有新文章，跳过细探测
        if coarse_boundary == last_probed and probe_start > last_probed:
            print(f"\n✅ 未发现新文章，边界保持在 ID {last_probed}")
            driver.quit()
            return 0
        
        # 细探测：从最后存在点往前 3 个作为安全边界，往后探测 50 个
        fine_start = max(1, coarse_boundary - FINE_PROBE_SAFETY)
        precise_boundary = fine_probe_boundary(
            driver,
            fine_start,
            probe_range=FINE_PROBE_RANGE,
            original_boundary=last_probed
        )
        
        # 只有当新边界 >= 原边界时才更新
        if precise_boundary >= last_probed:
            data["last_probed_id"] = precise_boundary
            data["next_probe_id"] = precise_boundary + 1
            
            # 添加探测历史
            if "probe_history" not in data:
                data["probe_history"] = []
            data["probe_history"].append({
                "start": probe_start,
                "stop": precise_boundary,
                "found": precise_boundary,
                "ts": int(time.time())
            })
            data["probe_history"] = data["probe_history"][-20:]
            
            total_modified = True
            
            print("\n✅ 边界探测完成")
            print(f"   原边界: ID {last_probed}")
            print(f"   新边界: ID {precise_boundary}")
            print(f"   新增范围: {precise_boundary - last_probed} 个 ID")
        else:
            print(f"\n⚠️  探测结果 ({precise_boundary}) 未超过原边界 ({last_probed})，保持原值")
        
    except Exception as e:
        print(f"\n❌ 边界探测失败: {e}")
        print("   将使用现有配置继续")
    finally:
        # 确保 driver 被正确关闭
        driver.quit()
    
    # 5. 保存修改
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
