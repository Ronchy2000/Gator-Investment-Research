# 微信公众号同步器

同步器当前管理两个来源：

| slug | 公众号 | 栏目 | 已配置范围 |
| --- | --- | --- | --- |
| `huode-xinxicha` | 获得信息差 | 每日信息 | 自 `2026-06-15` 起 |
| `like-a-gator` | 像鳄鱼一样思考 | 每日复盘 | 截至 `2026-08-05` 已归档 453 篇，并持续增量与补档 |

在账号页面记录总数为 562 篇时，首个微信读书登录账号取得最近 99 篇，追加多个账号并刷新失效凭据后，历史窗口分批开放至 448 篇。中转列表目前停在 `2024-08-23`，但人工提供的原文链接证明更早文章仍然存在；其中 `2024-08-20` 至 `2024-08-22` 的 3 篇已通过直接链接回填，历史缺口由 114 篇降至 111 篇。后续每日新增文章不计入这项历史缺口。

结论是：缺口来自中转服务没有枚举出完整历史窗口，不是原文失效，也不是下载器遗漏。定时 Action 继续负责两个公众号的新文章增量同步；这 111 篇旧文章只在本地执行一次性回填，完成后提交文章、资源和索引即可。

## 本地使用

首次使用时创建环境并扫码：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-wechat.txt
python -m wechat_sync.auth
```

同步全部配置账号：

```bash
python -m wechat_sync.sync --max-pages 20 --delay 2
```

只同步一个账号：

```bash
python -m wechat_sync.sync --account like-a-gator --max-pages 20 --delay 2
```

同步器会：

- 从 `wechat_sync/accounts.json` 读取全部目标公众号。
- 为每个来源维护 `wechat_sync/indexes/<slug>.json`，账号之间不会共用分页游标或失败队列。
- 日常先检查最新页；大规模历史回补未完成时，再从已保存的页码附近续传并重叠一页去重。
- 已知公众号总数大于本地归档数时，会在预计页数内循环探测稀疏历史窗口；新增账号从第 1 页重新扫描，空页之后的非空页面不会被跳过。
- 已有本地索引时，第 1 页临时为空只会跳过当次增量边界检查，不会阻断后续历史页面回补。
- 单个账号请求超时、连接失败或返回 `401`、`429`、`5xx` 时自动切换到账号池中的下一个账号。
- 使用文章 ID 和规范化原文链接双重去重。
- 将失败项写入对应索引的 `pendingArticles`，下次执行时优先重试。
- 将正文保存到 `src/content/articles/`，封面和正文图片保存到 `public/article-assets/`。
- 纯图片正文必须至少解析出一张可用图片，所有远程正文图片成功本地化后才会入库。
- 单篇成功后立即原子更新索引，中断时不会丢失已完成进度。

## 回填列表接口遗漏的旧文章

### 已知原文链接

已经取得原文链接时，不需要扫码凭据，也不会消耗微信读书中转接口额度：

```bash
python -m wechat_sync.import_urls \
  --account like-a-gator \
  --url 'https://mp.weixin.qq.com/s/example-1' \
  --url 'https://mp.weixin.qq.com/s/example-2'
```

链接较多时可放入任意 UTF-8 文本或 Markdown 文件，每行格式不限，命令会提取其中全部微信原文链接：

```bash
python -m wechat_sync.import_urls \
  --account like-a-gator \
  --input data/wechat/legacy-urls.md
