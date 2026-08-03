# 微信公众号同步迁移方案

## 1. 目标

在 `feature/wechat-mp-sync` 分支开发新的单公众号同步流程。完成并稳定运行后：

- 将当前 `master` 保留为历史站点分支，不再继续开发旧研报爬虫。
- 将新分支合并或提升为新的默认分支。
- 只同步一个指定微信公众号，不引入小红书、B 站、抖音、视频号等无关模块。
- 使用 GitHub Actions 定时获取新文章，生成 Markdown、本地媒体资源和 Astro 静态页面。

### 1.1 已确认范围

- 目标公众号：`获得信息差`
- 首篇日期：`2026-06-15`
- 已知首批文章：
  - `大模型之战：为什么价格差这么多？`
  - `6.15鸡蛋商品调研：梅雨影响鸡蛋价格？`
- 用于解析公众号 `mpId` 的种子文章：
  - `https://mp.weixin.qq.com/s/zmDm_g8Jh9M6gEI1R8xq7g`
- 首次运行：补齐 `2026-06-15` 起的全部历史文章。
- 后续运行：只获取并提交新文章。

## 2. 上游评估

分析基于：

- 上游仓库：[x554960766/wechat-mp-tools](https://github.com/x554960766/wechat-mp-tools)
- 固定提交：`d8d83225f12d3baec20f943498716883aae8fe8a`
- 上游版本：`1.7.0`
- 提交日期：`2026-07-31`
- 许可证：MIT

### 2.1 可复用部分

微信公众号链路可拆成三个独立步骤：

1. 通过微信读书扫码获取 `vid` 和 Bearer `token`。
2. 使用 `weread.111965.xyz` 的接口解析公众号文章链接，得到公众号 `mpId`。
3. 使用同一接口获取文章列表，再直接请求 `mp.weixin.qq.com` 下载正文与媒体。

第 2、3 步可以在无界面的 Linux GitHub Actions runner 中执行。上游当前的文章正文下载已经使用 `requests`，不再强制依赖 Playwright。

### 2.2 不应直接引入的部分

不建议把整个 `wechat-mp-tools` 仓库作为子模块或完整复制进来：

- 它是 Flask/桌面工具，不是可直接安装的 Python 库。
- 完整依赖包含 Playwright、pywebview、mitmproxy、视频处理和多个平台 SDK。
- 顶层批量下载脚本仍混有旧版公众号后台登录逻辑，与 `1.7.0` 的微信读书凭证格式不完全一致。
- 项目中的账号有效期存在 4 天、30 天和“长期有效”三种互相矛盾的表达。
- 凭证检查接口主要检查本地账号池是否存在可用条目，不等同于远端 token 真实有效。

推荐做法是固定上游提交，仅移植并注明来源的最小逻辑：

- 扫码凭证获取
- 单公众号 `mpId` 解析
- 增量文章列表获取
- 单篇正文及图片下载

## 3. GitHub Actions 可行性

结论：**有条件可行，适合单公众号低频同步，但依赖第三方中转服务，不应视为高可靠或永久稳定方案。**

### 3.1 有利条件

- 列表接口和文章正文下载都可以使用普通 HTTP 请求。
- 只关注一个公众号，每天同步一次时请求量较低。
- GitHub Actions 可以直接提交生成的 Markdown、图片和索引状态。
- runner 无需保持桌面会话，也无需每次扫码。

### 3.2 主要限制

- `weread.111965.xyz` 是第三方中转服务，不是微信官方公开 API。
- 上游参考的 `cooderl/wewe-rss` 已于 2026-05-11 归档。
- 公开中转服务曾说明限制单账号每天 50 次、单 IP 每天 300 次请求。
- token 失效后的刷新机制不可靠，目前没有可用于 Actions 的稳定 refresh token 流程。
- GitHub-hosted runner 使用数据中心出口 IP，可能遇到微信或中转服务限流。
- 下载大量原图会持续增大 Git 仓库体积，需要设置图片大小和历史保留策略。

## 4. 登录持久化方案

### 4.1 推荐方案：本地扫码，Secrets 持久化

登录只在可信的本地环境执行一次：

1. 本地运行精简登录工具并扫码。
2. 获取 `vid` 和 `token`。
3. 将两项值分别写入 GitHub Actions Secrets：
   - `WEREAD_VID`
   - `WEREAD_TOKEN`
4. Actions 每次运行时从 Secrets 读取，不生成或提交真实凭证文件。
5. token 失效时，任务明确失败；用户在本地重新扫码并更新两个 Secrets。

这种方案实现的是“跨 Actions 运行持久化使用”，不是“永不失效”或“自动续签”。

### 4.2 不采用的方案

- **不提交 `data/wechat_mp_config.json`**：会永久泄漏凭证到 Git 历史。
- **不使用 Actions Cache 保存凭证**：Cache 不是密钥存储，访问范围和生命周期也不适合认证信息。
- **不使用 Artifact 保存凭证**：Artifact 可下载，不应承载长期登录密钥。
- **不让定时任务等待扫码**：计划任务没有合适的人机交互通道，二维码还有短时有效期。
- **不使用 `GITHUB_TOKEN` 自动更新 Secrets**：它默认无权更新仓库 Secrets，而且上游也没有可靠的 token 自动刷新接口。

### 4.3 可选方案：自托管 runner

自托管 runner 可以保留本地 `data/` 目录并在失效时直接扫码，但代价是个人电脑或服务器必须长期在线，并承担系统维护和凭证保护责任。除非 GitHub-hosted runner 的出口 IP 被持续限制，否则不优先采用。

## 5. 推荐架构

```text
本地一次扫码
    |
    v
GitHub Secrets: WEREAD_VID + WEREAD_TOKEN
    |
    v
GitHub Actions (每日一次 / 手动触发)
    |
    +-- 获取单公众号最新文章列表
    +-- 遇到已保存 URL 立即停止翻页
    +-- 下载新增文章正文和图片
    +-- 转换为 Markdown
    +-- 更新 wechat_sync/index.json
    +-- 更新 Astro 内容集合和首页索引
    +-- 构建静态 HTML、RSS 和 sitemap
    +-- 仅在有新增内容时提交
```

### 5.1 建议目录

```text
wechat_sync/
  auth.py               # 仅本地使用的扫码登录入口
  client.py             # 微信读书中转接口最小客户端
  downloader.py         # 微信文章正文与媒体下载
  converter.py          # HTML -> Markdown
  sync.py               # 单公众号增量同步入口
src/content/articles/
  YYYY-MM-DD-slug.md     # 带 frontmatter 的 Markdown 文章
public/article-assets/
  <article-id>/          # 每篇文章的本地图片和媒体
wechat_sync/
  index.json             # 已保存 URL、发布时间和文章路径
src/pages/
  index.astro            # 首页
  articles/[...slug].astro
.github/workflows/
  wechat-sync.yml
```

### 5.2 展示层决策：Astro 静态站点

新站推荐从 Docsify 迁移到 Astro，但继续以 Markdown 作为文章事实来源。

选择 Astro 的原因：

- 构建时为每篇文章生成真实 HTML，不依赖浏览器加载 Markdown。
- 使用正常路径而不是 Hash 路由，文章直链和图片相对路径更稳定。
- 适合生成文章列表、日期归档、RSS、sitemap、Open Graph 和阅读时间。
- Content Collections 可以校验标题、日期、原文链接等 frontmatter 字段。
- Cloudflare Pages 原生支持 Git 仓库构建，配置为 `npm run build`，输出目录为 `dist`。
- 开发分支可以使用 Cloudflare Pages Preview Deployment，切换默认分支前不影响当前线上站点。

保持纯静态输出，不引入 Astro SSR、Cloudflare Functions、D1 或其他运行时服务。这样部署复杂度仍接近 Docsify，但文章页面的可靠性和可扩展性更好。

### 5.3 建议 Secrets 与配置

敏感配置：

- `WEREAD_VID`
- `WEREAD_TOKEN`

非敏感配置可以写入仓库：

- `WECHAT_MP_NAME`
- `WECHAT_MP_ID`
- `WEREAD_PLATFORM_URL`
- 每次最大翻页数
- 每次最大新增文章数
- 请求间隔

公众号 `mpId` 只需在首次通过该公众号任意文章链接解析后固定保存，后续不必每天重新解析。

## 6. Actions 运行策略

第一阶段只启用 `workflow_dispatch`，验证凭证和目标公众号配置稳定后再增加定时任务。

正式定时任务建议：

- 每天运行一次，不做高频轮询。
- `concurrency` 禁止同一同步任务并发。
- 每页间隔 2 至 5 秒并加入轻微随机抖动。
- 默认只读取第一页；只有第一页没有命中已保存文章时才继续翻页。
- 单次最多读取 3 至 5 页，避免耗尽账号每日请求额度。
- 遇到 401 立即停止并提示凭证失效。
- 遇到 429 立即停止，不在同一次任务中持续重试。
- 文章下载失败时不写入“已完成”索引，留给下次重试。
- 只有检测到新增文章时才更新导航并提交。

## 7. 分支与迁移步骤

### 阶段 A：最小同步器

- [x] 使用已提供的种子文章链接解析并固定公众号 `mpId`。
- [x] 本地扫码生成 `vid/token`。
- [x] 解析并固定 `WECHAT_MP_ID`。
- [x] 实现文章列表获取和增量去重。
- [x] 实现正文、图片和 Markdown 保存。
- [x] 首次补齐 `2026-06-15` 起的全部 49 篇历史文章。

### 阶段 B：手动 Actions

- 添加仅支持手动触发的工作流。
- 配置 Secrets。
- 验证新增文章提交格式和凭证错误提示。
- 搭建 Astro 静态页面、RSS 和 sitemap。
- 使用 Cloudflare Pages 开发分支预览地址检查内容。

### 阶段 C：定时运行

- 增加每日一次的 cron。
- 增加 401/429 失败摘要。
- 控制媒体大小和仓库增长。

### 阶段 D：默认分支切换

- 冻结当前 `master`，创建清晰的历史分支或标签。
- 将 `feature/wechat-mp-sync` 合并为新的 `master`。
- 修改 GitHub Pages/托管平台的构建分支。
- 确认新站点稳定后再删除或归档旧 Python 入口；旧历史分支永久保留。

## 8. 下一步所需操作

本地扫码、公众号初始化、同步器实现和首次历史回补已经完成。下一步是将本地 `vid/token` 配置到 GitHub Secrets，添加手动 Actions 工作流，再搭建 Astro 页面并接入 Cloudflare Pages 开发分支预览。

本地扫码命令：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-wechat.txt
python -m wechat_sync.auth
```

二维码保存在 `data/wechat/login-qrcode.png`，登录凭证保存在 `data/wechat/credentials.json`。两个路径均受 `.gitignore` 保护。

## 9. 决策摘要

- 选择 `feature/wechat-mp-sync` 作为开发分支。
- 只集成微信公众号最小链路，不引入其他平台功能。
- GitHub Actions 可用于低频单公众号同步。
- 凭证使用 GitHub Secrets；首次登录和失效轮换必须在本地扫码完成。
- 不依赖 Cache、Artifact 或仓库文件保存凭证。
- 首次补齐“获得信息差”自 `2026-06-15` 起的全部历史文章，之后增量同步。
- 新站使用 Astro 生成静态 HTML，文章内容继续保存为 Markdown。
- Cloudflare Pages 先部署开发分支预览，稳定后再切换生产分支。
- 不直接复制完整上游应用，固定提交后移植最小代码并保留 MIT 归属声明。
- 在手动工作流稳定前，不启用定时任务，也不替换 `master`。
