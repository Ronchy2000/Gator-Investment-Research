# 🐊 鳄鱼派投资研报

<div align="center">

![Logo](https://img.icons8.com/color/150/000000/alligator.png)

**真实研报每日同步 · 开源整理与展示**

[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/Ronchy2000/Gator-Investment-Research/daily-update.yml?label=daily-sync)](https://github.com/Ronchy2000/Gator-Investment-Research/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)

[📖 在线阅读](https://gator-investment-research.vercel.app/) | [📋 更新日志](CHANGELOG.md) | [🏗️ 技术架构](ARCHITECTURE.md)

</div>

---

## 📖 项目简介

**鳄鱼派投资研报**是一个开源项目，使用脚本每天同步券商与研究机构公开发布的研报，转成 Markdown 并按分类、日期归档，方便快速查阅。站内内容均为公开数据的原文呈现，不使用 AI 生成或润色。

### 💡 核心特性

- ✅ **真实来源** - 收录公开研报，保留标题与发布日期
- 📅 **按日同步** - 每天 08:00 (UTC+8) 更新新增内容
- 🗂️ **清晰分类** - 宏观/行业双分类，导航与全文搜索
- 📱 **多端适配** - 桌面、平板、手机均可流畅浏览
- 📈 **数据统计** - 自动生成数量与更新时间

### 📌 数据说明

- 只收录券商/研究机构公开发布的研报
- 网页内容转换为 Markdown，尽量保持原有结构
- 文件名记录日期与标题，便于按时间回溯
- 不使用 AI 生成或改写任何研报内容

### 📊 内容统计

> 数据来自每日同步的公开研报，分类随新增自动更新

```
📚 研报总数: 持续增长中（每日同步）
宏观分析: 政策、经济、市场趋势
🏭 行业分析: 多个重点行业与细分赛道
🔄 更新频率: 每日 08:00 (UTC+8)
```

---

## ✨ 功能特性

### 📄 内容展示

- **研报分类**: 宏观分析、行业分析双重分类体系，按日期归档
- **正文呈现**: Markdown 转换，尽量保留原文结构和重点
- **全文搜索**: 支持关键词搜索，快速定位内容
- **元数据提取**: 提取日期、分类等基础信息，便于筛选

### 🔄 自动化流程

系统采用自动化脚本每日运行：

**阶段 1: 增量探测**
- 记录上次抓取位置，继续查找新文章
- 处理 SPA 动态页面（等待 3.5s，阈值 150 字符）
- 性能表现：首次 ~10 分钟，日常增量 ~1-2 分钟

**阶段 2: 内容下载**
- 校验 JSON 与 Markdown 文件，保持数据一致
- 增量下载未收录的文章（单次最多 500 篇）
- HTML → Markdown 转换（支持表格、列表、图片）
- 自动更新分类和导航

详细架构说明请查看 [ARCHITECTURE.md](ARCHITECTURE.md)

---

## 🏗️ 技术架构

### 项目结构

```
Gator-Investment-Research/
├── .github/workflows/
│   └── daily-update.yml       # 自动化工作流
├── crawler/
│   └── fetch_reports.py       # 内容下载（阶段2）
├── scripts/
│   ├── pre_crawl_check.py     # 边界探测（阶段1）
│   ├── update_category_meta.py # 更新分类信息
│   ├── generate_sidebar.py    # 生成导航
│   └── diagnose_crawler.py    # 健康诊断
├── docs/                      # 文档目录（网站内容）
│   ├── index.json             # 索引数据
│   ├── 全部研报/
│   ├── 宏观分析/
│   └── 行业分析/
├── ARCHITECTURE.md            # 架构文档
├── CHANGELOG.md               # 更新日志
└── requirements.txt           # 依赖清单
```

### 技术栈

| 组件 | 技术 | 用途 |
|-----|------|------|
| **爬虫引擎** | Selenium | 浏览器自动化（SPA 支持） |
| **内容解析** | BeautifulSoup | HTML 解析转换 |
| **文档框架** | Docsify | 静态文档生成 |
| **自动化** | GitHub Actions | CI/CD 定时任务 |
| **托管服务** | GitHub Pages | 静态网站托管 |

---

## 📚 开发文档

### 核心脚本说明

**边界探测** (`scripts/pre_crawl_check.py`)
```bash
# 增量探测新文章边界
python scripts/pre_crawl_check.py
```

**内容下载** (`crawler/fetch_reports.py`)
```bash
# 下载未收录的文章（增量模式）
python crawler/fetch_reports.py --max-requests 500 --sleep 0.8
```

**完整参数说明**:
- `--max-requests 500`: 单次最多下载 500 篇
- `--sleep 0.8`: 请求间隔 0.8 秒（避免频率限制）

更多开发细节请参考 [ARCHITECTURE.md](ARCHITECTURE.md)

---

## 🤝 参与贡献

欢迎提出建议和改进意见！

- 🐛 [报告问题](https://github.com/Ronchy2000/Gator-Investment-Research/issues)
- 💡 [功能建议](https://github.com/Ronchy2000/Gator-Investment-Research/discussions)

---

## 📄 开源协议

MIT License © [Ronchy2000](https://github.com/Ronchy2000)

---

## ⚠️ 免责声明

1. 本项目仅供**学习和研究**使用
2. 研报内容版权归**原作者**所有，如有疑问请联系处理
3. 本项目不使用 AI 生成或改写研报，只做公开信息整理
4. 不构成任何**投资建议**；投资有风险，决策需谨慎

---

## 📜 相关文档

- [📋 CHANGELOG.md](CHANGELOG.md) - 版本更新日志
- [🏗️ ARCHITECTURE.md](ARCHITECTURE.md) - 技术架构详解

---

<div align="center">

**觉得不错？给个 Star ⭐️ 吧！**

Made with ❤️ by [Ronchy2000](https://github.com/Ronchy2000)

[🏠 在线阅读](https://gator-investment-research.vercel.app/) | [📮 反馈问题](https://github.com/Ronchy2000/Gator-Investment-Research/issues)

</div>
