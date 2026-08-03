# 增量恢复演练对照

本目录临时保留 `2026-08-03` 最新文章的原始下载结果，用于验证 GitHub Actions 能否在完成索引、Markdown 和资源同时缺失时自动恢复文章。

## 测试文章

| 字段 | 值 |
| --- | --- |
| 标题 | `8.3日韩股市低开` |
| 文章 ID | `qRFSHm1B6viK3dmMNlZGKw` |
| 原文 | `https://mp.weixin.qq.com/s/qRFSHm1B6viK3dmMNlZGKw` |
| 原 Markdown | `qRFSHm1B6viK3dmMNlZGKw/original.md.reference` |
| 原资源 | `qRFSHm1B6viK3dmMNlZGKw/assets/cover.jpg` |

原始文件校验值：

```text
Markdown SHA-256: e2adfd5fa5e587e6a1f4caea586e5e607a8ee37e98c7af0f92c7c2e02cac35a8
cover.jpg SHA-256: 048f7f86d7f51f4d988a4f78976c1f9edb337f410eb4511c57684a35da31befa
```

手动运行 `WeChat Article Sync` 后，预期自动恢复：

```text
src/content/articles/2026-08-03-qRFSHm1B6viK3dmMNlZGKw.md
public/article-assets/qRFSHm1B6viK3dmMNlZGKw/cover.jpg
wechat_sync/index.json 中对应的完成记录
```

确认恢复结果后，可以删除整个 `wechat_sync/recovery-reference/` 对照目录并提交清理。
