# 恒忆 Evermem · 版本管理与自动更新方案

> 目标：让**国内网络环境下的普通用户**也能稳定地「知道有新版本 → 拿到安装包 → 换上新版」，
> 全程不依赖直连 GitHub；任何一环失败都必须**说人话**，不允许静默失败。
> 参考实现：**DSH-manager**（`packages/core/src/github-mirror.js`、`version-manager.js`、`doh-resolver.js`、
> `packages/marketplace/src/github-api.js`、`electron/ipc-handlers.js` 更新检查、`RELEASE.md`）。

---

## 一、现状（已具备 / 仍缺失）

**已具备（本轮刚落地）：**

- `VERSION` 文件是版本号单一事实源；CI 从 git tag 取值生成 Windows 版本信息（exe 属性可见）。
- 运行时 `GET /api/version` 返回当前版本；UI「系统 → 版本与更新」（一级模块）显示版本并跳转 Releases。
- 产物名统一为 `Evermem-<平台>-v*`，Release 由 CI 自动创建并上传，附 `SHA256SUMS.txt`。
- 数据目录与程序目录已分离（数据默认在程序同级目录，建议在「③ 数据位置」改到独立目录）。

**仍缺失：**

1. 更新检查只有「跳转网页」，没有真正的版本比对，也不知道有没有新版。
2. 全部可达性都押在 `github.com` 上，DNS 污染 / 访问不稳定时直接失败。
3. 没有可切换的更新源，没有自建接口兜底。
4. 没有内置下载、校验与替换；没有失败提示规范。

---

## 二、版本管理方案

### 2.1 版本号规则

| 项 | 规则 |
|---|---|
| 版本格式 | SemVer `major.minor.patch`，例 `0.2.3` |
| 递增规则 | **MAJOR**：数据格式/目录结构不兼容变更；**MINOR**：新增能力；**PATCH**：修复与体验改进 |
| 单一事实源 | 仓库根 `VERSION`（纯版本号，无前缀） |
| Git Tag | `v` + `VERSION`，例 `v0.2.3`（**唯一发布触发方式**） |
| Release 名称 | `Evermem (恒忆) v{version} · 桌面壳` |
| 产物命名 | `Evermem-{windows\|macos\|linux}-v{version}[.exe\|.app.zip]` |
| 运行时取值 | `mem.py`/Web 读 `VERSION` 文件（已实现），禁止代码里硬编码版本号 |

> 索引可从 Markdown 重建，所以绝大多数改动都是 MINOR/PATCH；只有改了笔记结构或目录布局才升 MAJOR。

### 2.2 发布通道

- **stable（默认）**：GitHub `releases/latest`（非 prerelease）。
- **beta（预留，暂不启用）**：prerelease 中语义版本号最高者。
  > 教训来自 DSH-manager：DSH 全是 rc 版，`/releases/latest` 恒返回 404，只能取 `/releases?per_page=1`。
  > 本项目当前只发正式版，但接口设计必须预留 `channel` 字段，避免以后返工。

### 2.3 发布流程（CI 唯一入口）

```
改 VERSION → 更新 CHANGELOG → 提交 main
→ git tag -a v0.2.4 -m "release: v0.2.4 — 中文摘要"
→ git push origin main --tags
→ CI：三平台构建（onedir 绿色版 zip/tar.gz/.app.zip + 安装版 setup/dmg/deb/rpm）
→ GUI 冒烟 → SHA256SUMS → 创建/复用 Release → 上传全部产物
（2026-10-01 起：update-manifest.json 不进 Release、不由 CI 生成）
→ 云清单（可选，固定文件）：需要更新镜像列表时手动跑 gen_update_manifest.py merge，
   上传到 www.linhut.cn/evermem/update-manifest.json（长期有效，无需每次发版）
```

本地禁止构建后手动上传产物（沿用 DSH-manager `RELEASE.md` 的硬规定）。

### 2.4 回滚

- 更新检查返回的资产带 sha256；绿色版 P3 替换时在程序目录上级保留 `Evermem.old` 备份
  （安装版由安装器卸载/重装兜底），启动自检失败自动还原；
- **回滚只动程序文件，不动数据目录**（这是数据目录必须独立设置的第二个理由）。

