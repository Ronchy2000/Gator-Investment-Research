# 微信公众号自动同步配置

本手册用于配置“获得信息差”和“像鳄鱼一样思考”的自动归档。需要区分两类账号：

- **公众号来源**：被归档的两个公众号，配置在 `wechat_sync/accounts.json`。
- **微信读书登录账号**：用于调用公开中转接口的扫码账号，可以有多个，组成有序账号池。

完整链路如下：

```text
GitHub Actions 每天定时运行两次
  -> 从 WEREAD_ACCOUNTS 读取有序登录账号池
  -> 按顺序查询两个公众号，401 / 429 / 5xx / 历史空页时切换账号
  -> 下载新文章、正文图片并更新独立索引
  -> 完整性检查和 Astro 构建通过后提交 master
  -> Cloudflare Pages 检测提交并重新部署
```

Cloudflare Pages 只负责构建和托管，不需要微信凭据。部署配置见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 一、准备条件

- GitHub 仓库默认分支为 `master`，仓库未归档。
- 本地安装 Python `3.9` 或更高版本，并能使用微信扫码。
- GitHub Actions 的 Workflow permissions 设为 `Read and write permissions`。
- 仓库启用 Issues，以便同步失败时保留告警。
- 如果 `master` 有分支保护，需要允许 GitHub Actions 直接推送。

工作流使用 GitHub 自动签发的 `GITHUB_TOKEN` 提交，不需要创建 PAT。

## 二、本地隔离环境

在仓库根目录执行：

```bash
cd /Users/ronchylu/Documents/Developer/Workshop/Gator-Investment-Research
test -d .venv || python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-wechat.txt
```

`.venv` 是仓库专用环境。已有 `.venv` 时不会重建；激活只影响当前终端，不会改动系统 Python 或其他项目。完成后可执行 `deactivate`。

## 三、建立本地账号池

扫描第一个账号或追加新账号使用同一个命令：

```bash
python -m wechat_sync.auth
```

程序会生成临时二维码并等待手机确认。成功后：

1. 凭据写入被 Git 忽略的 `data/wechat/credentials.json`。
2. 新微信账号追加到池尾，已有账号顺序不变。
3. 如果重新扫描同一微信账号，则在原位置更新 token，不产生重复项。
4. 临时二维码自动删除。

账号池是有序的，结构如下。示例值仅用于说明，绝不能照抄：

```json
{
  "version": 2,
  "accounts": [
    {
      "vid": "<第一个账号>",
      "token": "<第一个账号令牌>",
      "platform_url": "https://weread.111965.xyz"
    },
    {
      "vid": "<第二个账号>",
      "token": "<第二个账号令牌>",
      "platform_url": "https://weread.111965.xyz"
    }
  ]
}
```

不要执行 `cat data/wechat/credentials.json`，不要截图或提交该文件。程序日志只显示账号序号，不显示 `vid`、`token` 或昵称。

只有明确要丢弃全部旧账号时才使用：

```bash
python -m wechat_sync.auth --reset-pool
```

该参数会清空本地账号池后只保留本次扫码账号，日常追加账号时不要使用。

## 四、上传 GitHub Secret

账号池统一保存在一个 Repository Secret：

```text
WEREAD_ACCOUNTS
```

不要把它放到 Cloudflare、GitHub Variables 或 Environment secrets。旧版 `WEREAD_VID` 和 `WEREAD_TOKEN` 仍可作为单账号兼容后备，但工作流只在 `WEREAD_ACCOUNTS` 不存在时使用它们。

### 方法 A：GitHub 网页

先把经过精简的账号池复制到系统剪贴板，命令不会打印明文：

```bash
python -m wechat_sync.github_secrets --copy WEREAD_ACCOUNTS
```

然后打开：

`Settings -> Secrets and variables -> Actions -> Repository secrets`

1. 点击 `New repository secret`。
2. Name 完整填写 `WEREAD_ACCOUNTS`。
3. Secret 粘贴剪贴板内容，不加引号、不改 JSON。
4. 保存。

以后追加、续期或删除本地账号后，重复以上操作并更新同名 Secret。GitHub 保存后不再显示值是正常行为。

### 方法 B：GitHub CLI

已安装并登录 `gh` 时可直接上传：

```bash
python -m wechat_sync.github_secrets \
  --repo Ronchy2000/Gator-Investment-Research
gh secret list --repo Ronchy2000/Gator-Investment-Research
```

上传脚本只把必要的 `vid`、`token` 和中转地址写入 Secret；本地昵称和保存时间不会上传。`gh secret list` 只显示 Secret 名称和更新时间，不显示内容。

## 五、账号池调用规则

每次 Action 启动时从池首开始：

1. 正常响应时继续使用当前账号，避免无意义消耗其他账号额度。
2. HTTP 401 或凭据失效时切换下一个账号。
3. HTTP 429 或账号额度受限时切换下一个账号。
4. HTTP 5xx 时切换下一个账号，避免单个登录账号的中转状态异常阻断整个任务。
5. 历史分页返回空列表时尝试下一个账号，因为不同登录账号可能暴露不同历史区间。
6. 所有账号都失败时，Action 才整体报错并创建告警 Issue。

账号切换只在本次进程内保持；下一次定时任务仍从池首开始。新增账号后，同步索引会检测账号池规模增加，并自动从上次历史断点附近重新探测，不需要手工修改 `backfillNextPage`。

实测第一个账号仅取得“像鳄鱼一样思考”最近 99 篇；追加第二个账号后先补齐 100 篇，冷却后又补齐第 5 页的 50 篇，当前共归档 249 篇。期间同一账号曾短暂连续返回第 1–8 页共 398 篇，但旧页在连续读取后重新变为空列表，说明公开中转的历史窗口会延迟开放且可能波动，并非固定的“每账号 100 篇”。

