# 微信公众号同步器

同步器轮询 RapidAPI 上三套微信公众号数据产品获取文章列表，正文先尝试读取微信原始 DOM；原文受限时再从两套已验证能保持图文顺序的详情接口获取 HTML。随后下载封面与正文图片，生成 Astro 使用的 Markdown 内容。

## 当前来源

| slug | 公众号 | 栏目 | 收录范围 |
| --- | --- | --- | --- |
| `huode-xinxicha` | 获得信息差 | 每日信息 | 自 `2026-06-15` 起 |
| `like-a-gator` | 像鳄鱼一样思考 | 每日复盘 | `2023-07-22` 至今，V2 历史补录已完成 |

非敏感配置位于 `accounts.json`。每个公众号通过 `seed_article_url` 中的一篇公开文章识别，不再需要微信读书 `mp_id`、`vid` 或 token。

## Key 池

本地追加 Key：

```bash
python -m wechat_sync.rapidapi_secrets --add
```

重复执行可建立 Key 池。文件保存于被 Git 忽略的 `data/wechat/rapidapi-keys.json`。上传 GitHub：

```bash
python -m wechat_sync.rapidapi_secrets \
  --upload \
  --repo Ronchy2000/Gator-Investment-Research
```

生成的 Repository Secret 名称固定为 `RAPIDAPI_KEYS`，值为 JSON 字符串数组。也可通过 `--copy` 复制后在 GitHub 网页手动配置。

多个 Key 必须合并在这一个 Secret 中，不要创建 `RAPIDAPI_KEY_1`、`RAPIDAPI_KEY_2` 等独立名称。截至 `2026-08-11` 当前生产池包含 15 个 Key；同步器支持任意非空数量并自动去重。Key 不要求订阅完全相同的产品，运行时会自动识别每个“Key × 产品”组合是否可用。

## API 使用说明

日常增量会轮询三套产品，成功后下一次请求从下一套产品开始，以利用彼此独立的套餐额度。正文优先使用微信原文，仅在原文受限时轮询前两套详情产品：

