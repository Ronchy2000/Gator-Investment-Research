# 自动同步与运维

本仓库每天从“获得信息差”微信公众号增量下载文章，本地化图片，提交到 `master`，再由 Cloudflare Pages 自动发布 Astro 静态站点。

## 首次配置

在本地完成扫码：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-wechat.txt
python -m wechat_sync.auth
```

扫码成功后会生成被 Git 忽略的 `data/wechat/credentials.json`。真正需要保存的只有：

- `vid` → GitHub Secret `WEREAD_VID`
- `token` → GitHub Secret `WEREAD_TOKEN`

`login-qrcode.png`、扫码 UUID、等待轮询记录和 `save_time` 都不需要上传。不要提交 `data/` 目录。

### 方式一：GitHub CLI

```bash
brew install gh
gh auth login
python -m wechat_sync.github_secrets --repo Ronchy2000/Gator-Investment-Research
```

上传脚本通过标准输入向 `gh secret set` 传值，不会在终端回显凭据。

### 方式二：GitHub 网页

1. 打开仓库 `Settings → Secrets and variables → Actions`。
2. 点击 `New repository secret`，分别创建 `WEREAD_VID` 和 `WEREAD_TOKEN`。
3. 使用下面的命令逐项复制，然后粘贴到对应 Secret：

```bash
python -m wechat_sync.github_secrets --copy vid
python -m wechat_sync.github_secrets --copy token
```

两项 Secret 必须分开保存。不建议把整个 JSON 放进一项 Secret，否则 GitHub 日志对其内部字段的自动脱敏可能不完整。

## Action 配置

`.github/workflows/wechat-sync.yml` 的生产流程：

1. 每天北京时间 `08:30` 执行，也可在 Actions 页面手动触发。
2. 最多检查 20 页文章列表；遇到已完成文章会提前停止，常规日增量只使用少量请求。
3. 按文章 ID 和规范化原文链接去重，已入库文章不重复下载。
4. 新文章正文、封面和图片全部本地化；纯图片文章同样受完整性检查。
5. 单篇失败时写入 `wechat_sync/index.json` 的 `pendingArticles`，下次自动重试。
6. 在提交前检查 Markdown/索引/图片一致性，并执行 `npm run build`。
7. 只提交 `src/content/articles`、`public/article-assets` 和 `wechat_sync/index.json`。
8. 推送 `master` 后，Cloudflare Pages 通过 GitHub 集成自动执行 `npm run build` 并发布 `dist`。

Action 提交使用 GitHub 每次运行自动签发的 `GITHUB_TOKEN`，工作流已限定为 `contents: write` 和 `issues: write`，不需要创建或长期保存 PAT。
如果推送时返回 403，在仓库 `Settings → Actions → General → Workflow permissions` 中选择 `Read and write permissions`，并检查 `master` 分支保护规则是否禁止 GitHub Actions 直接推送。

定时工作流只在默认分支运行，因此 GitHub 仓库的 Default branch 必须保持为 `master`。公开仓库连续 60 天没有任何仓库活动时，GitHub 可能自动禁用 scheduled workflow；若公众号长期停更，需在 Actions 页面重新启用。

## 失败与自愈

同步失败时，Action 会维护一个标题为“微信公众号自动同步失败”的 Issue，避免每天创建重复告警。后续同步成功后会自动关闭该 Issue。

- `429`：公开中转服务限流。当前任务会失败，已成功文章仍可提交，未完成文章下次重试。
- 单篇下载失败：文章进入 `pendingArticles`，下次运行自动重试。
- 完整性或 Astro 构建失败：不提交本次生成内容，Cloudflare 继续保留上一个正常版本。
- `401`：凭据已失效，需要人工重新扫码。上游接口没有提供 refresh token，因此无法在 GitHub 无人扫码的环境中自动续期。

401 轮换步骤：

```bash
source .venv/bin/activate
python -m wechat_sync.auth
python -m wechat_sync.github_secrets --repo Ronchy2000/Gator-Investment-Research
```

更新 Secrets 后，在 GitHub Actions 页面手动运行 `WeChat Article Sync`。

## Cloudflare Pages

Cloudflare 只负责构建和托管，不需要微信凭据。配置保持为：

| 配置 | 值 |
| --- | --- |
| Production branch | `master` |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Node.js | `22` |

如果 Cloudflare 仍使用旧 Docsify 站点的 `docs` 输出目录，必须改为 `dist`。