公众号显示总数为 562。只要本地完成数仍低于这个已知总数，后续 Action 就会持续从上次空页附近重新探测；某次空页不会再永久关闭历史回补。系统仍只把实际下载成功的文章计入归档。

## 六、定时任务与额度

`.github/workflows/wechat-sync.yml` 每天运行两次：

| 北京时间 | UTC cron | 目的 |
| --- | --- | --- |
| `10:00` | `0 2 * * *` | 收取早间信息更新 |
| `18:30` | `30 10 * * *` | 收取收盘后复盘及当日补充 |

定时任务默认每个公众号最多读取 10 页，遇到已入库文章会提前停止。日常增量通常只读取第一页；10 页上限主要用于新增账号后的分批历史回补。按两个公众号、每天两次计算，极端情况下为 40 次列表请求，低于公开服务单账号每日 50 次限制。

公开服务还存在单 IP 每日 300 次限制。不要频繁手动重跑，也不要长期把 `max_pages` 提高到 40。账号池是故障转移和扩展历史可见范围的手段，不用于绕过服务限制。

GitHub 的 cron 可能有几分钟延迟。公开仓库连续 60 天没有活动时，GitHub 也可能停用 scheduled workflow；发现停用后，在 Actions 页面重新启用并手动运行一次。

## 七、首次与手动运行

上传 Secret 后：

1. 打开仓库 `Actions`。
2. 选择 `WeChat Article Sync`。
3. 点击 `Run workflow`，分支选择 `master`。
4. `max_pages` 保持 `10`。
5. 启动并等待全部步骤完成。

工作流会依次执行凭据检查、增量同步、内容完整性检查和 Astro 构建。只有内容变化且全部步骤成功时才提交，例如：

```text
content: sync 1 WeChat article
content: sync 3 WeChat articles
```

提交数字是本次成功入库的文章数量。无新文章时正常结束，不创建空提交。失败文章保存在对应索引的 `pendingArticles`，下次自动重试。

## 八、日常同步行为

- 两个公众号分别维护 `wechat_sync/indexes/<slug>.json`。
- 文章 ID 与规范化原文链接双重去重。
- 历史回补从已保存页码附近续传，并重叠一页抵抗分页漂移。
- 正文、封面和正文图片写入仓库；纯图片文章至少成功本地化一张正文图片才算完成。
- 单篇成功后立即原子更新索引，中断时不丢失已完成进度。
- 完整性检查和 `npm run build` 都通过后才推送 `master`。
- Cloudflare Pages 检测 `master` 提交并部署 `dist/`。

## 九、凭据续期与追加账号

### 同一账号 token 失效

用该微信账号重新执行扫码：

```bash
source .venv/bin/activate
python -m wechat_sync.auth
python -m wechat_sync.github_secrets \
  --repo Ronchy2000/Gator-Investment-Research
```

相同账号会原位更新，不改变调用顺序。

### 追加第三个或更多账号

换用新微信账号执行同一套命令：

```bash
python -m wechat_sync.auth
python -m wechat_sync.github_secrets \
  --repo Ronchy2000/Gator-Investment-Research
```

扫码结果追加到池尾。下一次同步会自动识别账号池变大，并重新探测尚不可见的历史分页。

## 十、故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 缺少 `WEREAD_ACCOUNTS` | 新 Secret 未上传，旧版两项 Secret 也不完整 | 按第四节上传完整账号池 Secret |
| `WEREAD_ACCOUNTS` 不是有效 JSON | 网页粘贴时截断或手改内容 | 重新运行上传/复制脚本并覆盖同名 Secret |
| 某个账号 HTTP 401 | 该账号登录态失效 | 系统会切换下一账号；用原微信号重新扫码并上传账号池 |
| 所有账号 HTTP 401 | 整个池均失效 | 逐个重新扫码续期并覆盖 Secret |
| 某个账号 HTTP 429 | 该账号或服务触发限制 | 系统会切换下一账号；不要立即反复重跑 |
| 所有账号 HTTP 429 | 账号或 IP 当日额度耗尽 | 等待下一次定时任务或次日恢复 |
| 某个账号 HTTP 5xx | 中转服务或该账号的公众号状态异常 | 系统会切换下一账号；全部账号均失败时等待下次任务 |
| 历史页曾有内容、随后为空 | 公开中转的历史窗口波动或当次访问窗口耗尽 | 不手工反复探测；定时任务会从断点重试 |
| 单篇正文暂时为空 | 微信页面临时异常 | 文章保留在 `pendingArticles`，下次重试 |
| Action 成功但无提交 | 没有新文章或内容已去重 | 正常结果 |
| `git push` 403 | Actions 只读或分支保护 | 开启写权限并调整分支规则 |
| 有提交但网页未更新 | Cloudflare 未监听 `master` 或构建失败 | 查看 [DEPLOYMENT.md](DEPLOYMENT.md) |

同步失败时，已成功写入的文章和断点会保留；未完成文章不会被误标为成功。

## 十一、安全原则

- 不提交 `data/wechat/credentials.json`、二维码或任何 token 输出。
- 不把账号池放进 workflow YAML、README、Issue、普通 Variables 或 Cloudflare。
- 不在命令行中 `echo` token；使用仓库提供的复制/上传脚本。
- 如果凭据曾出现在提交、日志或截图中，立即用对应微信账号重新扫码并更新 Secret。
- GitHub Actions 只使用自动生成的 `GITHUB_TOKEN`，不要另建长期 PAT。

## 官方参考

- [GitHub：在 Actions 中使用 Secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
- [GitHub：手动运行工作流](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- [GitHub：GITHUB_TOKEN](https://docs.github.com/en/actions/concepts/security/github_token)
- [GitHub：scheduled workflow](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
