# 关于项目 📋

## 🎯 项目简介

**鳄鱼派投资研报**是一个全自动化的投资研究报告收录和展示平台。通过智能爬虫技术，每日自动从互联网抓取最新的投资研报，经过智能分类和格式化处理后，以 Markdown 文档的形式呈现，为投资者提供便捷的研报查阅服务。

### 为什么叫"鳄鱼派"？

鳄鱼是自然界中的顶级猎食者，以其耐心、精准的捕猎策略著称。在投资领域，我们希望像鳄鱼一样：
- 🎯 **精准捕捉**: 自动筛选高质量研报
- ⏱️ **耐心等待**: 每日定时更新，不错过任何机会
- 🔍 **洞察全局**: 覆盖宏观和行业多个维度

## 🏗️ 技术架构

### 核心组件

```
鳄鱼派投资研报系统
├── 爬虫模块 (Selenium)
│   ├── 自动抓取研报内容
│   ├── HTML 转 Markdown
│   └── 智能分类识别
├── 文档管理 (Docsify)
│   ├── 响应式文档展示
│   ├── 全文搜索功能
│   └── 自动生成导航
└── 自动化部署 (GitHub Actions)
    ├── 定时任务触发
    ├── 内容自动更新
    └── 统计信息生成
```

### 技术选型

| 技术 | 用途 | 优势 |
|-----|------|------|
| **Selenium** | 网页爬虫 | 成熟稳定，支持动态页面渲染和等待 |
| **Docsify** | 文档框架 | 轻量级，无需构建步骤，支持插件扩展 |
| **GitHub Actions** | CI/CD | 免费的定时任务，与代码仓库无缝集成 |
| **BeautifulSoup** | HTML 解析 | 强大的 HTML 解析和内容提取能力 |

## 🔧 核心功能

### 1. 智能爬虫系统

**技术实现**: 使用 Selenium 实现动态页面抓取

```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = Options()
options.add_argument("--headless")
driver = webdriver.Chrome(options=options)
# 等待 SPA 页面动态加载完成
# 支持 JavaScript 渲染的内容
```

**特点**:
- ✅ 成熟稳定：经过大规模实战验证
- ✅ 动态渲染：支持 SPA 单页应用
- ✅ 智能等待：自动等待页面加载完成

### 2. 内容智能处理

**HTML → Markdown 转换**:
- 保留标题层级 (h1-h6)
- 转换列表、加粗、链接、图片
- 去除冗余样式和脚本
- 优化可读性

**自动分类识别**:
```python
def detect_category(title, content):
    if any(kw in title for kw in ['宏观', '政策', '经济']):
        return '宏观分析'
    elif any(kw in title for kw in ['行业', '产业', '板块']):
        return '行业分析'
    return '全部研报'
```

### 3. 自动化导航生成

**侧边栏生成脚本** (`generate_sidebar.py`):
- 扫描所有 Markdown 文件
- 统计各分类文章数量
- 自动生成树形导航结构
- 支持增量更新

**统计信息生成** (`generate_stats.py`):
- 输出 JSON 格式统计数据
- 支持 GitHub badges 动态展示
- 记录最后更新时间

### 4. 每日自动更新

**GitHub Actions 工作流**:
- 定时触发：每天 UTC 0:00 (北京时间 8:00)
- 自动任务：
  1. 运行爬虫抓取最新内容
  2. 生成侧边栏和统计信息
  3. 提交并推送更新
  4. 自动部署到 GitHub Pages

## 📊 数据来源

- **目标网站**: `h5.2025eyp.com` (鳄鱼派)
- **内容类型**: 投资研究报告
- **更新频率**: 每日更新
- **历史数据**: 600+ 篇研报

## 🚀 部署指南

### 本地运行

```bash
# 1. 克隆仓库
git clone https://github.com/Ronchy2000/Gator-Investment-Research.git
cd Gator-Investment-Research

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行前置检查（边界探测）
python scripts/pre_crawl_check.py

# 4. 运行爬虫（内容下载）
python crawler/fetch_reports.py --max-requests 100 --sleep 1.0

# 5. 生成导航和统计
python scripts/update_category_meta.py
python scripts/generate_sidebar.py

# 6. 本地预览（需要全局安装 docsify-cli）
# npm i -g docsify-cli
docsify serve docs
```

### GitHub Pages 部署

1. 将项目推送到 GitHub 仓库
2. 在仓库 Settings → Pages 中启用 GitHub Pages
3. 选择分支: `main`，目录: `/docs`
4. 配置 GitHub Actions 定时任务

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 参与方式

- 🐛 报告 Bug: [提交 Issue](https://github.com/Ronchy2000/Gator-Investment-Research/issues)
- 💡 功能建议: [发起 Discussion](https://github.com/Ronchy2000/Gator-Investment-Research/discussions)
- 📝 改进文档: 提交 PR 更新 Markdown 文件
- 🔧 代码贡献: Fork 仓库并提交 PR

### 开发规范

- Python 代码遵循 PEP 8 风格
- Markdown 文件使用统一格式
- Commit 信息采用约定式提交规范

## 📜 开源协议

本项目采用 **MIT License** 开源协议。

## ⚠️ 免责声明

1. 本项目仅供学习和研究使用
2. 所有研报内容版权归原作者所有
3. 不构成任何投资建议
4. 投资有风险，决策需谨慎

## 📞 联系方式

- **项目作者**: ronchy2000
- **GitHub**: [@Ronchy2000](https://github.com/Ronchy2000)
- **项目仓库**: [Gator-Investment-Research](https://github.com/Ronchy2000/Gator-Investment-Research)
- **在线文档**: [https://ronchy2000.github.io/Gator-Investment-Research/](https://ronchy2000.github.io/Gator-Investment-Research/)

---

<div style="text-align: center; margin-top: 40px; padding: 20px; background: #f5f7fa; border-radius: 8px;">
  <p style="font-size: 18px; font-weight: bold; color: #303133;">🐊 感谢使用鳄鱼派投资研报</p>
  <p style="color: #909399;">如果觉得有帮助，欢迎 Star ⭐️</p>
</div>