---

## 三、可访问性：多源更新检查

### 3.1 官方云服务器固定清单 `update-manifest.json`（默认启用，2026-10-01 定案）

一次请求同时拿到「镜像列表 + 下载专用镜像」；**版本号始终由 GitHub Release 说了算**。

> 定案（用户拍板）：清单**不进 GitHub Releases、不由 CI 生成**，改为官网云服务器上的
> **固定文件** `https://www.linhut.cn/evermem/update-manifest.json`，维护者手动生成一次、
> 长期有效。客户端检查默认先请求它；404 / 缺 channel / 缺当前平台资产一律自动降级到
> GitHub 直连 + 镜像竞速，云清单挂了不阻塞检查。
>
> 文件名为 `update-manifest.json`，**不叫 `update.json`**——后者是客户端的更新源配置文件
> （存数据目录），两者重名会在开发态同目录互相覆盖。
>
> **清单只应写低频信息（镜像列表），不写版本号**——仓库/服务器里躺着过期版本比没有更危险：
> 清单一旦被读到就是版本真相源，忘了更新会让客户端一直显示"已是最新"（已实测复现）。

### 唯一用法：只下发镜像

| 清单内容 | 维护成本 | 风险 |
|---|---|---|
| 只有 `sources.mirrors` / `sources.download_only_mirrors` | **上传一次，长期有效** | 无。版本始终来自 GitHub |

只下发镜像的清单约 400 字节、`channels` 整段不写：客户端读到后只采用它的镜像列表，
版本号继续走 GitHub 直连 + 镜像竞速。代价是不再省那一次 API 请求，换来"永不假最新"。
镜像站存活周期短（实测 8 小时内就有镜像从可用变限流），能远程改名单才是清单真正的价值。

```json
{
  "schema": 1,
  "product": "evermem",
  "generated_at": "2026-09-30T22:00:00Z",
  "channels": {
    "stable": {
      "version": "0.2.4",
      "published_at": "2026-09-30T21:00:00Z",
      "notes": "修复…；新增…",
      "assets": {
        "windows-x64": {
          "name": "Evermem-windows-v0.2.4.exe",
          "size": 219337224,
          "sha256": "78d6…ecc5",
          "urls": [
            "https://oss-cn-hangzhou.aliyuncs.com/evermem/Evermem-windows-v0.2.4.exe",
            "https://github.com/linhut/evermem/releases/download/v0.2.4/Evermem-windows-v0.2.4.exe"
          ]
        },
        "macos-arm64": { "...": "..." },
        "linux-x64":   { "...": "..." }
      },
      "previous": { "version": "0.2.3", "assets": { "...": "..." } }
    },
    "beta": null
  },
  "sources": {
    "github_api": "https://api.github.com/repos/linhut/evermem/releases/latest",
    "mirrors": ["https://gh-proxy.com/", "https://cdn.gh-proxy.org/"],
    "doh_endpoints": ["https://223.5.5.5/resolve?name={host}&type=A"]
  }
}
```

关键设计：**镜像清单与 DoH 端点也由 manifest 下发**。镜像站存活周期短（DSH-manager 实测淘汰过
ghfast.top、ghproxy.net 等多个），写死在客户端等于发布即过期；下发即可远程热修。

### 3.2 候选链与竞速策略

```
第 1 跳：自建 manifest（多个托管地址并行竞速，取最快且版本最高者）
   ├─ 命中且 generated_at 新鲜（≤24h）→ 直接返回（快路径，省一次跨境请求）
   ├─ 命中但已过期        → 必须进入第 2 跳复核（见下方"为什么必须复核"）
   └─ 全部清单地址失败    → 进入第 2 跳
第 2 跳：并行竞速，取最快成功者
   ├─ GitHub Releases API 直连
   ├─ DoH 直连（解析真实 IP 绕过 DNS 污染；Python 端为可选 P2）
   └─ manifest 下发的镜像前缀 + GitHub URL
第 2 跳结果 vs 清单结果：取版本更高者（罕见情况下 GitHub API 落后于清单）
第 2 跳也全挂、但清单可用 → 用清单结果返回，并标记 manifest_stale=true（如实告知"可能不是最新"）
全部失败 → 返回结构化错误（每个源的错误与耗时），UI 明确提示 + 手动下载链接
```

