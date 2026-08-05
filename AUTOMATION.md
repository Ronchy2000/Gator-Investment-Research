# GitHub Actions 自动同步

生产分支使用 RapidAPI 上的 **Weixin/Wechat Official Accounts Platform** 获取公众号文章列表，不再依赖微信读书扫码、`vid` 或短期登录令牌。正文与图片仍由仓库下载器从微信原文地址本地化。

## 自动化流程

```text
RAPIDAPI_KEYS
  -> 按日期选择一个 Key
  -> 查询两个公众号的最新文章页
  -> Key 无效、限流或额度耗尽时自动切换
  -> 与已归档文章按 ID、链接及“标题 + 日期”去重
  -> 下载正文和图片
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

免费套餐当前显示每个账号每月 50 次请求；套餐和额度可能调整，以 RapidAPI 页面及响应头为准。当前工作流通常每月需要：

```text
2 个公众号 × 每天 2 次 × 30 天 = 约 120 次列表请求
```

5 个免费账号理论上提供约 250 次/月，足以覆盖正常增量和少量重试。不要用多个 Key 并行轰击接口；同步器会按日期分摊使用，并仅在当前 Key 不可用时故障转移。

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

名称必须填写：

```text
RAPIDAPI_KEYS
```

值是工具生成的 JSON 字符串数组。不要自行添加引号、代码块或说明文字。工作流也兼容单个 `RAPIDAPI_KEY`，但生产环境应使用 `RAPIDAPI_KEYS`。

旧的 `WEREAD_ACCOUNTS`、`WEREAD_VID`、`WEREAD_TOKEN` 和 `WEREAD_PLATFORM_URL` 不再读取，确认新工作流成功后可以从 Repository Secrets 删除。

## 4. 首次验证

1. 打开 `Actions -> WeChat Article Sync`。
2. 点击 `Run workflow`，分支选择 `master`。
3. `max_pages` 保持 `1`，只检查每个公众号最新一页。
4. 确认 `Check synchronization credentials` 和 `Synchronize articles` 成功。
5. 有新文章时，工作流会提交 `content: sync N WeChat article(s)`；没有新文章时不会产生提交。

正文下载仍包含纯图片文章保护：文章没有可见文字时，必须成功解析并保存至少一张正文图片，否则保留到下一次同步重试。

## 5. Key 池行为

`RAPIDAPI_KEYS` 支持以下两种格式：

```json
["key-1", "key-2", "key-3"]
```

```json
{"keys":["key-1","key-2","key-3"]}
```

同步器不会输出 Key。每天以不同位置作为首选 Key，同一天的两次任务优先使用同一个 Key，从而把月度调用量均匀分配到账号池。遇到以下情况会尝试下一个 Key：

- HTTP `401`、`403`：Key 无效、未订阅或无权限。
- HTTP `429`：RapidAPI 套餐额度或速率限制。
- HTTP `5xx`：RapidAPI 或上游暂时不可用。
- 业务码 `100`、`302`、`303`、`600`、`601`、`602`：鉴权、限流、额度或权限问题。
- 业务码 `301`：第三方采集临时失败。

只有所有 Key 都失败时，任务才失败并创建或更新“微信公众号自动同步失败”Issue。

## 6. 历史补录

日常定时任务固定检查最新 `1` 页。需要继续补录旧文章时，在手动运行界面提高 `max_pages`，例如 `10` 或 `20`。每个公众号每页通常返回 10 篇，页数会直接消耗 RapidAPI 请求额度。

同步器始终先检查最新页，再从索引中的 `backfillNextPage` 附近继续；已经存在的短链接文章会通过“标题 + 发布日期”识别，避免 RapidAPI 长链接造成重复归档。

不要在接近免费额度上限时一次请求 40 页。历史补录应分批运行，并查看 RapidAPI 控制台用量。

## 7. 常见故障

| 日志 | 原因 | 处理 |
| --- | --- | --- |
| 缺少 `RAPIDAPI_KEYS` | Secret 名称错误或尚未上传 | 按第 3 节重新上传 |
| Key 池不是有效 JSON | 网页粘贴内容被修改 | 使用工具重新 `--copy` 或 `--upload` |
| HTTP 401/403 | Key 无效或该账号未订阅接口 | 检查 RapidAPI 订阅并轮换 Key |
| HTTP 429 | 当前 Key 额度耗尽 | 补充 Key 或等待额度重置 |
| 业务码 301 | 上游临时采集失败 | 等待下一次定时任务，通常无需改 Secret |
| 连续多页未遇到已入库文章 | 两次同步之间新增量超过检查页数 | 手动提高 `max_pages` |
| 正文节点不存在 | 微信原文返回验证页或文章不可访问 | 等待重试或检查原文 |
| 纯图片正文没有图片 | 图片资源暂时不可用 | 文章保留在 pending，下一次重试 |

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
