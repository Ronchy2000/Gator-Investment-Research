# 🐊 鳄鱼派投资研报自动化系统

<div align="center">

![Logo](https://img.icons8.com/color/150/000000/alligator.png)

**全天候投资风向标 · 自动化研报收录与展示平台**

[![GitHub stars](https://img.shields.io/github/stars/ronchy2000/Python_Study?style=social)](https://github.com/ronchy2000/Python_Study)
[![GitHub forks](https://img.shields.io/github/forks/ronchy2000/Python_Study?style=social)](https://github.com/ronchy2000/Python_Study)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)

[在线文档](https://ronchy2000.github.io/Python_Study/爬虫学习/鳄鱼派研报/wiki_Gator_Investment_Research/docs/) | [快速开始](#快速开始) | [功能特性](#功能特性) | [技术架构](#技术架构)

</div>

---

## 📖 项目简介

**鳄鱼派投资研报**是一个完全自动化的投资研究报告收录和展示平台。系统通过智能爬虫技术，每日自动从互联网抓取最新的投资研报，经过智能分类和格式化处理后，以 Markdown 文档的形式展示在基于 Docsify 构建的在线文档中。

### 💡 项目亮点

- ✅ **零配置部署** - 使用 Playwright 自动下载浏览器驱动，无需手动配置 ChromeDriver
- 🤖 **全自动更新** - GitHub Actions 每日定时任务，自动抓取、分类、提交
- 📊 **智能分类** - 自动识别研报类型（宏观分析/行业分析），精准归档
- 🔍 **全文搜索** - 支持关键词搜索，快速定位目标内容
- 📱 **响应式界面** - Docsify 框架，完美支持桌面和移动端
- 📈 **实时统计** - 自动生成文章统计信息和访问量数据

### 📊 当前数据

- 📚 **总文章数**: 140+ 篇
- 📑 **全部研报**: 10 篇
- 📈 **宏观分析**: 8 篇  
- 🏭 **行业分析**: 122 篇
- 🔄 **更新频率**: 每日自动更新

---

## 🚀 快速开始

### 环境要求

- Python 3.12+
- Git
- 互联网连接（Playwright 首次运行会自动下载浏览器）

### 本地运行

```bash
# 1. 克隆项目
git clone https://github.com/ronchy2000/Python_Study.git
cd Python_Study/爬虫学习/鳄鱼派研报/wiki_Gator_Investment_Research

# 2. 安装依赖
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium

# 3. 运行爬虫抓取研报
python3 crawler/fetch_reports.py --batch-size 50 --max-miss 20

# 4. 更新文档与统计
python3 scripts/update_category_meta.py
python3 scripts/generate_sidebar.py

# 5. 本地预览文档（需要安装 docsify-cli）
npm i docsify-cli -g
cd ../docs
docsify serve .
```

访问 `http://localhost:3000` 查看文档。

### 部署到 GitHub Pages

1. **Fork 本项目**到你的 GitHub 账号

2. **启用 GitHub Pages**:
   - 进入仓库 Settings → Pages
   - Source 选择 `main` 分支
  - Folder 选择 `/docs`（如果仍位于 Python_Study 仓库中，请选择 `/爬虫学习/鳄鱼派研报/wiki_Gator_Investment_Research/docs`）
   - 保存

3. **配置 GitHub Actions**（可选）:
   - Actions 已配置自动运行
   - 每天 UTC 0:00 (北京时间 8:00) 自动更新
   - 也可以手动触发: Actions → 每日自动更新研报 → Run workflow

4. **访问你的文档站点**:
   ```
   https://<your-username>.github.io/Python_Study/爬虫学习/鳄鱼派研报/wiki_Gator_Investment_Research/docs/
   ```

---

## ✨ 功能特性

### 🕷️ 智能爬虫系统

- **技术选型**: Playwright (替代传统 Selenium)
  - ✅ 自动管理浏览器驱动，首次运行自动下载
  - ✅ 支持 JavaScript 渲染的 SPA 页面
  - ✅ 反检测机制，模拟真实用户行为
  
- **内容处理**:
  - HTML → Markdown 自动转换
  - 保留文章结构（标题、列表、加粗、链接、图片）
  - 去除冗余样式和脚本，优化可读性

- **智能分类**:
  ```python
  # 基于关键词自动识别分类
  宏观分析: 宏观、政策、经济、市场趋势
  行业分析: 行业、产业、板块、细分领域
  ```

### 📑 自动化文档管理

- **侧边栏自动生成** (`generate_sidebar.py`):
  - 扫描所有 Markdown 文件
  - 统计各分类文章数量
  - 生成树形导航结构
  - 支持增量更新

- **统计信息更新** (`update_category_meta.py`):
  - 自动调用 `generate_stats.py` 生成 JSON 统计数据
  - 同步更新分类 README、首页、index.md
  - 记录最新抓取日期和总文章数

### 🔄 GitHub Actions 自动化

每日定时任务工作流 (`.github/workflows/daily-update.yml`):

```yaml
1. 运行爬虫 → 抓取最新研报
2. 生成导航 → 更新侧边栏
3. 生成统计 → 更新数据
4. 提交推送 → 自动部署
```

### 🎨 精美文档界面

基于 **Docsify** 框架，包含:
- 🔍 全文搜索插件
- 📖 字数统计和阅读时间
- 📄 上下篇翻页导航
- 🎯 代码高亮和复制
- 📊 访问量统计 (不蒜子)
- 🖼️ 图片缩放查看

---

## 🏗️ 技术架构

### 项目结构

```
wiki_Gator_Investment_Research/
├── .github/
│   └── workflows/
│       └── daily-update.yml          # GitHub Actions 工作流
├── config.py                         # 全局路径与目录定义
├── crawler/
│   └── fetch_reports.py              # Playwright 爬虫脚本
├── data/
│   └── raw_html/                     # 调试用原始页面（可选生成）
├── docs/                             # Docsify 文档目录
│   ├── index.html                    # Docsify 配置
│   ├── index.md                      # 首页索引（自动生成）
│   ├── README.md                     # 文档首页（自动更新统计）
│   ├── about.md                      # 关于页面
│   ├── _coverpage.md                 # 封面页
│   ├── _sidebar.md                   # 侧边栏（自动生成）
│   ├── stats.json                    # 统计数据（自动生成）
│   ├── 全部研报/                     # 研报分类目录
│   ├── 宏观分析/
│   └── 行业分析/
├── requirements.txt                  # Python 依赖
├── scripts/                          # 自动化脚本
│   ├── __init__.py
│   ├── generate_sidebar.py           # 侧边栏生成
│   ├── generate_stats.py             # 统计信息基础逻辑
│   └── update_category_meta.py       # 更新统计、首页与分类 README
└── README.md                         # 项目说明文档
```

### 技术栈

| 技术 | 用途 | 优势 |
|-----|------|------|
| **Playwright** | 网页爬虫 | 自动下载驱动，支持 SPA 渲染 |
| **BeautifulSoup** | HTML 解析 | 强大的内容提取和转换能力 |
| **Docsify** | 文档框架 | 轻量级，无需构建，插件丰富 |
| **GitHub Actions** | CI/CD | 免费定时任务，无缝集成 |
| **GitHub Pages** | 静态托管 | 免费、稳定、CDN 加速 |

### 核心流程

```mermaid
graph LR
    A[定时触发] --> B[Playwright 爬虫]
    B --> C[抓取研报内容]
    C --> D[HTML → Markdown]
    D --> E[智能分类]
    E --> F[保存到文件系统]
    F --> G[生成侧边栏]
    G --> H[生成统计信息]
    H --> I[Git 提交推送]
    I --> J[GitHub Pages 部署]
```

---

## 📚 使用说明

### 爬虫配置

爬虫脚本位于 `crawler/fetch_reports.py`，通过命令行参数即可控制抓取范围：

```bash
# 指定起止 ID
python3 crawler/fetch_reports.py --start-id 200 --end-id 230

# 或者自动从最新 ID 开始继续抓取 80 篇
python3 crawler/fetch_reports.py --batch-size 80 --max-miss 15

# 调试时保存原始 HTML
python3 crawler/fetch_reports.py --start-id 210 --end-id 212 --save-html --no-headless
```

主要参数说明：

- `--start-id / --end-id`：手动指定抓取区间
- `--batch-size`：未指定 end-id 时一次性尝试的数量（默认 50）
- `--max-miss`：连续缺失多少篇后停止，防止空跑
- `--sleep`：请求间隔控制，默认 1 秒，避免触发反爬
- `--save-html`：将原始页面保存到 `data/raw_html` 便于排查
- `--no-headless`：调试时打开浏览器窗口

### 自定义导航

侧边栏自动生成，无需手动编辑。如需自定义：

```bash
# 重新生成侧边栏
cd scripts
python generate_sidebar.py

# 重新生成统计
python update_category_meta.py
```

### GitHub Actions 触发

**自动触发**: 每天 UTC 0:00 (北京时间 8:00)

**手动触发**:
1. 进入 Actions 页面
2. 选择 "每日自动更新研报"
3. 点击 "Run workflow"

---

## 🤝 参与贡献

欢迎提交 Issue 和 Pull Request！

### 贡献方式

- 🐛 **报告 Bug**: [提交 Issue](https://github.com/ronchy2000/Python_Study/issues)
- 💡 **功能建议**: [发起 Discussion](https://github.com/ronchy2000/Python_Study/discussions)
- 📝 **改进文档**: 提交 PR 更新 Markdown 文件
- 🔧 **代码贡献**: Fork 后提交 PR

### 开发规范

- Python 代码遵循 **PEP 8** 风格
- Commit 信息采用 **约定式提交** 规范
- PR 请附上详细的变更说明

---

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。

---

## ⚠️ 免责声明

1. 本项目仅供**学习和研究**使用
2. 所有研报内容版权归**原作者**所有
3. 不构成任何**投资建议**
4. 投资有风险，决策需谨慎

---

## 🙏 致谢

- [Docsify](https://docsify.js.org/) - 优秀的文档生成工具
- [Playwright](https://playwright.dev/) - 现代化的浏览器自动化框架
- [GitHub Actions](https://github.com/features/actions) - 强大的 CI/CD 平台
- [Icons8](https://icons8.com/) - 提供精美图标资源

---

## 📞 联系方式

- **GitHub**: [@ronchy2000](https://github.com/ronchy2000)
- **项目主页**: [Python_Study](https://github.com/ronchy2000/Python_Study)
- **在线文档**: [Wiki 首页](https://ronchy2000.github.io/Python_Study/爬虫学习/鳄鱼派研报/wiki_Gator_Investment_Research/docs/)

---

<div align="center">

**如果觉得这个项目对你有帮助，欢迎 Star ⭐️**

Made with ❤️ by [ronchy2000](https://github.com/ronchy2000)

</div>