**为什么过期必须复核**：清单是"命中即返回"的快路径，一旦被 CDN 缓存住（jsDelivr 实测
`s-maxage=43200`，即最长 12 小时），缓存期内所有用户都会被判定"已是最新版本"——
发布之后反而看不到更新。所以 `generated_at` 超过 24 小时就不再信任"它说没有就没有"，
必须去 GitHub/镜像复核一次。24h 是 12h 缓存的一倍余量：发版当天清单必新鲜，快路径照常生效。

- **4xx 立即短路**（资源不存在，换源也没用），**5xx 换源重试**，重试退避 1s/2s，最多 2 轮（照搬 DSH-manager `_fetchWithRetry`）。
- UA 必须带：`Evermem/<version>`（GitHub API 拒绝空 UA）。
- 结果缓存：内存 + `update_state.json`，24 小时内不重复联网（手动点「检查更新」可 `force=1` 跳过）。

### 3.3 可切换的更新源（用户可改）

配置落在数据目录 `update.json`（与 `pmem_config.json` 同级，同样不进版本库）：

```json
{
  "channel": "stable",
  "auto_check": true,
  "manifest_url": "https://www.linhut.cn/evermem/update-manifest.json",
  "sources": ["github", "mirror"],
  "mirrors": ["https://gh-proxy.com/", "https://cdn.gh-proxy.org/"]
}
```

`manifest_url` 留空即关闭清单这一跳（默认状态）。

UI（侧栏一级模块「版本与更新 → ② 更新源」）提供：

- 开关：自动检查更新（打开设置页时检查一次，结果缓存 24 小时，**只检查不下载**）
- 自建清单地址：留空即不使用清单，改动立即保存并回读真实值
- 加速镜像：一行一个，用于版本检查；下载时额外追加"只通文件"的镜像
- 检查失败时逐源列出 `源(错误 耗时)`，并给手动下载链接（不是笼统一句"已是最新"）

### 3.4 失败必须明确（禁止静默）

接口返回（失败样例）：

```json
{
  "ok": false,
  "current": "0.2.3",
  "latest": null,
  "error": "全部更新源不可用",
  "attempts": [
    {"source": "manifest", "url": "https://www.linhut.cn/evermem/update-manifest.json", "ok": false, "elapsed_ms": 15002, "error": "超时"},
    {"source": "github",   "url": "https://api.github.com/...", "ok": false, "elapsed_ms": 3004, "error": "DNS 解析失败"},
    {"source": "mirror",   "url": "https://gh-proxy.com/https://api.github.com/...", "ok": false, "elapsed_ms": 8001, "error": "HTTP 502"}
  ],
  "manual_url": "https://github.com/linhut/evermem/releases/latest"
}
```

UI 文案（照抄即可）：

> 更新检查失败：3 个更新源均不可用（自建接口超时；GitHub DNS 解析失败；镜像 HTTP 502）。
> 当前版本 v0.2.3 可正常使用，不影响记忆功能。可稍后重试、更换更新源，或手动下载：
> `https://github.com/linhut/evermem/releases/latest`
> 〔重试〕〔更换源〕〔手动下载〕〔复制诊断信息〕

- 写日志 `update.log`（保留最近 50 条）供反馈时粘贴。
- **下载阶段失败同样要单独提示**：版本查到了但下载失败 ≠ 检查失败，两种错误文案必须分开。

---

## 四、下载与替换（分阶段落地，谨慎推进）

| 阶段 | 内容 | 风险 | 建议 |
|---|---|---|---|
| **P1** | 检查更新 + 展示新版本说明 + 多源下载链接（打开浏览器 / 复制链接） | 极低 | **先做**，能解决 80% 的"不知道有新版"问题 |
| **P2** | 内置下载：后台线程、进度条、`Range` 断点续传、**SHA256 必校验**、失败自动换源，落在 `<数据目录>/updates/` | 低 | 做，200MB 级别必须能续传 |
| **P3** | 一键替换 + 重启 + 失败回滚 | 中 | Windows 优先，macOS/Linux 次之 |

