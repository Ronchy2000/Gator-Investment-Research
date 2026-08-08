# 系统架构

当前 `master` 使用“RapidAPI 双公众号同步 + Astro 静态站点”。微信读书实现保存在 `legacy/weread-sync`，旧 Docsify 站点保存在 `legacy/docsify-archive`。

## 数据流

```text
GitHub Secret: RAPIDAPI_KEYS
      |
      v
RapidAPI 列表 V2 + 文章详情 V4
      |
      v
wechat_sync/sync.py
      |
      +-- 获取并校验完整正文 HTML
      +-- 从微信 CDN 本地化封面和正文图片
      +-- 写入 Markdown frontmatter + HTML 正文
      +-- 成功后更新对应的 wechat_sync/indexes/<slug>.json
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
EdgeOne Pages / dist
```

旧 Docsify 的 913 篇唯一研报通过一次性迁移器进入 `src/content/reports`，不参与微信公众号增量任务。旧分类目录中的 876 个副本不重复迁移。
旧站单独发布的投资随笔进入 `src/content/notes`，不计入机构研报统计。

## 同步层

### API Key 池

`wechat_sync/rapidapi_secrets.py` 使用隐藏输入维护被 Git 忽略的 `data/wechat/rapidapi-keys.json`。GitHub Actions 通过单个 `RAPIDAPI_KEYS` Secret 读取 JSON Key 数组；截至 `2026-08-05` 当前池中有十个已订阅同一 API 产品的 Key，单个 `RAPIDAPI_KEY` 仅作兼容后备。Key 不会写入日志、仓库或 EdgeOne 环境变量。

`wechat_sync/client.py` 每天从不同 Key 开始请求，使套餐额度在账号池中分摊。HTTP 401、403、429、5xx，以及可切换的业务错误会触发下一个 Key；成功切换后，同一次任务继续使用该 Key，只有所有 Key 都失败时才终止同步。Key 数量可调整，代码不依赖固定数量。

### 列表和增量判断

`wechat_sync/client.py` 通过 RapidAPI 访问公众号文章列表 V2 和文章详情 V4 接口。`wechat_sync/sync.py` 读取 `wechat_sync/accounts.json` 和已提交的 `wechat_sync/indexes/*.json`：

1. 日常任务通过 V2 空游标获取“获得信息差”和“像鳄鱼一样思考”的最新列表页。
2. 每个公众号通过一篇公开种子文章识别，并独立配置最早收录日期、分页断点、完成索引和失败队列。
3. 同时使用文章 ID、规范化原文链接以及“标题 + 发布日期”去重，兼容旧版短链接和 RapidAPI 长链接。
4. 本地历史模式通过 V2 从 `PagingInfo.Offset` 游标断点继续；日常增量游标不会覆盖历史进度。
5. 失败文章写入 `pendingArticles`，下次执行时与新文章一起处理。
6. 单篇成功后立即原子更新索引，因此部分失败不会丢失已完成结果。
7. 请求按日期分配到 Key 池，鉴权、额度、限流或临时采集失败时自动切换。
8. 历史补录以 V2 的 `PagingInfo.IsEnd` 为准；`backfillComplete=true`、空 `backfillOffset` 和空 `pendingArticles` 共同表示已到接口末页且下载完整。

日常 Action 默认只请求每个公众号最新一页；这足以覆盖每日增量，并把列表请求控制在约 120 次/月。V2 在免费套餐下每个 Key 另有 10 次 Pro 月额度，因此每天两次同步两个公众号理论上需要约 12 个同额度 Key，或改用足够额度的套餐。显式 `--history-v2` 模式还会保存游标并从断点继续，应只在本地分批运行。截至 `2026-08-05`，“像鳄鱼一样思考”已通过 V2 到达真实末页；清理 7 份旧编码损坏的重复归档后，共有 581 篇唯一文章，最早至 `2023-07-22`。结果仍多于此前页面显示的 562 篇，证明公开总数不能作为完成依据。

### 正文和媒体

