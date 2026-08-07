# EdgeOne Pages 托管配置

本项目是 Astro 静态站点，由 EdgeOne Pages 从 GitHub 拉取仓库、执行 `npm run build`，然后发布 `dist/`。公众号同步使用的 RapidAPI Key 池只配置在 GitHub Actions，不应出现在 EdgeOne 项目设置中。

## 一、固定配置

| 配置项 | 正确值 |
| --- | --- |
| GitHub repository | `Ronchy2000/Gator-Investment-Research` |
| Production branch | `master` |
| Root directory | 留空，即仓库根目录 |
| Framework preset | `Astro` |
| Install command | `npm ci` |
| Build command | `npm run build` |
| Output directory | `dist` |
| Node.js | `22`，并确认实际版本不低于 `22.12.0` |

仓库中的部署相关文件：

- `edgeone.json`：覆盖安装、构建、输出目录，并配置 UTF-8、安全响应头和静态资源缓存。
- `package.json`：定义 `npm run build`，并声明最低 Node.js 版本。
- `.nvmrc`：要求 Node.js 22；EdgeOne Pages 会在构建时识别并切换版本。
- `astro.config.mjs`：使用 Astro 静态输出并配置生产域名。

项目不需要 `@edgeone/astro` 适配器。该适配器用于 Astro SSR 或混合渲染；本站使用 `output: "static"`，直接发布 `dist/` 即可。

## 二、新建 EdgeOne Pages 项目

如果已经在 EdgeOne Pages 托管当前站点，请跳到第三节核对现有配置。