**P3 替换要点（Windows）**

1. 下载并校验通过 → 写成同目录 `Evermem.new.exe`；
2. 写一个 `update-pending.json`（含 sha256、旧文件名）到数据目录；
3. 退出时启动**脱离进程的替换脚本**（`cmd /c` + `timeout /t 2` 后执行替换再拉起程序）——
   比"运行中自替换"边界少得多；
4. 新进程启动先跑一次自检（`--smoke` 或 `/api/health`），**通过后才删除 `Evermem.old.exe`**；失败则还原旧文件并提示。
   > Windows 允许重命名正在运行的 exe（不允许删除），所以"先改名再放新文件"自替换路径可行，
   > 但推荐用脚本方案，行为可预期、可排查。

**必须同时满足的前提**

- 程序文件名固定为 `Evermem.exe`（开机自启注册表绑的是绝对路径，改名会让自启失效）。
- 数据目录必须独立于程序目录，否则替换会被数据文件干扰，用户也会误以为"更新丢数据"。
- 新 exe 同样未签名 → SmartScreen 会再弹一次，更新提示里要提前说明（沿用 USER-GUIDE 第 2.1 节第 4 步）。
- macOS 替换 `.app` 后会被重新打上 quarantine 标记 → 提示用户去「隐私与安全性 → 仍要打开」。

---

## 五、接口与文件

| 接口 | 说明 |
|---|---|
| `GET /api/version` | 当前版本（**已实现**） |
| `GET /api/update/check?force=0\|1` | 按 3.2 多源检查，返回 3.4 结构（含 `attempts`） |
| `GET /api/update/sources` / `POST /api/update/sources/save` | 读写 3.3 配置；保存后回读真实值 |
| `POST /api/update/download` | 返回 `task_id`，复用现有 `/api/task/status` 轮询进度 |
| `POST /api/update/apply` | P3：写 pending 并触发替换与重启 |

本地文件（数据目录，均不进版本库）：`update.json`（源配置）、`update_state.json`（上次检查/已下载/pending）、
`update.log`、`<数据目录>/updates/`（下载暂存）。

---

## 六、与 DSH-manager 的复用关系（哪些直接拿，哪些要改）

| DSH-manager 实现 | 能否直接复用 | 在本项目要做的调整 |
|---|---|---|
| 候选链 + 顺序回退（`ipc-handlers.js` 更新检查） | **思路 100% 复用** | 换 Python 实现：`urllib`/线程；无 `AbortController`，改用 `socket.timeout` |
| 并行竞速 + 最快胜出 + 4xx 短路 + 5xx 重试（`github-api.js`） | **逻辑复用** | 同上；退避与重试次数照搬 |
| `GITHUB_PROXIES` 清单 + 「实测淘汰」原则 | **清单与原则复用** | 镜像存活周期短 → **改由 manifest 下发**，客户端只留兜底默认值，并定期复检 |
| DoH 无污染解析（`doh-resolver.js`） | 端点清单与降级思路复用 | Python 没有 Node 的 `lookup` 钩子：需 `ssl` 手工 `wrap_socket(server_hostname=域名)` 再发 HTTP（约 40 行）。**列为 P2 可选项，不是必需项** |
| 语义化版本比较（含 rc 处理） | **规则复用** | 本项目当前只发正式版；实现 `parse_semver` 即可，字段预留 prerelease 位次 |
| UA 动态化（`dsh-manager/<ver>`） | **直接复用** | 改成 `Evermem/<ver>` |
| 失败返回 `error` 字段 + UI 明示 | **直接复用** | 额外补「手动下载链接」与「复制诊断信息」 |
| `RELEASE.md` 禁止入库清单 + 发布前检查 | **直接复用** | 见《仓库同步与发布规范》docs 同步范围章节 |
| npm `dist-tags` 双通道（latest/next） | **不适用**（本项目无 npm） | 改为 manifest 的 `channels.stable/beta` |
| 「镜像源」用户可切换按钮（安装场景） | **交互形态复用** | 已落地为「版本与更新 → ② 更新源」卡：清单地址 + 镜像列表可编辑；「逐源测试」按钮仍属 P1 |