新文章先通过详情 V4 接口取得正文 HTML，再由 `wechat_sync/downloader.py` 处理正文与微信 CDN 媒体。列表返回的微信长链接不会被直接请求，避免跳转到验证码页面：

- 接受包含文本或图片的正文节点，纯图片文章不会被误判为空正文。
- 纯图片文章必须解析出可用图片，远程图片未全部本地化时不会进入完成索引。
- 删除脚本、表单和事件属性。
- 将微信懒加载图片地址转换为本地路径。
- 每篇文章在临时目录下载完整后再替换正式资源目录。
- 单个媒体限制为 25 MiB。
- 将文章写入 `src/content/articles/YYYY-MM-DD-<id>.md`。

## 展示层

Astro 使用 `src/content.config.ts` 中的 schema 读取全部文章，在构建阶段输出真实 HTML。

- `src/pages/index.astro`：最新文章、统计、月份入口。
- `src/pages/archive.astro`：合并浏览两个公众号的文章。
- `src/pages/archive/[source].astro`：分别浏览每日信息和每日复盘。
- `src/pages/articles/[id].astro`：文章正文、原文入口和前后导航。
- `src/pages/reports/index.astro`：按分类、年份浏览 913 篇冻结历史研报。
- `src/pages/reports/[id].astro`：历史研报静态详情页。
- `src/pages/notes/[id].astro`：独立投资随笔详情页。
- `src/pages/search-index.json.ts`：构建一次、首次搜索时按需加载的全文索引。
- `src/components/SearchDialog.astro`：每日信息/每日复盘/历史研报范围切换和客户端全文搜索。
- `src/layouts/BaseLayout.astro`：全局导航、明暗主题、SEO 和页脚。
- `src/pages/rss.xml.js`：RSS 订阅源。

历史研报迁移已完成，当前生产分支只保留迁移结果。迁移前的 Docsify 源文档、旧爬虫和一次性迁移器可在 `legacy/docsify-archive` 分支追溯。

旧站为每篇文章自动添加的首段引用不具备统一的强调语义，因此迁移时移除。正文还会统一清理残缺导语、OCR 编号和孤立编号，恢复列表、章节标签及少量折叠表格；真正由作者写入正文的 Markdown 引用仍可作为重点提示。唯一包含远程图片的旧文因源站失效而使用明确的本地占位图，原图片链接仍保留供追溯。

站点仅使用少量原生 JavaScript 处理搜索、主题、阅读进度和图片放大，不引入 React/Vue 等运行时框架。

品牌资源统一使用 `public/brand/huode-xinxicha-logo.jpg`，用于页头、页脚、favicon、默认社交分享图和无封面占位。页脚通过不蒜子 `3.6.9` 官方 CDN 展示全站 PV/UV；统计脚本属于非关键增强，加载失败不会阻塞内容页面。

## 自动化

`.github/workflows/wechat-sync.yml` 每天北京时间 09:07 和 16:37 运行，也支持手动触发，分别覆盖早间信息和收盘后复盘：

1. 安装最小 Python 依赖。
2. 每个公众号默认读取最新 1 页文章列表，遇到已完成文章时提前停止。
3. 检查 Markdown、索引、封面和正文图片的引用完整性。
4. 执行 Astro 生产构建，只在完整性检查和构建成功后提交。
5. 使用工作流自带的 `GITHUB_TOKEN` 提交到 `master`，不需要额外 PAT。
6. 任何阶段失败时创建或更新唯一的 GitHub Issue；后续恢复时自动关闭。

EdgeOne Pages 监听内容提交并执行 `npm run build`，静态输出目录为 `dist`。
RapidAPI Key、GitHub Secrets 与 Action 运维见 `AUTOMATION.md`；新建或迁移 EdgeOne Pages 项目见 `DEPLOYMENT.md`。

## 分支布局

- `master`：RapidAPI 增量同步与 Astro 生产站，也是定时任务的提交目标。
- `legacy/weread-sync`：切换前的微信读书扫码与中转接口实现，内容冻结。
- `legacy/docsify-archive`：Astro 迁移前的 Docsify 旧站快照，内容冻结。
