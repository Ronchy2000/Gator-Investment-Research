# 微信公众号同步器

同步器通过 RapidAPI 获取公众号文章列表和完整文章 HTML，再下载封面与正文图片，生成 Astro 使用的 Markdown 内容。这样不会用列表接口返回的微信长链接直接请求正文，避免触发微信验证码页面。

## 当前来源

| slug | 公众号 | 栏目 | 收录范围 |
| --- | --- | --- | --- |
| `huode-xinxicha` | 获得信息差 | 每日信息 | 自 `2026-06-15` 起 |
| `like-a-gator` | 像鳄鱼一样思考 | 每日复盘 | 持续增量并补录历史 |

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

多个 Key 必须合并在这一个 Secret 中，不要创建 `RAPIDAPI_KEY_1`、`RAPIDAPI_KEY_2` 等独立名称。当前生产池包含 9 个 Key；同步器支持任意非空数量并自动去重。

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

1. 通过 RapidAPI 已弃用但额度较宽松的 V1 接口获取最新列表页。
2. 使用文章 ID、规范化链接和“标题 + 发布日期”与现有索引去重。
3. 新文章加入 `pendingArticles`，下载失败时保留到下一次。
4. 通过 RapidAPI 文章详情 V4 接口取得正文 HTML，再从微信 CDN 下载封面和正文图片。
5. 正文与媒体全部成功后写入 `src/content/articles` 和 `public/article-assets`。
6. 每完成一篇即原子更新 `indexes/<slug>.json`。

RapidAPI 返回完整长链接，而旧数据大量使用微信短链接，因此“标题 + 发布日期”去重是数据源迁移期间避免重复文章的必要保护。

## 历史补录

完整历史必须使用 V2 游标接口，不能把 V1 的 `page` 当作可靠的历史回补方式。V2 要把上一页返回的 `PagingInfo.Offset` 作为下一次请求的 `offset` 表单字段：

```bash
python -m wechat_sync.sync \
  --account like-a-gator \
  --history-v2 \
  --max-pages 8 \
  --delay 3
```

每页通常有 10 组群发消息。V2 在 RapidAPI 免费套餐中同时消耗普通月额度和独立的 Pro 月额度；实测每个 Key 的 Pro 月额度为 10 次，因此应分批执行。同步器把不透明游标保存在对应索引的 `backfillOffset` 中，下次从断点继续；`backfillNextPage` 仅用于显示进度。

GitHub Action 不启用 `--history-v2`。自动任务每天只读取 V1 最新一页，以免两次定时任务迅速耗尽 Pro 额度。历史补录应在本地显式执行，完成后提交生成的文章、资源和索引。

## Key 故障转移

同步器每天从不同 Key 开始，均衡消耗多个 RapidAPI 账号的月度额度。某个 Key 失败后按池中顺序切换，成功后该次任务继续使用新 Key。以下情况会切换到下一个 Key：

- HTTP `401`、`403`、`429`、`5xx`。
- 业务码 `100`、`301`、`302`、`303`、`500`、`600`、`601`、`602`。
- 网络连接失败或请求超时。

所有 Key 都失败时，该公众号同步失败并由 Action 更新告警 Issue。Key 内容不会打印。

HTTP `429` 是套餐额度或速率限制信号。额度由 RapidAPI 侧统计，无需在本地保存；下次运行仍会按日期选择起点，并在遇到已耗尽 Key 时继续故障转移。

## 纯图片文章

正文只有图片时仍视为有效文章，但至少要成功解析并保存一张正文图片。正文图片或封面下载失败时，不会把文章写入完成索引；临时目录会被清理，文章留在 pending 队列等待重试。

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
  --earliest-date 2026-01-01
```

命令只更新非敏感配置，并在缺少时创建空索引。新增栏目还需要在 `src/lib/articles.ts` 中补充前端定义。

## 输出目录

```text
src/content/articles/       文章 Markdown
public/article-assets/      本地化封面和正文图片
wechat_sync/indexes/        每个公众号的完成与 pending 索引
data/wechat/                被 Git 忽略的本地 Key 和临时输入
```

完整 GitHub Actions 配置与错误处理见 [`../AUTOMATION.md`](../AUTOMATION.md)。微信读书旧实现保存在 `legacy/weread-sync` 分支。
