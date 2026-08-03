# Cloudflare Pages 托管配置

本项目是 Astro 静态站点。Cloudflare Pages 只需要从 GitHub 拉取仓库、执行 `npm run build`，然后发布 `dist/`。微信公众号的扫码凭据只配置在 GitHub Actions，不应出现在 Cloudflare。

## 一、项目的固定配置

| 配置项 | 正确值 |
| --- | --- |
| GitHub repository | `Ronchy2000/Gator-Investment-Research` |
| Production branch | `master` |
| Root directory | 留空，即仓库根目录 |
| Framework preset | `Astro` |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Node.js | `22`，仓库通过 `.nvmrc` 固定 |

仓库中的相关文件：

- `package.json`：定义 `npm run build` 和 Node 版本要求。
- `.nvmrc`：指定 Node.js 22。
- `astro.config.mjs`：配置静态输出和生产域名。
- `wrangler.toml`：声明 Pages 输出目录 `./dist`。
- `public/_headers`：配置静态缓存和基础安全响应头。

不需要在 Cloudflare 中运行 Python。Python 同步发生在 GitHub Actions，提交完成后 Cloudflare 只构建已经写入仓库的 Markdown 和图片。

## 二、新建 Cloudflare Pages 项目

如果已有原站点并希望保留域名和历史部署，请跳到“第三节：修改现有项目”。

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)。
2. 打开 `Workers & Pages`。
3. 点击 `Create application`，选择 Pages 的 Git 仓库导入方式。
4. 连接 GitHub；如果首次连接，授权 Cloudflare GitHub App 读取此仓库。
5. 选择 `Ronchy2000/Gator-Investment-Research`。
6. Production branch 选择 `master`。
7. Framework preset 选择 `Astro`。
8. Root directory 留空，不要填写 `docs`、`src` 或 `public`。
9. Build command 填写 `npm run build`。
10. Build output directory 填写 `dist`，不要写 `/dist` 或 `docs`。
11. 保存并执行第一次部署。

新建的 Pages 项目默认使用较新的构建系统。仓库的 `.nvmrc` 会要求 Node.js 22；通常不需要额外添加 `NODE_VERSION` 环境变量。

第一次部署成功后，Cloudflare 会提供一个 `*.pages.dev` 地址。先打开该地址确认首页、归档和文章详情页可以访问，再绑定正式域名。

## 三、修改现有 Docsify 项目

原来的 Cloudflare Pages 项目可以继续使用，不需要删除项目、重建域名或修改 DNS。进入现有 Pages 项目后，打开 `Settings -> Builds & deployments`，修改生产构建配置：

| 旧配置可能是 | 修改为 |
| --- | --- |
| Production branch 为旧分支 | `master` |
| Build command 为空或 Docsify 命令 | `npm run build` |
| Build output directory 为 `docs` | `dist` |
| Root directory 为 `docs` | 留空 |
| 旧 Node.js 版本 | Node.js `22` / 构建系统 v3 |

同时确认 Production deployments 的自动部署已启用。Cloudflare 需要监听 `master` 的每次提交，GitHub Action 添加新文章后才会自动发布。

如果当前项目仍使用旧构建镜像，优先升级到 Build system version 3。无法升级时，在 Production 和 Preview 的环境变量中设置：

```text
NODE_VERSION=22.16.0
```

新构建系统通常会读取仓库根目录的 `.nvmrc`，无需重复设置。不要把 `WEREAD_ACCOUNTS`、`WEREAD_VID` 或 `WEREAD_TOKEN` 添加到 Cloudflare 环境变量。

保存后手动触发一次 `Retry deployment` 或推送一个正常提交，确认构建日志中执行的是 `npm run build`，最终上传目录是 `dist`。

## 四、自定义域名

当前生产域名在 `astro.config.mjs` 中配置为：

```text
https://gator.ronchy2000.top
```

如果继续使用原 Cloudflare Pages 项目，原有自定义域名通常会保留，无需重新配置。

如果新建了 Pages 项目：

1. 打开该项目的 `Custom domains`。
2. 点击 `Set up a custom domain`。
3. 输入 `gator.ronchy2000.top`。
4. 按 Cloudflare 提示创建或确认 DNS 记录。
5. 等待证书签发完成，再访问 HTTPS 地址。