```

导入器会核对页面显示的公众号名称，使用文章 ID 和规范化链接去重，并复用日常同步器的纯图片正文与图片本地化逻辑。目标公众号不匹配、微信返回验证页或任一必需资源下载失败时不会写入索引。

### 自动发现剩余历史链接

微信读书中转接口无法返回 `2024-08-23` 之前的窗口，因此本地历史回填使用 Just One API 的“[账户历史文章 V2](https://docs.justoneapi.com/zh/api/wechat-official-accounts/account-historical-articles-v2)”接口。它按公众号原始 ID 和上一页返回的游标连续翻页，比按日期逐天查询更适合补齐完整历史。该第三方接口只用于本地一次性补档，不参与 GitHub Action。

1. 在 [Just One API 控制台](https://dashboard.justoneapi.com/) 注册并创建 token。接口价格、权限和配额以控制台当前信息为准。
2. 使用隐藏输入保存到被 Git 忽略的本地文件，token 不会出现在终端历史中：

```bash
python -m wechat_sync.history_backfill --save-token
```

如不希望保存文件，也可以只在当前终端会话设置环境变量 `JUSTONE_API_TOKEN`；环境变量优先于本地 token 文件。

3. 运行游标回填。每轮默认最多查询 20 页，链接与游标保存在被 Git 忽略的 `data/wechat/history-backfill/like-a-gator.json`：

```bash
python -m wechat_sync.history_backfill \
  --account like-a-gator \
  --max-pages 20 \
  --delay 2
```

重复执行同一命令会从上次游标继续，并优先重试已经发现但尚未下载成功的链接。脚本使用原文链接，以及“标题 + 发布日期”双重识别现有文章，因此扫描较新的页面不会重复下载。`562` 是当时页面显示的数量快照，后续仍有日常新文章发布，因此脚本只在接口明确返回游标结束时标记历史遍历完成，不使用固定文章总数提前停止。

如只想先收集链接、不下载正文，可添加 `--discover-only`。需要废弃现有游标并从第一页重新扫描时才添加 `--reset-state`。token 只应存在于本地环境或被忽略的 `data/wechat/justone-token`，不需要也不应上传为 GitHub Repository Secret。

## 添加公众号

先准备一个公开文章链接，再执行：

```bash
python -m wechat_sync.initialize \
  --slug example-account \
  --name "公众号名称" \
  --seed-url "https://mp.weixin.qq.com/s/example" \
  --earliest-date 2026-01-01
```

命令会更新 `accounts.json`，并只在索引不存在时创建新的空索引，不会覆盖已有文章。新增账号后还应在 `src/lib/articles.ts` 中补充前端栏目定义。

## 凭据

本地扫码凭据保存在被 Git 忽略的 `data/wechat/credentials.json`，不得提交到仓库。重复执行扫码命令时，新账号追加到有序池尾，同一账号则原位更新：

```bash
python -m wechat_sync.auth
```

GitHub Actions 使用一个 Repository Secret：`WEREAD_ACCOUNTS`。旧版 `WEREAD_VID` 与 `WEREAD_TOKEN` 仅作单账号兼容后备。

可安全上传到 GitHub：

```bash
python -m wechat_sync.github_secrets --repo Ronchy2000/Gator-Investment-Research
```

或复制到剪贴板后在 GitHub 网页创建/更新同名 Secret：

```bash
python -m wechat_sync.github_secrets --copy WEREAD_ACCOUNTS
```

客户端默认从池首调用；遇到 401、429、5xx 或列表空页时自动尝试下一账号。手动把 `--max-pages` 设为大于 1 时，新增账号会触发历史断点重探；定时 Action 固定使用 1 页，只负责增量。凭据没有可供 Action 自动使用的 refresh token，失效账号需要用原微信号重新扫码并更新账号池 Secret。完整流程见 [../AUTOMATION.md](../AUTOMATION.md)。

## 参数与退出状态

```bash
python -m wechat_sync.sync --max-pages 20 --delay 2
```

- `--account` 只同步指定账号 slug，可重复传入；省略时同步全部。
- `--max-pages` 是每个公众号的单次列表页上限，最大为 40；Action 定时运行默认使用 1。
- `--delay` 控制列表页、文章及账号之间的请求间隔秒数。

第一页暂时为空时会自动重试三次。一个公众号失败不会阻止另一个公众号保存已完成结果，但命令最终会返回非零状态并触发 Action 告警。
