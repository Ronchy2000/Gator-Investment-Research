# 获得信息差

“获得信息差”微信公众号的静态文章归档站。文章按发布日期同步为 Markdown，正文图片保存在本地，由 Astro 构建为独立 HTML 后部署到 Cloudflare Pages。

开发工作位于 `feature/wechat-mp-sync` 分支；原 `master` 暂时保留旧版 Docsify 研报站历史。

## 当前能力

- 同步单一微信公众号，不包含小红书、B 站等无关平台。
- 首次补齐 `2026-06-15` 起的历史文章，后续根据索引增量更新。
- 同时支持文本文章和内容完全由图片组成的文章。
- 正文、封面和图片全部本地化，避免微信远程图片防盗链失效。
- Astro 静态生成首页、日期归档、文章详情、RSS 和 sitemap。
- 提供标题与正文全文搜索、明暗主题、阅读时间、图片放大和前后文章导航。

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

首次扫码和初始化：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-wechat.txt
python -m wechat_sync.auth
python -m wechat_sync.initialize
```

执行同步：

```bash
python -m wechat_sync.sync --max-pages 20 --delay 2
```

详细说明见 [wechat_sync/README.md](wechat_sync/README.md)。本地凭据保存在被 Git 忽略的 `data/wechat/credentials.json`，不得提交到仓库。

## 目录结构

```text
src/
  components/             Astro 页面组件
  content/articles/       微信文章 Markdown
  content.config.ts       内容集合 schema
  layouts/                全局页面布局
  pages/                  首页、归档、文章页和 RSS
  styles/                 全局设计系统
public/
  article-assets/         本地化文章图片
wechat_sync/
  auth.py                 本地扫码登录
  client.py               微信读书中转接口客户端
  downloader.py           正文解析与图片本地化
  sync.py                 首次回补与增量同步入口
  index.json              已完成文章索引
```

## Cloudflare Pages

建议构建设置：

| 配置 | 值 |
| --- | --- |
| Production branch | 完成迁移后使用新的默认分支 |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Node.js | `22` |

`wrangler.toml`、静态缓存头和基础安全响应头已经写入仓库。站点域名配置在 `astro.config.mjs`。

GitHub Actions 同步时需要配置：

- `WEREAD_VID`
- `WEREAD_TOKEN`

## 免责声明

本站仅用于公开信息整理和阅读，不构成任何投资建议。文章版权归原作者所有；投资有风险，请独立判断并承担相应责任。

## 许可证

项目代码采用 [MIT License](LICENSE)。第三方代码归属见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
