# 🐊 鳄鱼派投资研报

<div align="center">

![Logo](https://img.icons8.com/color/150/000000/alligator.png)

**全天候投资风向标 · 自动化研报收录与展示平台**

[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/Ronchy2000/Gator-Investment-Research/daily-update.yml?label=daily-sync)](https://github.com/Ronchy2000/Gator-Investment-Research/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)

[📖 在线阅读](https://ronchy2000.github.io/Gator-Investment-Research/) | [� 更新日志](CHANGELOG.md) | [🏗️ 技术架构](ARCHITECTURE.md)

</div>

---

## 📖 项目简介

**鳄鱼派投资研报**是一个完全自动化的投资研究报告收录和展示平台。系统每日自动抓取最新投资研报，经过智能分类和格式化处理后，以优雅的在线文档形式呈现。

### 💡 核心特性

- 🤖 **全自动运行** - 每日 08:00 (UTC+8) 自动更新内容
- 📊 **智能分类** - 自动识别宏观/行业分析，智能归档
- 🔍 **全文搜索** - 支持关键词搜索，快速定位内容
- 📱 **响应式设计** - 完美适配桌面、平板、手机
- 📈 **实时统计** - 自动生成统计报表（由脚本自动更新）

### 📊 内容统计

> 数据由自动化脚本实时更新

```
📚 研报总数: 持续增长中
 宏观分析: 涵盖政策、经济、市场趋势
🏭 行业分析: 覆盖多个行业和细分领域
🔄 更新频率: 每日 08:00 (UTC+8)
```

---

## ✨ 功能特性

### � 内容展示

- **研报分类**: 宏观分析、行业分析双重分类体系
- **智能识别**: 根据关键词自动归类（宏观、政策、经济 / 行业、产业、板块）
- **格式优化**: Markdown 格式，清晰易读
- **元数据提取**: 自动提取日期、分类、摘要信息

### 🔄 自动化流程

系统采用 **自动化网站构建技术**，每日自动运行：

**阶段 1: 边界探测**
- 增量探测新文章边界（从上次探测位置继续）
- 智能检测 SPA 动态页面（等待 3.5s，阈值 150 字符）
- 性能优化：首次 ~10 分钟，增量 ~1-2 分钟（提升 80-90%）

**阶段 2: 内容下载**
- 文件验证与双向同步（JSON ↔ MD 文件）
- 增量下载未收录的文章（单次最多 500 篇）
- HTML → Markdown 智能转换（支持表格、列表、图片）
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
2. 研报内容版权归**原作者**所有
3. 不构成任何**投资建议**
4. 投资有风险，决策需谨慎

---

## � 相关文档

- [📋 CHANGELOG.md](CHANGELOG.md) - 版本更新日志
- [🏗️ ARCHITECTURE.md](ARCHITECTURE.md) - 技术架构详解

---

<div align="center">

**觉得不错？给个 Star ⭐️ 吧！**

Made with ❤️ by [Ronchy2000](https://github.com/Ronchy2000)

[🏠 在线阅读](https://gator-investment-research.vercel.app/) | [📮 反馈问题](https://github.com/Ronchy2000/Gator-Investment-Research/issues)

</div>
