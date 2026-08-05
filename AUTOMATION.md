# GitHub Actions 自动同步

生产分支使用 RapidAPI 上的 **Weixin/Wechat Official Accounts Platform** 获取公众号文章列表和完整正文 HTML，不再依赖微信读书扫码、`vid` 或短期登录令牌。封面与正文图片由仓库下载器从微信 CDN 本地化。

## 当前生产基线

- 生产分支：`master`。
- 工作流：`.github/workflows/wechat-sync.yml`。
- 数据源：RapidAPI 的文章列表 V1、历史文章 V2 与文章详情 V4。
- 公众号：“获得信息差”和“像鳄鱼一样思考”。
- 凭据：一个名为 `RAPIDAPI_KEYS` 的 Repository Secret，当前按五 Key 池配置。
- 调度：北京时间每天 `10:17`、`18:47`，也可手动运行。
- 部署：Action 只提交完整文章；EdgeOne Pages 监听 `master` 并发布 `dist/`。

RapidAPI Key 不属于 EdgeOne 构建环境。EdgeOne 无需、也不应配置任何公众号同步凭据。

## 自动化流程

```text
RAPIDAPI_KEYS
  -> 按日期选择一个 Key
  -> 查询两个公众号的最新文章页
  -> Key 无效、限流或额度耗尽时自动切换
  -> 与已归档文章按 ID、链接及“标题 + 日期”去重
  -> 通过文章详情 V4 获取正文 HTML
  -> 下载并本地化封面和正文图片
  -> 完整性检查与 Astro 构建
  -> commit 并 push master
  -> EdgeOne Pages 自动部署
```

工作流文件为 `.github/workflows/wechat-sync.yml`，每天北京时间 `10:17` 和 `18:47` 各运行一次，也支持手动执行。

## 1. 准备 RapidAPI Key