1. 登录 [EdgeOne Pages](https://pages.edgeone.ai/)。
2. 创建项目并选择“导入 Git 仓库”。
3. 连接 GitHub；首次连接时授权 EdgeOne 读取此仓库。
4. 选择 `Ronchy2000/Gator-Investment-Research`。
5. Production branch 选择 `master`。
6. Framework preset 选择 `Astro`。
7. Root directory 留空，不要填写 `docs`、`src` 或 `public`。
8. 确认安装命令为 `npm ci`。
9. 确认构建命令为 `npm run build`。
10. 确认输出目录为 `dist`，不要填写 `/dist` 或 `docs`。
11. 保存并执行第一次部署。

根目录的 `edgeone.json` 会覆盖控制台中对应的安装、构建和输出目录。第一次部署后，先使用 EdgeOne 提供的预览域名检查首页、归档和文章详情页，再绑定正式域名。

## 三、修改现有 Docsify 项目

原 EdgeOne Pages 项目可以继续使用，无需重建仓库连接。进入“项目设置 -> 构建部署配置”，核对：

| 旧配置可能是 | 修改为 |
| --- | --- |
| Production branch 为旧分支 | `master` |
| Build command 为空或为旧 Docsify 命令 | `npm run build` |
| Output directory 为 `docs` | `dist` |
| Root directory 为 `docs` | 留空 |
| Node.js 版本过低 | Node.js 22，实际版本至少 `22.12.0` |

同时启用 `master` 的自动生产部署。GitHub Action 添加新文章并推送后，EdgeOne Pages 才会自动发布新版本。

如果构建日志使用的是 `22.11.0` 并触发 `package.json` 的版本错误，取消控制台中的旧版本固定值，让根目录 `.nvmrc` 选择较新的 Node.js 22，再重新部署。

不要把 `RAPIDAPI_KEYS` 或 `RAPIDAPI_KEY` 添加到 EdgeOne 环境变量。Python 同步发生在 GitHub Actions；EdgeOne 只构建已经写入仓库的 Markdown 和图片。

## 四、自定义域名

当前生产域名在 `astro.config.mjs` 中配置为：

```text
https://gator.ronchy2000.top
```

在 EdgeOne Pages 项目中打开“域名管理”，添加 `gator.ronchy2000.top`，按控制台提示配置 CNAME 并启用 HTTPS。已有项目继续使用原域名时，通常只需确认域名仍关联当前生产项目。

如果以后更换域名，必须同时修改 `astro.config.mjs` 中的 `site`，否则 sitemap、RSS 和分享链接仍会指向旧域名。

## 五、自动发布链路

使用 EdgeOne 的 GitHub 仓库集成时，不需要额外配置 `EDGEONE_API_TOKEN`：

```text
北京时间 09:07 / 16:37
  -> GitHub Actions 检查微信公众号
  -> 有内容或同步状态变化时提交并推送 master
  -> EdgeOne Pages 检测 master 更新
  -> npm ci / npm run build
  -> 发布 dist
  -> 新版本替换线上版本
```

GitHub Actions 和 EdgeOne Pages 是两个独立阶段：

- GitHub Action 失败：仓库不会写入不完整文章，EdgeOne 继续保留上一版。
- GitHub Action 成功但 EdgeOne 构建失败：仓库已有新内容，但线上仍是上一版，需要查看 EdgeOne 构建日志。
- 两者都成功：网站自动显示新文章，不需要人工上传 `dist/`。

只有改用 GitHub Actions 直接调用 EdgeOne CLI 部署时，才需要配置 `EDGEONE_API_TOKEN`。当前仓库使用 Git 集成，不需要重复增加这套部署流程。

## 六、上线检查

1. 最新 Production deployment 的 Branch 是 `master`。
2. 部署关联的 Commit 与 GitHub `master` 最新提交一致。
3. 构建日志使用 Node.js 22，且版本不低于 `22.12.0`。
4. 安装和构建分别执行 `npm ci`、`npm run build`。
5. Output directory 是 `dist`。
6. 首页、`/archive/`、搜索和任意文章详情页均可访问。
7. `gator.ronchy2000.top` 的 CNAME 与 HTTPS 状态正常。
8. GitHub 手动运行 `WeChat Article Sync` 后，有新提交时 EdgeOne 自动产生下一次部署。

EdgeOne 必须为 HTML 返回以下响应头：

```text
Content-Type: text/html; charset=utf-8
```

仓库已在 `edgeone.json` 中为所有 HTML 路由单独声明该响应头。不要把它合并到全局 `/*` 规则，否则 CSS、JSON 和图片也可能被错误标记为 HTML。部署后可以执行以下命令核对首页和文章页：

```bash
curl -I https://gator.ronchy2000.top/
curl -I https://gator.ronchy2000.top/articles/<文章 ID>/
```

首页访问量和访问人数使用不蒜子脚本加载，属于非关键增强。统计服务异常不应影响正文、搜索、主题切换或页面构建。

## 七、常见故障

| 现象 | 检查位置 | 处理方法 |
| --- | --- | --- |
| 构建提示找不到 `astro` | EdgeOne 构建日志 | 确认 Root directory 留空，`npm ci` 成功完成 |
| Node 版本不满足要求 | 构建日志开头 | 移除旧版本固定值，让 `.nvmrc` 选择 Node 22，确保版本至少为 `22.12.0` |
| 输出目录不存在或为空 | 构建部署配置 | 确认 Build command 是 `npm run build`，Output directory 是 `dist` |
| 部署成功但显示旧 Docsify 页面 | Production branch / Output directory | 把分支改为 `master`，输出目录从 `docs` 改为 `dist` |
| GitHub 有新提交但没有部署 | Git 仓库集成 | 启用 `master` 自动生产部署，并检查 EdgeOne 的 GitHub 授权范围 |
| 构建成功但文章图片 404 | 部署文件和 GitHub 提交 | 确认对应 `public/article-assets/` 已提交，并查看 Action 完整性检查结果 |
| 页面路径刷新后 404 | 输出目录或部署版本 | 确认发布的是 Astro 生成的 `dist`，不是源码目录或旧 `docs` |
| 正式域名打开旧项目 | 域名管理 / DNS | 确认 CNAME 指向当前 EdgeOne Pages 项目，并移除冲突记录 |
| Action 成功但网页仍未更新 | GitHub commit 与 EdgeOne deployment | 对比提交 SHA；不一致时重新部署最新生产版本 |
| EdgeOne 页面中文乱码，但 Vercel 正常 | 正式域名的 `Content-Type` 响应头 | 确认响应包含 `charset=utf-8`；重新部署最新 `master`，再清理 EdgeOne 缓存并强制刷新浏览器 |

如果只有部分地区或网络仍显示乱码，先保留响应中的 `EO-LOG-UUID`，再用不同网络执行 `curl -I` 对比。最新部署已生效且响应头正确时，问题通常是区域节点或浏览器缓存；在 EdgeOne 控制台刷新缓存后仍未恢复，应把发生时间、访问地区、URL 和 `EO-LOG-UUID` 提交给 EdgeOne 支持。

EdgeOne Pages 对项目总存储、部署文件数量和单文件大小存在平台限制。历史图片继续增加时，应在构建日志中关注 `storage limit`、`file count` 和 `file size` 错误。

## 八、不应配置或提交的内容

- 不在 EdgeOne 中配置 `RAPIDAPI_KEYS` 或 `RAPIDAPI_KEY`。
- 不在 EdgeOne 中配置 GitHub PAT、RapidAPI Key 或任何历史扫码凭据。
- 不提交本地 `data/wechat/rapidapi-keys.json` 或任何 API Key。
- 不把 Output directory 设置成 `docs` 或仓库根目录。
- 不提交本地生成的 `dist/`；由 EdgeOne Pages 每次构建生成。

## 官方参考

- [EdgeOne Pages：Astro 框架配置](https://edgeone.ai/document/160427672961769472)
- [EdgeOne Pages：构建指南](https://edgeone.ai/document/159419364821458944)
- [EdgeOne Pages：edgeone.json](https://pages.edgeone.ai/document/edgeone-json)
- [EdgeOne Pages：排障指南](https://edgeone.ai/document/177540027705036800)
- [EdgeOne Pages：GitHub Actions 部署](https://pages.edgeone.ai/document/use-github-actions)
