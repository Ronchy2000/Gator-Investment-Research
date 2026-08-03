# 本地开发指南

本页收录开发、构建和仓库维护所需的技术信息。生产部署见 [DEPLOYMENT.md](DEPLOYMENT.md)，微信公众号自动同步与 Secrets 配置见 [AUTOMATION.md](AUTOMATION.md)。

## 环境要求

- Node.js `>=22.12.0`
- Python `>=3.9`
- npm

仓库根目录的 `.nvmrc` 固定使用 Node.js 22。Python 仅用于微信公众号同步，Astro 前端开发不需要 Python 服务常驻。

## 前端开发

安装依赖：

```bash
npm install
```

启动 Astro 开发服务器：

```bash
npm run dev
```

生成生产静态站点：

```bash
npm run build
```

构建结果位于 `dist/`，该目录不提交到 Git，由 Cloudflare Pages 在部署时重新生成。

## 同步器环境

首次使用时创建仓库专用虚拟环境。已有 `.venv` 时命令会直接复用：

```bash
test -d .venv || python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-wechat.txt
```

首次扫码与初始化：

```bash
python -m wechat_sync.auth
python -m wechat_sync.initialize
```

执行一次本地增量同步：

```bash
python -m wechat_sync.sync --max-pages 20 --delay 2
```

本地凭据位于被 Git 忽略的 `data/wechat/credentials.json`。不得提交、打印或截图传播该文件。完整的 Secret 上传和轮换流程见 [AUTOMATION.md](AUTOMATION.md)。

## 目录结构

```text
src/
  components/             Astro 页面组件
  content/articles/       持续增量的微信公众号 Markdown
  content/reports/        冻结的 913 篇历史研报
  content/notes/          独立投资随笔
  content.config.ts       Astro 内容集合 schema
  layouts/                全局页面布局
  pages/                  首页、归档、文章页、RSS 与索引
  styles/                 全局设计系统
public/
  article-assets/         本地化公众号图片
  brand/                  Logo、README 封面等品牌资源
  note-assets/            投资随笔图片
  report-assets/          历史研报图片或失效说明占位图
wechat_sync/
  auth.py                 本地扫码并维护有序登录账号池
  client.py               微信读书中转接口与账号故障转移客户端
  downloader.py           微信正文解析与媒体本地化
  github_secrets.py       安全上传或复制 Actions Secrets
  initialize.py           首次账户与索引初始化
  sync.py                 首次回补与增量同步入口
  validate.py             归档完整性检查
  accounts.json           双公众号非敏感配置
  indexes/                每个公众号独立的完成、回补和失败重试索引
```

## 内容边界

- `src/content/articles/`：只存放自动同步的“获得信息差”和“像鳄鱼一样思考”公众号文章。
- `src/content/reports/`：一次性迁移的旧站研报，不参与每日同步。
- `src/content/notes/`：独立投资随笔，不计入公众号或机构研报统计。
- `public/article-assets/`：与公众号文章 ID 对应的封面和正文图片。

新增内容必须保持 Markdown frontmatter、`wechat_sync/indexes/<slug>.json` 和本地图片引用一致。同步器只会在文章与所需媒体完整时写入对应账号的完成索引。

## 分支约定

- `master`：Astro 生产站，也是 Cloudflare Pages 与每日同步任务的来源。
- `legacy/docsify-archive`：切换前的旧 Docsify `master` 快照，只读保留。
- `feature/wechat-mp-sync`：迁移开发记录，用于追溯新站建设过程。

自动同步提交只包含：

```text
src/content/articles/
public/article-assets/
wechat_sync/indexes/
```

提交标题会包含成功同步的文章数量，例如：

```text
content: sync 1 WeChat article
content: sync 3 WeChat articles
```

## 相关文档

- [ARCHITECTURE.md](ARCHITECTURE.md)：完整系统架构和数据流。
- [AUTOMATION.md](AUTOMATION.md)：凭据、GitHub Actions 和运维。
- [DEPLOYMENT.md](DEPLOYMENT.md)：Cloudflare Pages 部署。
- [wechat_sync/README.md](wechat_sync/README.md)：同步参数和失败行为。
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)：第三方代码来源与许可证。
