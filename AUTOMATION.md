# 微信公众号自动同步配置

本手册用于配置“获得信息差”和“像鳄鱼一样思考”两个微信公众号的每日增量同步。两个公众号使用同一组微信读书登录凭据，完整链路是：

```text
GitHub Actions 定时启动
  -> 使用 WEREAD_VID / WEREAD_TOKEN 查询文章列表
  -> 下载新文章及图片并更新仓库
  -> 使用 GITHUB_TOKEN 推送 master
  -> Cloudflare Pages 检测提交并重新部署
```

Cloudflare Pages 的接入方法见 [DEPLOYMENT.md](DEPLOYMENT.md)。Cloudflare 只负责构建和托管，不需要配置微信凭据。

## 一、准备条件

开始前确认：

- GitHub 仓库为 `Ronchy2000/Gator-Investment-Research`，默认分支是 `master`。
- 本地安装 Python `3.9` 或更高版本，并可使用微信扫码。
- GitHub 仓库没有被归档，Actions 功能可用。
- 首次扫码和 Secret 配置只需要做一次；凭据失效后再重新扫码轮换。

## 二、检查 GitHub 仓库设置

### 1. 默认分支

打开仓库 `Settings -> General -> Default branch`，确认默认分支为 `master`。

定时工作流只会在默认分支执行。如果这里不是 `master`，定时任务可能不会运行。

### 2. Actions 权限

打开仓库 `Settings -> Actions -> General`：

1. 在 Actions permissions 中允许仓库运行 GitHub Actions。
2. 在 Workflow permissions 中选择 `Read and write permissions`。
3. 保存设置。

工作流需要写权限提交新文章，以及在失败时创建或更新告警 Issue。不需要创建 Personal Access Token（PAT）；工作流会使用 GitHub 每次运行自动签发的 `GITHUB_TOKEN`。

如果 `master` 配置了分支保护规则，还要确认规则允许 GitHub Actions 直接推送。否则同步和构建可以成功，但最后的 `git push` 会返回 403。

### 3. Issues

建议在仓库 `Settings -> General -> Features` 中启用 Issues。同步失败时，工作流会维护一个标题为“微信公众号自动同步失败”的 Issue；恢复成功后自动关闭。关闭 Issues 不影响下载，但会失去持久化告警。

## 三、本地扫码获取凭据

所有命令都在仓库根目录执行。下面的第一条命令只会在 `.venv` 不存在时创建环境；如果已经存在，会直接复用，不会覆盖：

```bash
cd /Users/ronchylu/Documents/Developer/Workshop/Gator-Investment-Research
test -d .venv || python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-wechat.txt
python -m wechat_sync.auth
```

`.venv` 是仓库专用的隔离环境。激活只会临时调整当前终端的命令路径，依赖也只安装到 `.venv`，不会修改系统 Python 或其他项目。扫码结束后可以执行 `deactivate` 退出环境。

如果 `.venv` 已经存在且此前成功运行过扫码工具，本次轮换可以跳过创建和安装，只执行：

```bash
cd /Users/ronchylu/Documents/Developer/Workshop/Gator-Investment-Research
source .venv/bin/activate
python -m wechat_sync.auth
```

运行后：

1. 程序生成并打开登录二维码。
2. 使用微信扫码，并在手机上确认登录。
3. 终端提示成功后，凭据写入 `data/wechat/credentials.json`。
4. 临时二维码会被清理，不需要上传二维码、扫码 UUID 或轮询记录。

如果本地已经有 `data/wechat/credentials.json`，重新扫码会原子覆盖旧凭据，这是轮换 GitHub Secrets 时的预期行为；不会修改已下载文章或同步索引。

真正需要保存到 GitHub 的只有两个字段：

| 本地字段 | GitHub Secret 名称 | 用途 |
| --- | --- | --- |
| `vid` | `WEREAD_VID` | 标识扫码登录账号 |
| `token` | `WEREAD_TOKEN` | 调用文章列表接口 |

这里的 `vid` 和 `token` 只是本地 JSON 字段名，不是 GitHub Secret 的 Name。GitHub 中必须完整填写 `WEREAD_VID` 和 `WEREAD_TOKEN`，不能缩写为 `VID`、`TOKEN`、`vid` 或 `token`。

`save_time`、昵称及其他元数据不需要上传。不要执行 `cat data/wechat/credentials.json` 后截图，也不要把该文件添加到 Git、聊天记录或 Cloudflare 环境变量。

该登录态没有可供 GitHub Actions 自动使用的 refresh token。正常情况下凭据可以长期使用；接口返回 401 时，必须在本地重新扫码并覆盖这两个 Secrets。

## 四、配置 GitHub Secrets

推荐使用 GitHub 网页，操作最直观。项目脚本会把单个值直接放入系统剪贴板，不在终端显示明文。

