# 鳄鱼派研报爬虫 - 架构说明

## 🏗️ 系统架构

本项目采用**两阶段爬取策略**,分离边界探测和内容下载:

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub Actions Daily Workflow                │
│                      (每天 UTC 0:00 执行)                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
         ┌────────────────────┴────────────────────┐
         │                                         │
    ┌────▼─────┐                            ┌─────▼────┐
    │ 阶段 1    │                            │ 阶段 2    │
    │ 边界探测  │                            │ 内容下载  │
    └──────────┘                            └──────────┘
         │                                         │
         │  scripts/pre_crawl_check.py            │  crawler/fetch_reports.py
         │  • 轻量级页面检查                       │  • 完整内容解析
         │  • 粗探测 (步长 50)                    │  • 增量下载
         │  • 细探测 (逐个检查)                   │  • Markdown 转换
         │  • 写入边界到 index.json               │  • 分类保存
         │                                         │
         └────────────┬────────────────────────────┘
                      │
                 ┌────▼─────┐
                 │  输出     │
                 │ index.json │
                 │ • 边界信息  │
                 │ • 已下载 ID │
                 │ • 缺失 ID   │
                 └───────────┘
```

---

## 🔍 核心发现: SPA 页面检测逻辑

### 关键特征 (2025-11-01 验证)

这是一个**单页应用 (SPA)**,所有 URL 都返回相同的 HTML 框架,真实内容通过 JavaScript 动态加载。

#### ✅ 文章存在的标识
```
页面长度: 通常 > 1000 字符
内容结构: 标题 + 日期 + 正文
示例 (ID 1):
  "AI计算机研报
   2025-05-13 14:45 星期二
   未来十年，无论是在工业，零售，司法，教育，都将会感受到AI的便捷..."
```

#### ❌ 文章不存在的标识
```
页面长度: 约 36-50 字符
唯一内容: "鳄鱼派声明：文章内容仅供参考，不构成投资建议。投资者据此操作，风险自担。"
```

### 检测代码 (核心逻辑)

```python
def check_article_exists(article_id: int, driver) -> bool:
    """
    ⚠️ 关键: 这是 SPA,需要等待 3.5 秒让 JS 加载完成
    
    判断标准:
    1. 文章不存在: 只有免责声明 (< 150 字符)
    2. 文章存在: 有完整内容 (> 150 字符)
    """
    url = f"http://h5.2025eyp.com/articles/{article_id}"
    driver.get(url)
    
    # 关键: 等待时间必须足够 (2 秒不够，3.5 秒稳定)
    time.sleep(3.5)
    
    body = driver.find_element(By.TAG_NAME, "body")
    visible_text = body.text.strip()
    
    # 只有免责声明 → 文章不存在
    if "鳄鱼派声明" in visible_text and len(visible_text) < 150:
        return False
    
    # 有实际内容 → 文章存在
    return len(visible_text) > 150
```

---

## 📝 脚本分工

### 1. `scripts/pre_crawl_check.py` - 边界探测

**职责**: 快速探测文章边界,不下载完整内容

**策略**:
- **增量探测**: 从上次边界 (`last_probed_id + 1`) 继续探测
- **粗探测**: 每隔 50 个 ID 采样 (快速定位大致边界)
- **细探测**: 在粗探测边界附近逐个检查 (精确定位)
- **停止条件**: 连续 10 个 ID 不存在

**输出**: 
```json
{
  "last_probed_id": 686,
  "next_probe_id": 687,
  "probe_history": [
    {"start": 687, "stop": 720, "found": 720, "ts": 1761935282}
  ]
}
```

**执行时间**: 
- 首次探测: ~5-10 分钟 (全量扫描 1-686)
- 增量探测: ~1-2 分钟 (只扫描新增部分 687+)

---

### 2. `crawler/fetch_reports.py` - 内容下载

**职责**: 下载文章完整内容并转换为 Markdown (**不再探测边界**)

**启动验证** (2025-11-01 新增):
```
1. 扫描所有 MD 文件,提取 article_id
2. 对比 downloaded_ids:
   - 文件丢失: JSON 有记录但文件不存在 → 从 downloaded_ids 移除
   - 额外文件: 文件存在但 JSON 无记录 → 添加到 downloaded_ids
3. 双向同步,确保 JSON 与文件一致
```

**模式**:
- **增量模式** (默认): 读取 `last_probed_id`,下载边界内未下载的文章
- **手动模式**: `--start-id` 和 `--end-id` 指定范围

**关键参数**:
```bash
--max-requests 500   # 单次最多下载 500 篇文章
--sleep 0.8          # 每次请求间隔 0.8 秒
```

**下载流程**:
1. **文件验证**: 扫描 MD 文件,同步 `downloaded_ids`
2. **读取边界**: 从 `index.json` 读取 `last_probed_id`
3. **计算待下载**: `[1, boundary] - downloaded_ids - missing_ids`
4. **批量下载**: 按顺序下载未下载的文章
5. **转换保存**: 转换为 Markdown 并保存到分类目录
6. **更新索引**: 更新 `downloaded_ids` 列表

**执行时间**: ~20-40 分钟 (取决于待下载文章数量)

---

## 🔢 边界信息

### 当前边界 (2025-11-01)
- **最大 ID**: 686
- **已探测**: 638 篇
- **已下载**: 638 篇
- **探测范围**: ID 1 - 686
- **分类统计**:
  - 全部研报: 638 篇
  - 宏观分析: 159 篇
  - 行业分析: 452 篇

### 历史变化
```
2025-06-14: ~468 篇 (旧逻辑,误判导致停止早)
2025-10-31: ~686 篇 (修复检测逻辑后正确边界)
2025-11-01: 638 篇完整下载 (增量下载完成,边界验证通过)
```

---

## ⚡ GitHub Actions 工作流

### 执行顺序
```
1. pre_crawl_check.py    → 边界探测 (5-10 分钟)
   └─ 输出: last_probed_id = 686 写入 index.json
   
