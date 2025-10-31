# 🐊 鳄鱼派投资研报自动化系统

<div align="center">

![Logo](https://img.icons8.com/color/150/000000/alligator.png)

**全天候投资风向标 · 自动化研报收录与展示平台**

[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/Ronchy2000/Gator-Investment-Research/daily-update.yml?label=daily-sync)](https://github.com/Ronchy2000/Gator-Investment-Research/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/playwright-1.40+-green.svg)](https://playwright.dev/)

[📖 在线文档](https://ronchy2000.github.io/Gator-Investment-Research/) | [🚀 快速开始](#-快速开始) | [✨ 功能特性](#-功能特性) | [🏗️ 技术架构](#-技术架构)

</div>

---

## 📖 项目简介

**鳄鱼派投资研报**是一个完全自动化的投资研究报告收录和展示平台。系统每日通过智能爬虫自动抓取最新投资研报，经过智能分类和格式化处理后，以优雅的在线文档形式呈现。

### 💡 核心特性

- ✅ **零配置部署** - Playwright 自动管理浏览器驱动，开箱即用
- 🤖 **全自动运行** - GitHub Actions 定时任务，自动抓取、分类、发布
- 📊 **智能分类** - AI 识别研报类型（宏观/行业），自动归档
- 🔍 **全文搜索** - 支持关键词搜索，快速定位目标内容
- 📱 **响应式设计** - 完美适配桌面、平板、手机
- 📈 **实时统计** - 自动生成统计报表和数据可视化
- 🔧 **健康检查** - 自动诊断和修复索引数据

### 📊 实时数据

```
📚 总文章数: 292+ 篇
📑 全部研报: 162 篇
📈 宏观分析: 47 篇  
🏭 行业分析: 230 篇
🔄 更新频率: 每日 08:00 (UTC+8)
```

---

## 🚀 快速开始

### 前置要求

- Python 3.12+
- Git
- 互联网连接

### 本地运行

```bash
# 1. 克隆项目
git clone https://github.com/Ronchy2000/Gator-Investment-Research.git
cd Gator-Investment-Research

# 2. 安装依赖
pip install -r requirements.txt
playwright install chromium

# 3. 运行爬虫（增量更新模式）
python crawler/fetch_reports.py --batch-size 80

# 4. 更新文档
python scripts/update_category_meta.py
python scripts/generate_sidebar.py

# 5. 本地预览（需要 Node.js）
npm i -g docsify-cli
docsify serve docs
```

访问 `http://localhost:3000` 查看文档。

### 部署到 GitHub Pages

1. **Fork 本项目**

2. **启用 GitHub Pages**
   - Settings → Pages
   - Source: `main` 分支
   - Folder: `/docs`

3. **配置自动更新**（可选）
   - Actions 已预配置
   - 每天 UTC 00:00 自动运行
   - 可手动触发: Actions → Run workflow

4. **访问文档**
   ```
   https://<your-username>.github.io/Gator-Investment-Research/
   ```

---

## ✨ 功能特性

### 🕷️ 智能爬虫

**技术优势**
- 🎭 **Playwright** - 现代化浏览器自动化
  - 自动下载和管理浏览器驱动
  - 完美支持 JavaScript 渲染页面
  - 反检测机制，模拟真实用户
  
**内容处理**
- 🔄 HTML → Markdown 智能转换
- 📐 保留完整文档结构（标题/列表/链接/图片）
- 🎨 去除冗余样式，优化阅读体验
- 🏷️ 自动提取元数据（日期/分类/摘要）

**分类逻辑**
```python
宏观分析: 宏观、政策、经济、市场趋势、货币政策
行业分析: 行业、产业、板块、细分领域、公司研究
```

### 📑 文档管理

**自动化脚本**
- 📋 `generate_sidebar.py` - 生成导航侧边栏
- 📊 `generate_stats.py` - 生成统计数据
- 🔄 `update_category_meta.py` - 更新分类信息
- 🔍 `diagnose_crawler.py` - 健康检查诊断
- 🔧 `pre_crawl_check.py` - 前置数据修复

**智能功能**
- ✅ 自动统计文章数量
- ✅ 生成文章列表（按日期排序）
- ✅ 检测并修复数据异常
- ✅ 去重统计（同文章多分类）

### 🔄 CI/CD 流程

**GitHub Actions 工作流**

```mermaid
graph LR
    A[定时触发] --> B[前置检查]
    B --> C[健康诊断]
    C --> D[运行爬虫]
    D --> E[更新统计]
    E --> F[生成导航]
    F --> G[提交推送]
    G --> H[自动部署]
```

**执行步骤**
1. 🔧 前置检查 - 验证 index.json 完整性
2. 🔍 健康诊断 - 分析数据状态
3. 🚀 运行爬虫 - 增量抓取新文章
4. 📊 更新统计 - 生成最新数据
5. 📋 生成导航 - 更新侧边栏
6. 🔍 最终诊断 - 确认运行结果
7. 📝 提交推送 - 自动部署到 Pages

### 🎨 文档界面

**基于 Docsify 框架**

| 功能 | 描述 | 功能 | 描述 |
|-----|------|------|------|
| 🔍 全文搜索 | 快速定位内容 | 📖 阅读统计 | 字数与时间 |
| 📄 上下篇导航 | 连续阅读 | 🎯 代码高亮 | 一键复制 |
| 📊 访问统计 | 实时追踪 | 🖼️ 图片查看 | 放大预览 |

---

## 🏗️ 技术架构

### 项目结构

```
Gator-Investment-Research/
├── .github/
│   └── workflows/
│       └── daily-update.yml       # GitHub Actions 自动化
├── crawler/
│   └── fetch_reports.py           # Playwright 爬虫
├── scripts/
│   ├── generate_sidebar.py        # 生成侧边栏
│   ├── generate_stats.py          # 生成统计
│   ├── update_category_meta.py    # 更新元数据
│   ├── diagnose_crawler.py        # 健康诊断
│   └── pre_crawl_check.py         # 前置检查
├── docs/                          # 文档目录
│   ├── index.html                 # Docsify 配置
│   ├── index.json                 # 索引数据
│   ├── stats.json                 # 统计数据
│   ├── _sidebar.md                # 侧边栏（自动生成）
│   ├── 全部研报/
│   ├── 宏观分析/
│   └── 行业分析/
├── config.py                      # 配置文件
└── requirements.txt               # 依赖清单
```

### 技术栈

| 组件 | 技术 | 用途 |
|-----|------|------|
| **爬虫引擎** | Playwright | 浏览器自动化 |
| **内容解析** | BeautifulSoup | HTML 解析转换 |
| **文档框架** | Docsify | 静态文档生成 |
| **自动化** | GitHub Actions | CI/CD 流程 |
| **托管服务** | GitHub Pages | 静态网站托管 |

### 数据流转

```
网站内容 → Playwright 抓取 → HTML 解析 
  → Markdown 转换 → 智能分类 → 文件保存 
  → 索引更新 → 统计生成 → 导航构建 
  → Git 提交 → Pages 部署 → 用户访问
```

---

## 📚 使用指南

### 爬虫参数

```bash
# 增量模式（推荐）- 自动从上次结束位置继续
python crawler/fetch_reports.py --batch-size 80

# 手动指定范围
python crawler/fetch_reports.py --start-id 100 --end-id 200

# 调试模式
python crawler/fetch_reports.py --no-headless --save-html

# 完整参数
python crawler/fetch_reports.py \
  --batch-size 80 \        # 单次抓取数量
  --max-miss 20 \          # 连续缺失停止阈值
  --sleep 0.8              # 请求间隔（秒）
```

### 诊断工具

```bash
# 运行健康检查
python scripts/diagnose_crawler.py

# 前置数据修复
python scripts/pre_crawl_check.py

# 手动更新文档
python scripts/update_category_meta.py
python scripts/generate_sidebar.py
```

### GitHub Actions

**自动触发**: 每天 UTC 00:00 (北京时间 08:00)

**手动触发**:
1. 进入 Actions 页面
2. 选择 "Daily Gator Sync"
3. 点击 "Run workflow"

---

## 🤝 参与贡献

欢迎所有形式的贡献！

### 贡献方式

- 🐛 [报告 Bug](https://github.com/Ronchy2000/Gator-Investment-Research/issues/new)
- 💡 [功能建议](https://github.com/Ronchy2000/Gator-Investment-Research/discussions)
- 📝 改进文档
- 🔧 提交代码

### 开发规范

- 遵循 PEP 8 代码风格
- 提交信息采用约定式提交
- PR 附带详细变更说明

---

## 📄 开源协议

MIT License © [Ronchy2000](https://github.com/Ronchy2000)

---

## ⚠️ 免责声明

1. 本项目仅供**学习和研究**使用
2. 研报内容版权归**原作者**所有
3. 不构成任何**投资建议**
4. 投资有风险，决策需谨慎

---

## 🙏 致谢

- [Docsify](https://docsify.js.org/) - 文档生成工具
- [Playwright](https://playwright.dev/) - 浏览器自动化
- [GitHub Actions](https://github.com/features/actions) - CI/CD 平台
- [Icons8](https://icons8.com/) - 图标资源

---

<div align="center">

**觉得不错？给个 Star ⭐️ 吧！**

Made with ❤️ by [Ronchy2000](https://github.com/Ronchy2000)

[🏠 首页](https://ronchy2000.github.io/Gator-Investment-Research/) | [📊 统计](https://ronchy2000.github.io/Gator-Investment-Research/#/stats) | [📮 反馈](https://github.com/Ronchy2000/Gator-Investment-Research/issues)

</div>
