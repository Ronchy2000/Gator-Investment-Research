# 系统架构

当前 `master` 已将项目从旧研报爬虫和 Docsify 前端迁移为“单公众号同步 + Astro 静态站点”。旧站原样保存在 `legacy/docsify-archive`。

## 数据流

```text
微信读书扫码凭据
      |
      v
weread.111965.xyz 文章列表
      |
      v
wechat_sync/sync.py
      |
      +-- 下载 mp.weixin.qq.com 正文
      +-- 本地化封面和正文图片
      +-- 写入 Markdown frontmatter + HTML 正文
      +-- 成功后更新 wechat_sync/index.json
      |
      v
src/content/articles + public/article-assets
      |
      v
Astro Content Collections
      |
      +-- 首页和最近文章
      +-- 日期归档
      +-- 静态文章页
      +-- 全文搜索索引
      +-- RSS + sitemap
      |
      v
Cloudflare Pages / dist
```

旧 Docsify 的 913 篇唯一研报通过一次性迁移器进入 `src/content/reports`，不参与微信公众号增量任务。旧分类目录中的 876 个副本不重复迁移。
旧站单独发布的投资随笔进入 `src/content/notes`，不计入机构研报统计。

## 同步层

### 凭据

`wechat_sync/auth.py` 在可信的本地设备完成微信读书扫码，凭据写入被 Git 忽略的 `data/wechat/credentials.json`。GitHub Actions 通过 `WEREAD_VID` 和 `WEREAD_TOKEN` Secrets 读取相同凭据。

### 列表和增量判断

`wechat_sync/client.py` 访问固定的微信读书中转接口。`wechat_sync/sync.py` 读取 `wechat_sync/account.json` 和已提交的 `wechat_sync/index.json`：

1. 按页获取目标公众号文章列表。
2. 过滤 `2026-06-15` 以前的内容。
3. 遇到已保存 URL 或早于起始日期的文章后停止翻页。
4. 只处理尚未进入索引的 URL。
5. 单篇成功后立即原子更新索引；失败文章留待下次重试。

第一页因中转缓存暂时为空时会最多重试三次。HTTP 401 和 429 会分别报告凭据失效和频率限制。

### 正文和媒体

`wechat_sync/downloader.py` 直接请求微信公众号文章：

- 接受包含文本或图片的正文节点，纯图片文章不会被误判为空正文。
- 删除脚本、表单和事件属性。
- 将微信懒加载图片地址转换为本地路径。
- 每篇文章在临时目录下载完整后再替换正式资源目录。
- 单个媒体限制为 25 MiB。
- 将文章写入 `src/content/articles/YYYY-MM-DD-<id>.md`。

## 展示层

Astro 使用 `src/content.config.ts` 中的 schema 读取全部文章，在构建阶段输出真实 HTML。

- `src/pages/index.astro`：最新文章、统计、月份入口。
- `src/pages/archive.astro`：按月和日期浏览公众号文章。
- `src/pages/articles/[id].astro`：文章正文、原文入口和前后导航。
- `src/pages/reports/index.astro`：按分类、年份浏览 913 篇冻结历史研报。
- `src/pages/reports/[id].astro`：历史研报静态详情页。
- `src/pages/notes/[id].astro`：独立投资随笔详情页。
- `src/pages/search-index.json.ts`：构建一次、首次搜索时按需加载的双资料库全文索引。
- `src/components/SearchDialog.astro`：公众号/历史研报范围切换和客户端全文搜索。
- `src/layouts/BaseLayout.astro`：全局导航、明暗主题、SEO 和页脚。
- `src/pages/rss.xml.js`：RSS 订阅源。

`scripts/migrate_legacy_reports_to_astro.py` 从 `docs/all-reports` 读取 913 篇唯一正文，转换 frontmatter 并保留原分类。迁移器优先从原文“摘要、核心观点、核心结论、投资要点”等章节提取 2-6 条完整句摘要；缺少这些章节时，先保留正文总论，再从全文选取带有结论信号的主题句。该过程只摘录原文，不生成原文不存在的判断。

旧站为每篇文章自动添加的首段引用不具备统一的强调语义，因此迁移时移除。正文还会统一清理残缺导语、OCR 编号和孤立编号，恢复列表、章节标签及少量折叠表格；真正由作者写入正文的 Markdown 引用仍可作为重点提示。唯一包含远程图片的旧文因源站失效而使用明确的本地占位图，原图片链接仍保留供追溯。

站点仅使用少量原生 JavaScript 处理搜索、主题、阅读进度和图片放大，不引入 React/Vue 等运行时框架。

品牌资源统一使用 `public/brand/huode-xinxicha-logo.jpg`，用于页头、页脚、favicon、默认社交分享图和无封面占位。页脚通过不蒜子 `3.6.9` 官方 CDN 展示全站 PV/UV；统计脚本属于非关键增强，加载失败不会阻塞内容页面。

## 自动化

`.github/workflows/wechat-sync.yml` 每天北京时间 08:30 运行，也支持手动触发：

1. 安装最小 Python 依赖。
2. 最多读取 5 页文章列表，页面和文章请求间隔 3 秒。
3. 只暂存文章 Markdown、本地资源和同步索引。
4. 即使某篇失败，也先提交本轮已成功内容，再让工作流以失败状态提示处理。

Cloudflare Pages 监听内容提交并执行 `npm run build`，静态输出目录为 `dist`。

## 分支布局

- `master`：Astro 生产站，也是定时微信公众号同步任务的提交目标。
- `legacy/docsify-archive`：切换前的旧 `master` 快照，内容冻结，不再改动。
- `feature/wechat-mp-sync`：保留迁移开发记录；首次上线后不再作为生产部署来源。
