# 微信公众号同步器

当前同步目标固定为 `获得信息差`，首次收录范围从 `2026-06-15` 开始。

## 本地使用

首次使用时创建环境并扫码：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-wechat.txt
python -m wechat_sync.auth
python -m wechat_sync.initialize
```

执行同步：

```bash
python -m wechat_sync.sync
```

同步器会：

- 从 `wechat_sync/account.json` 读取唯一目标公众号和最早收录日期。
- 首次补齐范围内的全部历史文章，后续根据 `wechat_sync/index.json` 只下载新增文章。
- 将正文保存到 `src/content/articles/`。
- 将封面和正文图片保存到 `public/article-assets/`，并把正文图片地址替换为本地路径。
- 单篇失败时不写入完成索引，使后续运行可以自动重试。

## 凭据

本地扫码凭据保存在被 Git 忽略的 `data/wechat/credentials.json`，不得提交到仓库。
GitHub Actions 使用以下 Secrets：

- `WEREAD_VID`
- `WEREAD_TOKEN`

凭据失效后，需要重新运行 `python -m wechat_sync.auth` 并更新 Secrets。

## 同步参数

```bash
python -m wechat_sync.sync --max-pages 20 --delay 2
```

- `--max-pages` 限制单次列表翻页数量。
- `--delay` 控制列表页和文章之间的请求间隔秒数。

第一页暂时返回空列表时会自动重试三次。遇到凭据失效、接口限流或正文异常时，命令以非零状态结束并保留已完成结果。