如果以后更换域名，必须同时修改 `astro.config.mjs` 中的 `site`，否则 sitemap、RSS 和分享链接仍会指向旧域名。

## 五、自动发布链路

完成 Git 集成后，无需 Cloudflare API Token。每天的发布过程为：

```text
北京时间 10:00 / 18:30
  -> GitHub Actions 检查微信公众号
  -> 有新文章时提交并推送 master
  -> Cloudflare Git 集成检测到 master 更新
  -> npm install / npm run build
  -> 发布 dist
  -> 原子替换线上版本
```

没有新文章时，GitHub Action 不创建空提交，因此 Cloudflare 不会进行无意义的重复构建。

Cloudflare 和 GitHub Actions 是两个独立阶段：

- GitHub Action 失败：仓库没有完整的新提交，Cloudflare 继续保留上一版。
- GitHub Action 成功但 Cloudflare 失败：仓库已经有新文章，但线上继续保留上一版，需要检查 Cloudflare 构建日志。
- 两者都成功：网页自动显示新文章，不需要人工上传 `dist/`。

## 六、首次上线验收

建议按以下顺序检查：

1. Cloudflare 最新 Production deployment 的 Branch 是 `master`。
2. 部署关联的 Commit 与 GitHub `master` 最新提交一致。
3. 构建日志使用 Node.js 22，并成功执行 `npm run build`。
4. Build output directory 是 `dist`。
5. `*.pages.dev` 地址可以访问首页、`/archive/` 和任意文章详情页。
6. 正式域名证书正常，HTTP 会跳转到 HTTPS。
7. GitHub 手动运行 `WeChat Article Sync` 后，有新提交时 Cloudflare 自动产生下一次部署。

首页访问量和访问人数使用不蒜子脚本加载，属于非关键增强。首次访问可能显示占位符，统计服务失败也不应影响正文、搜索、主题切换或页面构建。

## 七、常见故障

| 现象 | 检查位置 | 处理方法 |
| --- | --- | --- |
| 构建提示找不到 `astro` | Cloudflare 构建日志 | 确认 Root directory 留空，安装阶段成功执行 `npm install`/`npm ci` |
| Node 版本不满足要求 | 构建日志开头 | 使用构建系统 v3；必要时设置 `NODE_VERSION=22.16.0` |
| 部署成功但显示旧 Docsify 页面 | Build output / Production branch | 把输出从 `docs` 改为 `dist`，分支改为 `master` 后重新部署 |
| GitHub 有新提交但没有部署 | Builds & deployments | 启用 `master` 的 automatic production deployments，检查 GitHub App 仓库权限 |
| Cloudflare 构建成功但文章图片 404 | 部署文件和 GitHub 提交 | 确认对应 `public/article-assets/` 文件已提交，并查看 Action 完整性检查结果 |
| 页面路径刷新后 404 | 输出目录或部署版本错误 | 确认部署的是 Astro 生成的 `dist`，不是源码目录或旧 `docs` |
| 正式域名打开旧项目 | Custom domains / DNS | 确认域名绑定到当前 Pages 项目，移除冲突的旧 Pages 绑定 |
| Action 成功但网页仍未更新 | GitHub commit 与 Cloudflare deployment | 对比提交 SHA；如果不一致，重试最新生产部署 |

## 八、Cloudflare 中不应配置的内容

- 不配置 `WEREAD_ACCOUNTS`、`WEREAD_VID` 或 `WEREAD_TOKEN`。
- 不配置 GitHub PAT。
- 不配置扫码二维码或 `credentials.json`。
- 不把 Build output directory 设置成 `docs` 或仓库根目录。
- 不上传本地生成的 `dist/` 到 Git；由 Cloudflare 每次构建生成。

## 官方参考

- [Cloudflare：部署 Astro 站点](https://developers.cloudflare.com/pages/framework-guides/deploy-an-astro-site/)
- [Cloudflare：Pages 构建镜像与 Node 版本](https://developers.cloudflare.com/pages/configuration/build-image/)
- [Cloudflare：分支构建控制](https://developers.cloudflare.com/pages/configuration/branch-build-controls/)
- [Cloudflare：Git 集成](https://developers.cloudflare.com/pages/configuration/git-integration/)
- [Cloudflare：自定义域名](https://developers.cloudflare.com/pages/configuration/custom-domains/)