| 产品 | 文章列表 | 正文详情 | 账号标识 |
| --- | --- | --- | --- |
| [Weixin/Wechat Official Accounts Platform](https://rapidapi.com/dataapiman/api/weixin-wechat-official-accounts-platform) | `POST /api/weixin/get-account-history-articles/v2` | `GET /api/weixin/get-article-detail/v4` | 任意公开文章链接 |
| [WeChat Data](https://rapidapi.com/masxcn/api/wechat-data) | `POST /weixin/getps` | `POST /weixin/artinfo` | `biz` 先经 `/weixin/getinfo` 转为 `gh_*` |
| [WeChat Official Accounts Data API](https://rapidapi.com/venturessian/api/wechat-Wei-Xin-Gong-Zhong-Hao-official-accounts-data-api) | `GET /wechat-accounts/user-posts` | 不用于归档；实测会重排正文图片 | 配置微信号，或按公众号名称搜索 |

每套产品使用自己的 `x-rapidapi-host`，但共用同一个 `RAPIDAPI_KEYS` Key 池。以下是历史回补固定使用的 Official Accounts Platform 请求头：

```text
Host: weixin-wechat-official-accounts-platform.p.rapidapi.com
Headers:
  x-rapidapi-host: weixin-wechat-official-accounts-platform.p.rapidapi.com
  x-rapidapi-key: <你的 RapidAPI Key>
```

不要把真实 Key 写入脚本或命令历史；以下示例从环境变量读取单个 Key，仅用于理解接口。项目正式运行时使用 `RAPIDAPI_KEYS` JSON Key 池和内置故障转移。

### Official Accounts Platform 四个端点

| 名称 | 方法与参数 | 主要返回 | 适用场景 |
| --- | --- | --- | --- |
| Convert article link V1 | `GET /api/weixin/convert-article-link/v1`，查询参数 `link` | 规范化后的完整微信文章链接 | 手里只有短链接或中间链接时转换；不是文章下载接口 |
| Account history V1 | `POST /api/weixin/get-account-history-articles/v1`，查询参数 `url`、`page` | 旧版历史文章列表 | 提供方已标记过期；生产代码不再调用 |
| Account history V2 | `POST /api/weixin/get-account-history-articles/v2`，表单字段 `url`、`offset` | `MsgList` 和下一页 `PagingInfo.Offset` | 日常增量和历史补录的唯一列表接口 |
| Article detail V4 | `GET /api/weixin/get-article-detail/v4`，查询参数 `articleUrl` | 标题、公众号、摘要、封面和完整正文 HTML | 将列表中的每篇文章下载为可归档正文 |

Account history V1/V2 是两个历史文章**列表**版本。提供方已将历史文章 V1 标记为过期并要求迁移，且实测返回 `API INVALID`，因此生产代码已完全移除该调用。V2 从空游标读取最新页时负责日常增量，使用持久化游标时负责历史补录。V4 是单篇文章**详情**接口。名称相似的 Convert article link V1 是独立的链接转换工具，仍可使用，但不能列文章或下载正文。

对应的接口提供方说明：

- [文章链接转换 V1](https://docs.justoneapi.com/zh/api/wechat-official-accounts/article-link-conversion-v1)
- [公众号历史文章 V1（已弃用）](https://docs.justoneapi.com/zh/api/wechat-official-accounts/account-historical-articles-v1-deprecated)
- [公众号历史文章 V2](https://docs.justoneapi.com/zh/api/wechat-official-accounts/account-historical-articles-v2)
- [文章详情 V4](https://docs.justoneapi.com/zh/api/wechat-official-accounts/article-details-v4)

### 独立调用示例

```python
import os

import requests

host = "weixin-wechat-official-accounts-platform.p.rapidapi.com"
base_url = f"https://{host}"
article_url = "https://mp.weixin.qq.com/s/example"
headers = {
    "Accept": "application/json",
    "x-rapidapi-host": host,
    "x-rapidapi-key": os.environ["RAPIDAPI_KEY"],
}

# 可选：把短链接转换为完整链接。
converted = requests.get(
    f"{base_url}/api/weixin/convert-article-link/v1",
    headers=headers,
    params={"link": article_url},
    timeout=120,
)
converted.raise_for_status()

# 日常增量直接从 V2 最新页开始。
history = requests.post(
    f"{base_url}/api/weixin/get-account-history-articles/v2",
    headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
    data={"url": article_url, "offset": ""},
    timeout=120,
)
history.raise_for_status()

# 正文下载：把列表返回的文章 URL 传给 V4。
detail = requests.get(
    f"{base_url}/api/weixin/get-article-detail/v4",
    headers=headers,
    params={"articleUrl": article_url},
    timeout=120,
)
detail.raise_for_status()
```

实际使用应同时检查 HTTP 状态、JSON 的业务状态和返回结构，不能把 HTTP 200 直接视为成功。日常分页游标会编码产品名，避免把一种产品的 cursor/page/offset 误传给另一种产品；显式 `--history-v2` 回补仍固定使用 V2 原始 offset。本项目已经封装这些校验、产品切换、Key 切换、断点保存、去重、正文下载和图片本地化逻辑。

## 增量同步

常规本地运行：

```bash
python -m wechat_sync.sync --max-pages 1 --delay 3
```

仅同步指定公众号：

```bash
python -m wechat_sync.sync \
  --account like-a-gator \
  --max-pages 1 \
  --delay 3
```

同步器执行以下步骤：

1. 轮询三套 RapidAPI 产品获取最新文章页。
2. 使用文章 ID、规范化链接和“标题 + 发布日期”与现有索引去重。
3. 新文章加入 `pendingArticles`，下载失败时保留到下一次。
4. 优先按微信原始 DOM 归档；原文受限时轮询两套可信详情接口，再从微信 CDN 下载封面和正文图片。
5. 正文与媒体全部成功后写入 `src/content/articles` 和 `public/article-assets`。
6. 每完成一篇即原子更新 `indexes/<slug>.json`。

RapidAPI 返回完整长链接，而旧数据大量使用微信短链接，因此“标题 + 发布日期”去重是数据源迁移期间避免重复文章的必要保护。

## 历史补录

完整历史使用 V2 游标接口。V2 要把上一页返回的 `PagingInfo.Offset` 作为下一次请求的 `offset` 表单字段：

```bash
python -m wechat_sync.sync \
  --account like-a-gator \
  --history-v2 \
  --max-pages 8 \
  --delay 3
```

每页通常有 10 组群发消息。V2 在 RapidAPI 免费套餐中同时消耗普通月额度和独立的 Pro 月额度；实测每个 Key 的 Pro 月额度为 10 次，因此应分批执行。同步器把不透明游标保存在对应索引的 `backfillOffset` 中，下次从断点继续；`backfillNextPage` 仅用于显示进度。

GitHub Action 不启用 `--history-v2`。cron 配置为 `23:30 UTC` 和 `07:57 UTC`（北京时间次日 `07:30` 和当日 `15:57`），用于抵消 GitHub 调度延迟并尽量在北京时间 `09:00`、`16:30` 左右实际启动；两次任务都从空游标读取 V2 最新页。显式 `--history-v2` 只用于本地持久化历史断点。两个公众号每天检查两次约消耗 120 次 V2 Pro 调用/月，按每个 Key 10 次计算至少需要 12 个有效 Key，建议准备 15 个以覆盖 31 天、手动执行和失败重试。

每批结束后检查状态：

```bash
jq '{
  articleCount: (.articles | length),
  pendingCount: ((.pendingArticles // []) | length),
  backfillComplete,
  backfillNextPage,
  backfillOffset
}' wechat_sync/indexes/like-a-gator.json
```

继续重复同一条 `--history-v2` 命令，直到同时满足：

1. `backfillComplete` 为 `true`。
2. `backfillOffset` 为空字符串。
3. `pendingCount` 为 `0`。

这三项分别表示 V2 已返回末页、没有未使用的下一页游标、已发现文章全部下载完整。不要依赖页面显示的固定文章总数；“像鳄鱼一样思考”原先显示 562 篇，但 V2 到达 `IsEnd` 并清理 7 份旧编码损坏的重复归档后，实际有 581 篇唯一文章。截至 `2026-08-05`，该公众号历史补录已经完成，最早文章为 `2023-07-22`。以后只需让 GitHub Action 通过三套产品完成日常增量与正文下载。

## Key 故障转移

同步器分别轮询产品和 Key，均衡消耗各产品互不相通的月度额度。可用性按“产品 × Key”记录：旧 Key 没订阅某个产品时，只会在该产品中跳过，仍可继续调用它已经订阅的另外两套产品。以下情况会禁用当前运行中的单个组合并尝试该产品的下一个 Key：

- HTTP `401`、`403`、`429`。
- 业务码 `100`、`302`、`303`、`500`、`600`、`601`、`602`。

HTTP `5xx`、网络超时、连接失败和业务码 `301` 通常是产品或上游故障，与 Key 无关，因此不会把同一失败请求盲目重复到整个 Key 池，而是直接尝试下一套产品。文章列表在三套产品都失败时报告任务错误；正文在微信原文和两套可信详情产品都失败时保留 pending。所有请求都会记录产品、端点、Key 序号及 RapidAPI 返回的额度头，但不会打印 Key 内容。

HTTP `429` 是当前产品套餐额度或速率限制信号。额度由 RapidAPI 侧分别统计，无需在本地保存；下次运行仍会重新探测，不要求事先知道每个 Key 开通了哪些产品。

## 纯图片文章

正文只有图片时仍视为有效文章，但至少要成功解析并保存一张正文图片。正文图片或封面下载失败时，不会把文章写入完成索引；临时目录会被清理，文章留在 pending 队列等待重试。

## 乱码文章修复

旧版直接请求微信页面时，HTTP 编码误判可能把 UTF-8 中文保存为 `Õ`、`Ķ`、`ń`、`µ` 等高密度乱码。当前原文优先流程固定按 UTF-8 解码，不再使用该旧编码判断。若历史索引中同时存在损坏的短链接条目和正常 V2 规范条目，可执行：

```bash
python -m wechat_sync.repair_mojibake \
  --account like-a-gator \
  --delay 2
```

命令会扫描该公众号的全部本地 Markdown，为乱码条目匹配同日且发布时间接近的正常规范条目，再通过微信原文或可信详情产品重新下载正文和图片；只有全部重新下载成功后，才删除损坏的重复 Markdown、资源目录和索引项。无法唯一匹配时会停止，不会猜测删除。发布完整性检查也会阻止高密度乱码文章进入后续构建。

## 手动导入链接

已知原文链接可以绕过列表接口：

```bash
python -m wechat_sync.import_urls \
  --account like-a-gator \
  --url 'https://mp.weixin.qq.com/s/example'
```

链接较多时：

```bash
python -m wechat_sync.import_urls \
  --account like-a-gator \
  --input data/wechat/legacy-urls.md
```

导入器会验证公众号名称，并复用相同的正文和图片完整性规则。

## 添加公众号

准备一篇公开文章链接：

```bash
python -m wechat_sync.initialize \
  --slug example-account \
  --name "公众号名称" \
  --seed-url "https://mp.weixin.qq.com/s/example" \
  --biz "长链接中的__biz" \
  --earliest-date 2026-01-01
```

`biz` 不是密钥，可从该公众号任意完整文章链接的 `__biz` 查询参数取得，供 WeChat Data 自动换取 `gh_*` 原始 ID。若已知第三套产品使用的公众号微信号，可额外传 `--wechat-id`；不填写时同步器会按公众号名称尝试唯一匹配。命令只更新非敏感配置，并在缺少时创建空索引。新增栏目还需要在 `src/lib/articles.ts` 中补充前端定义。

## 输出目录

```text
src/content/articles/       文章 Markdown
public/article-assets/      本地化封面和正文图片
wechat_sync/indexes/        每个公众号的完成与 pending 索引
data/wechat/                被 Git 忽略的本地 Key 和临时输入
```

完整 GitHub Actions 配置与错误处理见 [`../AUTOMATION.md`](../AUTOMATION.md)。微信读书旧实现保存在 `legacy/weread-sync` 分支。