**结论**：DSH-manager 的**策略层**（多源、竞速、4xx 短路、失败明示、清单可运维）可以直接搬；
**实现层**（Electron/Node 的 fetch、DoH、npm）全部要按 Python 重写，其中 DoH 是唯一真正新增的工作量。

---

## 七、落地顺序

1. **P0（已完成）**：`update.py`（清单可选 + GitHub 直连 + 镜像并行竞速）+ `scripts/gen_update_manifest.py`（片段 → 汇总）+ CI `manifest` 作业 + `/api/update/check|sources|sources/save` + UI 一级模块「版本与更新」+ `tests/test_update_check.py`（21 个离线用例，含清单降级与镜像接管）。
   - CI 汇总产物名为 `update-manifest.json`（**不叫 `update.json`**）：开发态数据目录与仓库根重合，同名会互相覆盖（客户端源配置也叫 `update.json`）。产物随 Release 附件分发，不提交回仓库。
2. **P1**：UI 源选择、测试源、失败提示卡片、日志。
3. **P2（1 天）**：内置下载 + 进度 + 续传 + SHA256 校验 + 换源重试。
4. **P3（1～2 天）**：Windows 替换脚本与回滚；随后 macOS / Linux。

### P0 实测记录（2026-09-30，本机 Windows）

| 场景 | 结果 |
| --- | --- |
| 自建清单未部署（HTTP 404） | 自动降级，GitHub 直连约 600ms、两个镜像约 700ms 均成功，取最快者 |
| 源改为不可达地址 | `ok=false`、`error=全部更新源不可用`、`attempts` 含 URL/耗时/错误，附手动下载入口 |
| 全部源 HTTP 404 | 同上，错误信息可读为「HTTP 404」，不抛异常、不打挂服务 |
| 命中缓存 | 24h 内不重复联网；失败不缓存，可立即重试 |

实测还纠正了一件事：**网上流传的加速源列表大半已过期**，必须自己发请求验证，不能照抄。
2026-09-30 用真实请求（本项目 release 资产 + GitHub API）逐条实测：

| 前缀 | 版本检查(API) | 大文件下载 | 结论 |
| --- | --- | --- | --- |
| `edgeone.gh-proxy.org` | ✅ 200（0.7s） | ✅ 206（0.28s，最快） | 可用 |
| `cdn.gh-proxy.org` | ✅ 200（1.2s） | ✅ 206（0.57s） | 可用 |
| `gh-proxy.com` | ✅ 200（1.1s） | ✅ 206（0.87s） | 可用 |
| `gh.llkk.cc` | ✅ 200（0.85s） | ✅ 206（0.98s） | 可用（新发现） |
| `ghproxy.net` | ❌ 403 Invalid input | ✅ 206 | **只能下载，不能查版本** |
| `ghps.cc` / `hub.gitmirror.com` / `ghproxy.homeboyc.cn` / `gh.con.sh` / `gh.ddlc.top` | ❌ 403 / 已挂 / 429 | — | 不可用（多为网页工具，不是前缀代理） |

结论落地为两条规则：

1. **检查源与下载源分开**：`DEFAULT_MIRRORS` 只放通 API 的；`DOWNLOAD_ONLY_MIRRORS`
   （ghproxy.net）只拼进下载链。下载链一定比检查链多一层。
2. **UI 给两个入口**：「下载更新」走直连，「镜像加速下载」走第一个镜像。

尚未覆盖（需部署后验证）：自建清单真实命中路径、Release 带 `SHA256SUMS.txt` 时的校验值提取。

---

## 八、风险与边界

- **不做静默自动安装**：本地优先、用户知情是本项目的立身之本，自动更新必须"检查自动、下载与安装需确认"。
- **只认 HTTPS，SHA256 必校验**，校验不过一律丢弃并提示。
- 诊断信息只含源 URL、耗时、错误类型，**不含个人数据、不含笔记内容**。
- manifest 托管域名不可用时，全部流量回落到 GitHub 与镜像；此时体验降级但功能不瘫。
- 镜像是第三方服务，只作下载加速，**不作为信任根**（信任根是 SHA256 + 自建 manifest）。