> **名称必须完整一致：** Repository secrets 列表最终必须显示 `WEREAD_VID` 和 `WEREAD_TOKEN`。如果页面显示的是 `VID` 和 `TOKEN`，工作流无法读取，必须删除后按正确名称重建。

### 方法 A：GitHub 网页

打开仓库：

`Settings -> Secrets and variables -> Actions -> Repository secrets`

依次创建两项 Secret。

第一项：

1. 在本地执行 `python -m wechat_sync.github_secrets --copy WEREAD_VID`。
2. GitHub 点击 `New repository secret`。
3. Name 填写 `WEREAD_VID`。
4. Secret 粘贴剪贴板内容，不要手动添加引号或空格。
5. 点击 `Add secret`。

第二项：

1. 在本地执行 `python -m wechat_sync.github_secrets --copy WEREAD_TOKEN`。
2. GitHub 再次点击 `New repository secret`。
3. Name 填写 `WEREAD_TOKEN`。
4. Secret 粘贴剪贴板内容，不要手动添加引号或空格。
5. 点击 `Add secret`。

保存后 GitHub 只显示 Secret 名称，不会再次显示值，这是正常现象。最终列表应当是：

```text
WEREAD_TOKEN
WEREAD_VID
```

以下列表是错误的，工作流不会自动猜测缩写：

```text
TOKEN
VID
```

除非以后主动更换中转服务，否则不要创建 `WEREAD_PLATFORM_URL`。工作流内置当前公开服务地址；错误填写该项反而会导致接口不可用。

### 方法 B：GitHub CLI

如果已经安装并登录 `gh`，可以一次上传两项：

```bash
brew install gh
gh auth login
python -m wechat_sync.github_secrets --repo Ronchy2000/Gator-Investment-Research
gh secret list --repo Ronchy2000/Gator-Investment-Research
```

上传脚本通过标准输入向 `gh secret set` 传值，不会把凭据写进命令参数或终端输出。`gh secret list` 只用于核对名称和更新时间，不会读取 Secret 明文。

两项值必须分开保存。不要把整个 `credentials.json` 放进一项 Secret，否则字段读取会失败，日志脱敏也不够精确。

## 五、首次手动运行

Secret 保存后，不要等待第二天的定时任务，立即进行一次正式运行：

1. 打开 GitHub 仓库的 `Actions` 页面。
2. 左侧选择 `WeChat Article Sync`。
3. 点击 `Run workflow`。
4. Branch 选择 `master`。
5. `max_pages` 表示每个公众号的页数上限，保持 `20` 即可。需要分次回补较多文章时可以提高，但单账号单次不要超过工作流允许的 `40`。
6. 再次点击绿色的 `Run workflow`。

工作流会依次执行凭据检查、文章增量同步、内容完整性检查和 Astro 构建。只有发现内容变化且全部检查成功时，才会创建提交：

```text
content: sync 1 WeChat article
content: sync 3 WeChat articles
```

提交标题中的数字是该次成功写入归档的文章数量。单篇失败会进入重试队列，不计入成功数量。

验收标准：

- Action 运行结果为绿色。
- 有新文章时，`master` 出现自动提交；没有新文章时会正常结束且不创建空提交。
- 新文章 Markdown 位于 `src/content/articles/`。
- 文章封面和正文图片位于 `public/article-assets/`，包括正文完全由图片组成的文章。
- Cloudflare Pages 随后收到同一提交并完成生产部署。
- 打开网站后能在首页或日期归档中看到新文章，详情页图片可正常加载。

手动运行入口只会在包含 `workflow_dispatch` 的工作流已经位于默认分支时显示。当前仓库已经满足这一条件。

## 六、日常自动更新逻辑

`.github/workflows/wechat-sync.yml` 每天北京时间 `18:30` 自动执行，也可以随时手动触发。该时间晚于“获得信息差”的早间更新和“像鳄鱼一样思考”的收盘后复盘，单次运行即可收齐当天两个来源。

每次运行会：

1. 依次检查 `wechat_sync/accounts.json` 中的两个公众号，每个账号最多读取 20 页，遇到已完成文章时提前停止。
2. 每个公众号分别使用文章 ID 和规范化原文链接双重去重，只下载新增文章。
3. 优先重试 `wechat_sync/indexes/<slug>.json` 中的 `pendingArticles`，避免一次失败造成永久漏文。
4. 下载正文、封面和正文图片；纯图片文章只有在至少解析并本地化一张图片后才算成功。
5. 检查 Markdown、索引和本地图片引用的一致性。
6. 执行 `npm run build`，确保生成的 Astro 网站可构建。
7. 只提交 `src/content/articles`、`public/article-assets` 和 `wechat_sync/indexes/`。
8. 推送 `master`，由 Cloudflare Pages 的 Git 集成自动发布。