1. 登录 [RapidAPI](https://rapidapi.com/)。
2. 订阅 [Weixin/Wechat Official Accounts Platform](https://rapidapi.com/dataapiman/api/weixin-wechat-official-accounts-platform/pricing) 的可用套餐。
3. 在接口页面复制 `X-RapidAPI-Key`。
4. 多个 RapidAPI 账号需要分别订阅该 API，再分别取得 Key。

截至 `2026-08-05`，免费套餐页面显示每个账号每月 50 次请求；套餐和额度可能调整，以 RapidAPI 页面及响应头为准。当前工作流通常每月需要：

```text
2 个公众号 × 每天 2 次 × 30 天 = 约 120 次列表请求
2 个公众号 × 每天约 1 篇新文章 × 30 天 = 约 60 次详情请求
```

正常双公众号增量约需 180 次/月，实际数量随发文频率变化。单个 50 次/月的 Key 无法支撑整月每天两次检查；五个免费账号理论上提供约 250 次/月，可覆盖正常增量和少量重试。不要用多个 Key 并行请求；同步器会按日期分摊使用，并仅在当前 Key 不可用时按顺序故障转移。

Key 池只应包含你有权使用的 Key。多个账号共享使用是否符合免费套餐规则，以 RapidAPI 和接口提供方的最新条款为准；若条款不允许通过多账号叠加免费额度，应改用付费套餐或降低执行频率。

## 2. 安全维护本地 Key 池

仓库提供隐藏输入工具。Key 只写入被 Git 忽略的 `data/wechat/rapidapi-keys.json`，文件权限设置为仅当前用户可读写。

每获得一个 Key，执行一次：

```bash
python -m wechat_sync.rapidapi_secrets --add
```

输入不会回显。重复执行可继续追加，重复 Key 会自动忽略。只检查数量：

```bash
python -m wechat_sync.rapidapi_secrets --count
```

移除已经泄露或废弃的 Key：

```bash
python -m wechat_sync.rapidapi_secrets --remove
```

不要把 Key 写进命令行参数、README、Issue、聊天、截图或提交记录。已经公开过的 Key 应在 RapidAPI 的应用 Security 页面创建新 Key，并删除旧 Key。

## 3. 上传 GitHub Repository Secret

推荐使用 GitHub CLI，从标准输入上传，Key 不会出现在命令参数中：

```bash
python -m wechat_sync.rapidapi_secrets \
  --upload \
  --repo Ronchy2000/Gator-Investment-Research
```

如果不使用 GitHub CLI，可复制到剪贴板：

```bash
python -m wechat_sync.rapidapi_secrets --copy
```

然后打开：

```text
GitHub 仓库
-> Settings
-> Secrets and variables
-> Actions
-> New repository secret
```

五个 Key 不要分别创建五个 Secret。名称只填写：

```text
RAPIDAPI_KEYS
```

值是工具生成的 JSON 字符串数组，例如 `[` 开头、`]` 结尾。不要粘贴 `curl` 命令、Markdown 代码块、Secret 名称或说明文字。工作流也兼容单个 `RAPIDAPI_KEY`，但生产环境应使用 `RAPIDAPI_KEYS`；当 Key 池存在时，兼容 Secret 不参与请求。

GitHub 不允许读取已保存 Secret 的值，只能查看名称和更新时间。上传后可确认：

```bash
gh secret list --repo Ronchy2000/Gator-Investment-Research
```

输出中应存在 `RAPIDAPI_KEYS`。如需确认池内数量，应在上传前执行本地 `--count`；GitHub 页面无法反查内容。

旧的 `WEREAD_ACCOUNTS`、`WEREAD_VID`、`WEREAD_TOKEN` 和 `WEREAD_PLATFORM_URL` 不再读取，确认新工作流成功后可以从 Repository Secrets 删除。

## 4. 首次验证

1. 打开 `Actions -> WeChat Article Sync`。
2. 点击 `Run workflow`，分支选择 `master`。
3. `max_pages` 保持 `1`，只检查每个公众号最新一页。
4. 确认 `Check synchronization credentials` 和 `Synchronize articles` 成功。
5. 有新文章时，工作流会提交 `content: sync N WeChat article(s)`；没有新文章时不会产生提交。

正文详情与媒体下载仍包含纯图片文章保护：文章没有可见文字时，必须成功解析并保存至少一张正文图片，否则保留到下一次同步重试。

## 5. Key 池行为

`RAPIDAPI_KEYS` 支持以下两种格式：

```json
["key-1", "key-2", "key-3"]
```

```json
{"keys":["key-1","key-2","key-3"]}
```

同步器不会输出 Key。每天以不同位置作为首选 Key，同一天的两次任务优先从同一位置开始，从而把月度调用量分配到账号池。Key 顺序首尾相接；某个 Key 失败后立即尝试下一个，切换成功后该次任务的后续请求继续使用新 Key。下一天会按日期重新计算起点，不需要在仓库中保存额度状态。

RapidAPI 负责记录每个账号的实际剩余额度。遇到以下情况会尝试下一个 Key：

- HTTP `401`、`403`：Key 无效、未订阅或无权限。
- HTTP `429`：RapidAPI 套餐额度或速率限制。
- HTTP `5xx`：RapidAPI 或上游暂时不可用。
- 业务码 `100`、`302`、`303`、`600`、`601`、`602`：鉴权、限流、额度或权限问题。
- 业务码 `301`：第三方采集临时失败。

只有所有 Key 都失败时，任务才失败并创建或更新“微信公众号自动同步失败”Issue。HTTP `429` 是额度用完后切换 Key 的主要信号；不需要人工调整 Key 顺序。

## 6. 历史补录

日常定时任务固定通过 V1 检查最新 `1` 页。V1 已被接口提供方标记为弃用，且当前 RapidAPI 实际响应不可靠地执行 `page` 参数，因此不要在手动运行界面提高 `max_pages` 来补历史。

历史补录必须在本地显式使用 V2：

```bash
python -m wechat_sync.sync \
  --account like-a-gator \
  --history-v2 \
  --max-pages 8 \
  --delay 3
```

V2 以 `PagingInfo.Offset` 游标翻页。同步器将下一页游标保存到 `backfillOffset`，下次从该断点继续；已存在的短链接文章仍会通过“标题 + 发布日期”识别，避免重复归档。

截至 `2026-08-05`，免费套餐响应头显示每个 Key 有 50 次普通月额度，但 V2 另受每月 10 次的 Pro 子额度限制。GitHub Action 不启用 V2；历史补录应按每个 Key 最多约 8 页分批运行，保留少量额度用于重试，并查看 RapidAPI 控制台用量。

## 7. 常见故障

| 日志 | 原因 | 处理 |
| --- | --- | --- |
| 缺少 `RAPIDAPI_KEYS` | Secret 名称错误或尚未上传 | 按第 3 节重新上传 |
| Key 池不是有效 JSON | 网页粘贴内容被修改 | 使用工具重新 `--copy` 或 `--upload` |
| HTTP 401/403 | Key 无效或该账号未订阅接口 | 检查 RapidAPI 订阅并轮换 Key |
| HTTP 429 | 当前 Key 额度耗尽 | 补充 Key 或等待额度重置 |
| 业务码 301 | 上游临时采集失败 | 等待下一次定时任务，通常无需改 Secret |
| 连续多页未遇到已入库文章 | 两次同步之间新增量超过检查页数 | 手动提高 `max_pages` |
| 文章详情缺少必要字段 | 详情 V4 暂未采集到完整 HTML | 等待下一次任务重试 |
| 图片下载失败 | 微信 CDN 资源暂时不可访问 | 文章保留在 pending，下一次重试 |
| 纯图片正文没有图片 | 图片资源暂时不可用 | 文章保留在 pending，下一次重试 |

如果日志先显示“Key 池第 N/M 个不可用，尝试下一个”，随后同步成功，这是正常故障转移，不需要更新 Secret。只有全部 Key 都失败，或所有 Key 都返回 `401/403` 时，才需要检查订阅和 Key 状态。

## 8. 本地运行

本地运行只需 Python 依赖和本地 Key 池：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-wechat.txt
python -m wechat_sync.rapidapi_secrets --add
python -m wechat_sync.sync --max-pages 1 --delay 3
```

本地 Key 文件、虚拟环境和临时状态均被 Git 忽略。EdgeOne Pages 只构建静态站点，不需要配置任何 RapidAPI Secret。

## 9. 历史实现

微信读书扫码、中转接口和账号池实现冻结在 `legacy/weread-sync` 分支。旧版 Docsify 网站保存在 `legacy/docsify-archive` 分支。生产 `master` 不再依赖这两套历史实现。
