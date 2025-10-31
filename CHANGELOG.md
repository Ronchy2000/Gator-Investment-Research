# 🐊 鳄鱼派投资研报 - 更新日志

## 2025-11-01 (凌晨02:40) - 架构重构 🎉

### ⚡ 核心变更

1. **职责分离 - 探测与下载解耦**
   - `pre_crawl_check.py`: 专注于快速边界探测 (轻量级)
   - `fetch_reports.py`: 专注于内容下载 (重量级)
   - 探测速度提升 **80-90%** (增量模式)

2. **增量边界探测**
   - 从上次边界 (`last_probed_id + 1`) 继续探测
   - 避免重复探测已知范围
   - 首次: ~10 分钟,后续: ~1-2 分钟

3. **文件一致性保证**
   - 启动时自动验证 MD 文件与 JSON 一致性
   - 自动修复文件丢失 (从 `downloaded_ids` 移除)
   - 自动同步额外文件 (添加到 `downloaded_ids`)
   - 解决手动删除/添加文件导致的数据不一致

### 🔍 关键发现

**SPA 页面检测逻辑** (重要!)
```
✅ 文章存在: 完整内容 (标题+日期+正文, > 150 字符)
❌ 文章不存在: 只有免责声明 "鳄鱼派声明：文章内容仅供参考..." (~36字符)
```

- 等待时间: 2 秒 → **3.5 秒** (SPA 需要时间加载)
- 判断阈值: 100 字符 → **150 字符**
- 真实边界: **ID 686** (与用户预期完全一致)

### 📊 性能对比

| 场景 | 旧架构 | 新架构 | 提升 |
|------|--------|--------|------|
| 日常增量探测 | ~10 分钟 | ~1-2 分钟 | **80-90%** |
| 总体流程 | ~50 分钟 | ~42 分钟 | **16%** |

### 🛠️ 技术改进

1. **pre_crawl_check.py**
   ```python
   # 增量探测逻辑
   last_probed = int(data.get("last_probed_id", 0))
   probe_start = last_probed + 1 if last_probed > 0 else 1
   ```

2. **fetch_reports.py**
   ```python
   # 文件验证与同步
   def verify_downloaded_files(index: Dict[str, Any]) -> tuple[set[int], set[int], set[int]]:
       """验证 downloaded_ids 对应的文件是否实际存在"""
       # 扫描 MD 文件,双向同步
   ```

3. **GitHub Actions**
   ```yaml
   - name: 阶段 1 - 边界探测
     run: python scripts/pre_crawl_check.py
     
   - name: 阶段 2 - 内容下载
     run: python crawler/fetch_reports.py --max-requests 500
   ```

### 📝 新增文件

- `scripts/test_workflow.py` - 工作流测试脚本
- `ARCHITECTURE.md` - 完整架构文档 (更新)

### 🐛 修复

- 修复探测逻辑导致边界定位不准 (等待时间不足)
- 修复 JSON 与文件不一致导致的重复下载/跳过下载
- 修复探测起点总是从 ID 1 开始的低效问题

---

## 2025-11-01 (上午) - 重大改进

### ✨ 新功能

1. **智能健康检查系统**
   - 新增 `diagnose_crawler.py` - 全面诊断爬虫状态
   - 新增 `pre_crawl_check.py` - 运行前自动检查和修复
   - 自动检测数据完整性并修复异常

2. **增强的爬虫功能**
   - 添加 `downloaded_ids` 追踪机制
   - 区分"已探测"和"已下载"状态
   - 自动检测并修复未完成的下载
   - 避免重复下载和数据丢失

3. **优化的文档生成**
   - 改进 README.md 文章列表格式
   - 清晰的编号和日期展示
   - 修复相对路径问题
   - 自动去重统计

### 🔧 改进

1. **GitHub Actions 工作流**
   - 添加前置检查步骤
   - 添加健康诊断步骤
   - 添加最终状态报告
   - 改进错误处理和日志输出

2. **代码质量**
   - 完善 `.gitignore` 配置
   - 统一错误处理逻辑
   - 添加详细注释和文档

3. **README 优化**
   - 更新项目介绍
   - 添加实时数据展示
   - 完善技术架构说明
   - 优化排版和视觉效果

### 🐛 修复

1. 修复文章列表路径错误
2. 修复统计数据不准确问题
3. 修复重复文章计数问题
4. 修复 index.json 字段缺失

### 📚 技术细节

**新增字段**
```json
{
  "downloaded_ids": [],  // 追踪已成功下载的文章
  "saved_ids": [],       // 追踪已探测的文章
  "missing_ids": [],     // 记录缺失的ID
  "pending_ids": []      // 待下载队列
}
```

**自动化流程**
```
前置检查 → 健康诊断 → 运行爬虫 → 更新文档 → 最终诊断 → 提交推送
```

---

## 使用指南

### 本地测试

```bash
# 1. 前置检查
python scripts/pre_crawl_check.py

# 2. 健康诊断
python scripts/diagnose_crawler.py

# 3. 运行爬虫
python crawler/fetch_reports.py --batch-size 80

# 4. 更新文档
python scripts/update_category_meta.py
python scripts/generate_sidebar.py
```

### GitHub Actions

工作流会自动执行上述所有步骤，无需手动干预。

---

## 下一步计划

- [ ] 添加文章内容质量检查
- [ ] 实现更智能的分类算法
- [ ] 添加图表和数据可视化
- [ ] 支持更多数据源