公开服务的单账号每日 50 次、单 IP 每日 300 次额度足够两个公众号的日常增量使用。常规情况下每个账号只读取第一页；即使都达到默认上限也只有 40 次列表请求。不要无故反复手动运行或把 `max_pages` 长期设置为 40。

首次接入“像鳄鱼一样思考”时，账号页面显示 562 篇，但中转接口只返回最近 99 篇，并在第 3 页返回空列表。这 99 篇已一次性回补；自动化会从当前时间继续保存新增文章。其余历史文章不是额度不足或分页游标错误，而是当前数据源没有返回，除非后续提供另一种可持久化的文章列表来源，否则 Action 无法凭空枚举文章链接。

公开仓库连续 60 天没有任何仓库活动时，GitHub 可能自动禁用 scheduled workflow。若公众号长期停更，应定期查看 Actions；发现计划任务被禁用时，在工作流页面重新启用并手动运行一次。

## 七、凭据失效时轮换

当 Action 日志或告警 Issue 显示 HTTP 401、unauthorized、token invalid 等凭据错误时：

```bash
cd /Users/ronchylu/Documents/Developer/Workshop/Gator-Investment-Research
source .venv/bin/activate
python -m wechat_sync.auth
```

扫码成功后，使用“第四节”的网页方法覆盖 `WEREAD_VID` 和 `WEREAD_TOKEN`，或执行：

```bash
python -m wechat_sync.github_secrets --repo Ronchy2000/Gator-Investment-Research
```

然后在 Actions 页面手动运行一次 `WeChat Article Sync`。成功后，工作流会自动关闭之前的同步失败 Issue。

更新同名 Secret 即可，不需要删除重建工作流，不需要修改 YAML，也不需要在 Cloudflare 中同步更新。

## 八、故障排查

| 现象 | 常见原因 | 处理方法 |
| --- | --- | --- |
| `Missing WEREAD_VID` 或 `Missing WEREAD_TOKEN` | Secret 未创建、缩写成 `VID`/`TOKEN`、名称拼错或保存到 Environment secrets | 删除错误项，在 Repository secrets 中按完整名称 `WEREAD_VID`/`WEREAD_TOKEN` 重建；无需重新扫码 |
| HTTP 401 / unauthorized | 扫码登录态失效 | 重新扫码并覆盖两个 Secrets |
| HTTP 429 | 公开中转服务达到频率限制 | 停止重复运行，等待额度恢复后再手动执行；不必重新扫码 |
| 单篇文章失败 | 微信正文暂时不可访问、媒体下载失败或正文异常 | 查看 `pendingArticles`，下一次任务会自动重试 |
| 纯图片文章未入库 | 至少一张正文图片没有成功解析或本地化 | 等待下一次重试；持续失败时查看该文章下载日志 |
| `git push` 返回 403 | Workflow permissions 为只读或分支保护阻止推送 | 开启 `Read and write permissions`，调整分支保护规则 |
| Action 成功但没有新提交 | 没有新文章，或文章已经在索引中 | 属于正常结果，查看同步摘要中的新增数量 |
| Action 有提交但网页没更新 | Cloudflare 未监听 `master`、自动生产部署关闭或构建失败 | 按 [DEPLOYMENT.md](DEPLOYMENT.md) 检查分支和最新部署日志 |
| Astro 构建失败 | 新内容完整性异常或依赖/配置问题 | 工作流不会提交不完整内容，先根据失败步骤修复后重跑 |

同步失败时，已成功写入并通过检查的文章可以保留；未完成文章会进入重试队列。完整性或构建失败时不会推送本次内容，因此线上仍保留上一个正常版本。

## 九、安全注意事项

- 不要提交 `data/wechat/credentials.json`、二维码、终端凭据输出或浏览器网络请求截图。
- 不要把 Secret 写进 workflow YAML、README、Cloudflare 环境变量或普通 GitHub Variables。
- 不要在命令行中直接 `echo` 或打印 token；使用仓库提供的剪贴板和上传脚本。
- 如果凭据曾出现在提交、Issue、Action 日志或截图中，应立即重新扫码并覆盖 Secrets；仅删除文件不足以使旧凭据失效。
- GitHub Actions 只需要仓库自动提供的 `GITHUB_TOKEN`，不要额外创建长期 PAT。

## 官方参考

- [GitHub：在 Actions 中使用 Secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
- [GitHub：手动运行工作流](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- [GitHub：GITHUB_TOKEN](https://docs.github.com/en/actions/concepts/security/github_token)
- [GitHub：scheduled 工作流行为](https://docs.github.com/en/enterprise-cloud%40latest/actions/reference/workflows-and-actions/events-that-trigger-workflows)
