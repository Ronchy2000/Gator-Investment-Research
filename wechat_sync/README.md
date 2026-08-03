# 微信公众号同步器

同步器当前管理两个来源：

| slug | 公众号 | 栏目 | 已配置范围 |
| --- | --- | --- | --- |
| `huode-xinxicha` | 获得信息差 | 每日信息 | 自 `2026-06-15` 起 |
| `like-a-gator` | 像鳄鱼一样思考 | 每日复盘 | 当前双账号池可见的 199 篇，并持续增量与补档 |

账号页面显示“像鳄鱼一样思考”共有 562 篇。首个微信读书登录账号取得最近 99 篇，追加第二个登录账号后又补齐 100 篇。同步器会在未来扩充账号池时重新探测历史断点，但不会把接口尚未枚举的文章标记为已下载。

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
- 使用文章 ID 和规范化原文链接双重去重。
- 将失败项写入对应索引的 `pendingArticles`，下次执行时优先重试。
- 将正文保存到 `src/content/articles/`，封面和正文图片保存到 `public/article-assets/`。
- 纯图片正文必须至少解析出一张可用图片，所有远程正文图片成功本地化后才会入库。
- 单篇成功后立即原子更新索引，中断时不会丢失已完成进度。

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

客户端默认从池首调用；遇到 401、429 或历史空页时自动尝试下一账号。新增账号会触发历史断点重探。凭据没有可供 Action 自动使用的 refresh token，失效账号需要用原微信号重新扫码并更新账号池 Secret。完整流程见 [../AUTOMATION.md](../AUTOMATION.md)。

## 参数与退出状态

```bash
python -m wechat_sync.sync --max-pages 20 --delay 2
```

- `--account` 只同步指定账号 slug，可重复传入；省略时同步全部。
- `--max-pages` 是每个公众号的单次列表页上限，最大为 40；Action 定时运行默认使用 10。
- `--delay` 控制列表页、文章及账号之间的请求间隔秒数。

第一页暂时为空时会自动重试三次。一个公众号失败不会阻止另一个公众号保存已完成结果，但命令最终会返回非零状态并触发 Action 告警。
