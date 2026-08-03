# 获得信息差

“获得信息差”微信公众号的静态文章归档站。文章按发布日期同步为 Markdown，正文图片保存在本地，由 Astro 构建为独立 HTML 后部署到 Cloudflare Pages。

`master` 是当前 Astro 生产站；原 Docsify 站完整保存在 `legacy/docsify-archive`，仅作为历史快照保留，不再修改。

## 站点入口

- [当前站点：获得信息差](https://gator.ronchy2000.top/)：由 `master` 构建，持续同步微信公众号新文章，并保留已迁移的历史研报。
- [旧版站点：鳄鱼派投资研报](https://gator0.ronchy2000.top/)：由 `legacy/docsify-archive` 构建，只读保留旧 Docsify 界面和迁移前内容。

## 当前能力

- 同步单一微信公众号，不包含小红书、B 站等无关平台。
- 首次补齐 `2026-06-15` 起的历史文章，后续根据索引增量更新。
- 同时支持文本文章和内容完全由图片组成的文章。
- 下载失败的文章进入持久化重试队列，不会因跨页或部分成功而永久遗漏。
- 正文、封面和图片全部本地化，避免微信远程图片防盗链失效。
- 去重迁移旧站 913 篇历史研报，保留宏观、行业、其他分类及旧链接跳转。
- 为历史研报生成 2-6 条完整句摘要，并清理模板引用、OCR 编号、失效列表和折叠表格。
- 独立保留“宽基指数：新三年计划”投资随笔及其本地配图。
- Astro 静态生成首页、日期归档、文章详情、RSS 和 sitemap。
- 提供公众号/历史研报全文搜索、分类与年份筛选、明暗主题、阅读时间和前后文章导航。
- 使用本地品牌 Logo，并在页脚通过不蒜子展示累计访客数和累计浏览量。

## 首次上线

按以下顺序配置，不需要把任何登录文件提交到仓库：

1. 按 [DEPLOYMENT.md](DEPLOYMENT.md) 将仓库连接到 Cloudflare Pages。旧项目可以直接修改构建配置，无需重建站点或更换域名。
2. 按 [AUTOMATION.md](AUTOMATION.md) 在本地扫码，创建 `WEREAD_VID` 和 `WEREAD_TOKEN` 两项 GitHub Actions Secrets。
3. 在 GitHub Actions 页面手动运行一次 `WeChat Article Sync`，确认同步成功。
4. 确认 Cloudflare Pages 收到新提交并完成部署。以后 Action 会每天自动检查新文章。

最终配置应满足：

- GitHub 默认分支为 `master`。
- Cloudflare Production branch 为 `master`，构建命令为 `npm run build`，输出目录为 `dist`。
- GitHub 仓库中存在 `WEREAD_VID` 和 `WEREAD_TOKEN`，但仓库文件和 Cloudflare 环境变量中都不存在明文凭据。
- `WeChat Article Sync` 可以手动运行，且 GitHub Actions 的 Workflow permissions 允许写入仓库。

## 本地开发

环境要求：

- Node.js `>=22.12.0`
- Python `>=3.9`

启动前端：

```bash
npm install
npm run dev
```

生产构建输出目录为 `dist/`：

```bash
npm run build
```

## 文章同步

首次扫码和初始化。已有 `.venv` 时不要重复创建，直接执行 `source .venv/bin/activate`：

```bash
test -d .venv || python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-wechat.txt
python -m wechat_sync.auth
python -m wechat_sync.initialize
```

执行同步：

```bash
python -m wechat_sync.sync --max-pages 20 --delay 2
```

详细说明见 [AUTOMATION.md](AUTOMATION.md)。本地凭据保存在被 Git 忽略的 `data/wechat/credentials.json`，不得提交到仓库、聊天记录或截图中。

## 目录结构

```text
src/
  components/             Astro 页面组件
  content/articles/       持续增量的微信文章 Markdown
  content/reports/        冻结的 913 篇历史研报
  content/notes/          独立投资随笔
  content.config.ts       内容集合 schema
  layouts/                全局页面布局
  pages/                  首页、归档、文章页和 RSS
  styles/                 全局设计系统
public/
  article-assets/         本地化文章图片
  brand/                  网站 Logo 等品牌资源
  report-assets/          历史研报图片或失效说明占位图
wechat_sync/
  auth.py                 本地扫码登录
  client.py               微信读书中转接口客户端
  downloader.py           正文解析与图片本地化
  github_secrets.py       安全上传或复制 Actions Secrets
  sync.py                 首次回补与增量同步入口
  index.json              已完成文章索引
```

## 部署与自动化

Cloudflare Pages 的核心构建设置如下：

| 配置 | 值 |
| --- | --- |
| Production branch | `master` |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Node.js | `22` |

`wrangler.toml`、静态缓存头和基础安全响应头已经写入仓库。站点域名配置在 `astro.config.mjs`。新建项目、旧项目改造、自定义域名和部署故障排查见 [DEPLOYMENT.md](DEPLOYMENT.md)。

访问统计使用不蒜子 `3.6.9` 官方 CDN，页脚元素分别读取全站 PV 与 UV。统计服务不可用时只显示占位符，不影响静态页面、搜索或文章阅读。

GitHub Actions 每天北京时间 `08:30` 自动同步。必须配置两个独立的 Repository Secrets：

- `WEREAD_VID`
- `WEREAD_TOKEN`

不需要自行创建 GitHub PAT、Cloudflare API Token 或微信 refresh token；提交使用每次工作流自动生成的 `GITHUB_TOKEN`。扫码登录态正常情况下可以持续使用，但上游没有提供可自动刷新的 refresh token；收到 401 告警时需要在本地重新扫码并轮换上述两个 Secrets。完整配置、首次验收和故障处理见 [AUTOMATION.md](AUTOMATION.md)。

## 免责声明

本站仅用于公开信息整理和阅读，不构成任何投资建议。文章版权归原作者所有；投资有风险，请独立判断并承担相应责任。

## 分支说明

- `master`：Astro 生产站、微信公众号增量同步和 Cloudflare Pages 部署来源。
- `legacy/docsify-archive`：切换前的旧 Docsify 站，只读部署在 [gator0.ronchy2000.top](https://gator0.ronchy2000.top/)。
- `feature/wechat-mp-sync`：新站迁移过程的功能分支，与首次上线提交保持一致，便于追溯。

## 许可证

项目代码采用 [MIT License](LICENSE)。第三方代码归属见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