2. fetch_reports.py      → 内容下载 (20-40 分钟)
   └─ 读取: last_probed_id = 686
   └─ 下载: [1, 686] 中未下载的文章
   
3. update_category_meta  → 更新分类元数据
4. generate_sidebar      → 生成侧边栏
5. diagnose_crawler      → 健康检查
```

### 配置参数
```yaml
- name: 阶段 1 - 边界探测
  run: python scripts/pre_crawl_check.py

- name: 阶段 2 - 内容下载
  run: python crawler/fetch_reports.py --max-requests 500 --sleep 0.8
```

---

## 🐛 常见问题

### 1. 为什么探测结果不准确?

**原因**: SPA 页面需要足够的等待时间让 JavaScript 执行
**解决**: 增加 `time.sleep(3.5)` (原来是 2 秒)

### 2. 为什么有些 ID 显示不存在但实际存在?

**原因**: 
- 等待时间不足 (< 3 秒)
- 判断阈值过严 (< 100 字符)

**解决**: 
- 等待时间: 2 秒 → 3.5 秒
- 判断阈值: 100 字符 → 150 字符

### 3. 为什么 ID 不连续?

**答**: 文章 ID 分布不连续是正常现象,可能原因:
- 文章被删除
- ID 预留但未发布
- 测试文章不公开

### 4. JSON 记录的 downloaded_ids 与实际文件不一致怎么办?

**场景**:
- 手动删除了 MD 文件,但 JSON 还有记录
- 手动添加了 MD 文件,但 JSON 没有记录

**解决** (2025-11-01 自动修复):
```bash
# fetch_reports.py 启动时会自动验证并同步
python crawler/fetch_reports.py
```

输出示例:
```
🔍 验证已下载文件...
⚠️  发现 5 篇文件丢失 (JSON 有记录但文件不存在)
   丢失 ID: [12, 45, 67, 89, 123]
📥 发现 3 篇额外文件 (文件存在但 JSON 未记录)
   额外 ID: [400, 401, 402]
✅ 已同步 downloaded_ids: 468 篇
```

### 5. 如何从头重新探测边界?

**方法 1**: 删除 `last_probed_id`
```bash
python -c "import json; d=json.load(open('docs/index.json')); d['last_probed_id']=0; open('docs/index.json','w').write(json.dumps(d,indent=2,ensure_ascii=False))"
```

**方法 2**: 手动编辑 `docs/index.json`
```json
{
  "last_probed_id": 0,
  "next_probe_id": 1
}
```

然后运行:
```bash
python scripts/pre_crawl_check.py
```

---

## 📊 性能指标

### 探测速度
- **粗探测**: ~0.5 秒/ID (步长 50)
- **细探测**: ~0.3 秒/ID (逐个检查)
- **完整探测**: ~5-10 分钟 (1-686)

### 下载速度
- **单篇文章**: ~1-2 秒
- **批量下载**: ~1500 篇/次 (约 30-40 分钟)

### 资源消耗
- **CPU**: 中等 (Selenium + Chrome)
- **内存**: ~500MB (Chrome headless)
- **网络**: ~100-200 请求/次

---

## 🔧 维护建议

### 1. 定期检查边界
```bash
python scripts/pre_crawl_check.py
```

### 2. 手动补漏
如果发现缺失的 ID,可以手动下载:
```bash
python crawler/fetch_reports.py --start-id 400 --end-id 450
```

### 3. 清理缓存
定期清理 `data/raw_html/` 中的临时文件

---

## 📚 相关文件

- `scripts/pre_crawl_check.py` - 边界探测脚本
- `crawler/fetch_reports.py` - 内容下载脚本
- `config.py` - 配置文件 (路径、分类等)
- `docs/index.json` - 索引文件 (边界、下载记录)
- `.github/workflows/daily-update.yml` - GitHub Actions 配置

---

## 🎯 未来优化

1. ~~**并发探测**: 使用多线程加速边界探测~~ (已优化: 增量探测)
2. ~~**智能重试**: 对失败的 ID 自动重试 3 次~~ (已实现: missing_ids 机制)
3. ~~**增量更新**: 只下载更新后的文章~~ (已实现: downloaded_ids 追踪)
4. **监控告警**: 边界变化、下载失败时发送通知
5. **内容去重**: 检测重复文章并合并
6. **质量评分**: 为研报添加质量评分系统

---

**最后更新**: 2025-11-01
**维护者**: @Ronchy2000
