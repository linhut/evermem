<p align="center">
  <img alt="恒忆 Evermem" src="brand/evermem-logo-full.svg" width="240">
</p>

<h1 align="center">恒忆 Evermem</h1>

<p align="center"><em>个人跨会话经验记忆系统 —— 把 AI 会话中的试错过程沉淀为本地可复用知识，下次直接复用，不再从零试起。</em></p>

<p align="center">
  <img alt="License MIT" src="https://img.shields.io/badge/License-MIT-yellow.svg">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-blue">
  <img alt="Zero Dependency" src="https://img.shields.io/badge/Dependencies-Zero-orange">
  <img alt="Platform Win/macOS/Linux" src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey">
</p>

<p align="center">
  <a href="https://github.com/linhut/evermem/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/linhut/evermem?label=release"></a>
  <a href="https://github.com/linhut/evermem/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/linhut/evermem"></a>
  <a href="https://github.com/linhut/evermem/issues"><img alt="Issues" src="https://img.shields.io/github/issues/linhut/evermem"></a>
  <a href="https://github.com/linhut/evermem/commits/main"><img alt="Last commit" src="https://img.shields.io/github/last-commit/linhut/evermem"></a>
</p>

<p align="center">
  <b>零依赖 · 全本地 · 无云端。</b><br>
  <a href="README.en.md">English</a> ·
  <a href="docs/guides/USER-GUIDE.md">零基础使用说明</a> ·
  <a href="docs/README.md">文档索引</a> ·
  <a href="CONTRIBUTING.md">贡献指南</a> ·
  <a href="SECURITY.md">安全策略</a>
</p>

---

## 目录

<p align="center">
  <a href="#简介">简介</a> ·
  <a href="#特性">特性</a> ·
  <a href="#界面预览--system-diagram">界面预览</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#使用说明">使用说明</a> ·
  <a href="#架构设计">架构设计</a> ·
  <a href="#配置">配置</a> ·
  <a href="#隐私与安全">隐私与安全</a> ·
  <a href="#文档">文档</a> ·
  <a href="#贡献指南">贡献指南</a> ·
  <a href="#许可">许可</a>
</p>

---

## 简介

恒忆（Evermem，代号 pmem）是一个**个人跨会话经验记忆系统**：它直接读取 AI 宿主（WorkBuddy / DSH / Claude Code 等）的会话落盘记录，无需任何钩子或插件通道，即可自动捕获会话中的**试错过程**——失败的命令、错误的假设、最终验证可行的方案——并沉淀为结构化的本地记忆。下一次会话开始时，这些经验会被自动检索并注入上下文，让 AI 直接复用已验证的结论，而不是靠模型重新"猜"。

**核心理念**：

- 笔记是本地 Markdown（唯一权威），索引可随时重建；
- 数据与代码分离：**记忆数据永远不进 Git**，只经加密通道备份；
- 自动抽取永不直接进正式库：候选必须经过多角色评审或人工终审。

## 特性

| 能力 | 说明 |
| --- | --- |
| 🪝 **无需钩子自动捕获** | `harvest.py` 直接扫描宿主会话落盘，配对调用与结果，识别"失败 / 重试 / 失败后成功"模式 |
| 🔗 **双通道收割** | **命令级**：命令签名碎片（成功配方 / 失败教训）；**任务级**：识别同一会话"多次失败 → 最终成功"完整任务链，产出含任务意图与最终方案的经验候选 |
| 🧑⚖️ **多角色评审自动处置** | 六官独立打分（质量 / 技术 / 合规 / 价值 / 新颖 / 实操）→ 加权共识 → 分级处置：高分转正、低质/重复归档、**涉密/危险否决一律留人工** |
| 🔒 **涉密安全优先** | 合规官检测敏感特征（涉密/身份证/令牌等）、技术官检测危险命令（`rm -rf` 等）；被否决的候选绝不自动归档隐藏，留人工处置 |
| 🧠 **检索即用** | BM25 + 中文 2/3-gram 词面匹配；三层架构（热层常驻 / 温层召回 / 冷层溯源）保证"最值钱的经验绕过检索直接进上下文" |
| 📥 **数据导入（双来源）** | 文档导入：存量 docx/xlsx/pdf 切成文本块供 AI 提炼；其他记忆导入：画像导出格式、Markdown、JSON、目录批量收，自动去重后落 `staged` |
| 🖥️ **完整 Web 界面** | 零依赖（Python 标准库）HTTP 服务：记忆浏览、候选审核、数据导入、核心经验、统计诊断、接入设置、数据与维护、数据备份、版本与更新共 9 个一级模块，明亮/暗色双主题、中英双语 |
| 💾 **多渠道备份同步** | 对象存储（S3 兼容：阿里云 OSS / 腾讯云 COS / AWS / MinIO / 百度 BOS）、SMTP 邮件、本地镜像、全量快照、百度网盘冷备；增量同步 + 加密归档 + 失败告警 |
| 🌍 **跨平台零依赖** | 纯 Python 标准库实现，Windows / macOS / Linux 通用，无第三方运行时 |

## 目录结构

```
.
├── README.md (ZH 默认) / README.en.md (EN) / CHANGELOG.md / LICENSE / VERSION
├── CONTRIBUTING.md / SECURITY.md / CODE_OF_CONDUCT.md / CITATION.cff
├── mem.py            # CLI 引擎：recall / add / show / set-status / gc / hot / candidates / reindex / stats
├── harvest.py        # 会话收割：命令级 + 任务级经验候选（无需钩子）
├── memimport.py      # 外部记忆导入引擎（画像 / Markdown / JSON / 目录，内容哈希判重）
├── recipes.py        # 配方治理（四层作用域 / 求值链 / 依赖锁）
├── update.py         # 多源更新检查（自建清单 → GitHub 直连 → 镜像竞速）
├── evermem_mcp.py    # MCP 服务（查记忆 / 存记忆 / 更新 / 核心经验）
├── backup.py / s3client.py   # 多渠道数据备份（对象存储 / SMTP / 快照 / 加密归档）
├── desktop.py        # 桌面壳（内嵌 Web 服务 + QtWebEngine，跨平台，可选）
├── paths.py          # 数据目录 / 代码目录唯一解析入口（env > 持久化配置 > 安装版数据区 > 可移植默认）
├── web/              # 零依赖 Web 界面（server.py + 原生 JS/CSS）
├── templates/        # 技能与提示词模板（唯一事实源）
├── scripts/          # 开发与运维工具（自检 / 冒烟 / 基准 / 知识扫描 / 图标生成）
├── tests/            # 回归测试
├── installers/       # 安装器脚本与向导图（Inno Setup 等）
├── assets/           # 打包用应用图标（icon.ico / icon.icns / icon.png）
├── brand/            # 品牌源（SVG）与多尺寸 PNG，运行时经 /brand/ 路由提供
├── .github/          # CI 工作流与社区健康文件
└── docs/             # design 设计 · guides 使用与运维 · dev 维护与发布 · ui 界面截图
```

## 界面预览 · System Diagram

核心界面设计稿覆盖**主要视图 → 备份与同步模块**，共 8 屏，按系统模块顺序排列。界面为内置零依赖 Web 应用（`python web/server.py` 启动），**全部设计均已落地为代码**，明亮 / 暗色双主题对等实现。

### 01 · 记忆浏览 · 桌面

> 系统主界面：侧边导航（9 个一级模块：记忆浏览 / 候选审核 / 数据导入 / 核心经验 / 统计诊断 / 接入设置 / 数据与维护 / 数据备份 / 版本与更新）、记忆检索列表、标签 / 类型 / 状态筛选与分页。

![01 记忆浏览](docs/ui/01-view-browse.png)

### 02 · 候选审核 · 桌面

> 自动收割候选的评审工作台：AI 多角色评分徽章、正文查看、"多角色评审并自动处理"入口与转正 / 存疑 / 归档操作。

![02 候选审核](docs/ui/02-view-triage.png)

### 03 · 统计诊断 · 桌面

> 系统健康度总览：笔记类型 / 状态分布、检索使用统计、收割与索引诊断。

![03 统计诊断](docs/ui/03-view-stats.png)

### 04 · 数据备份 · 桌面

> 备份与同步入口：渠道列表与状态徽标、立即备份 / 恢复、日志查看。

![04 数据备份](docs/ui/04-view-backup.png)

### 05 · 系统架构：本地 → 对象存储 → 百度云

> 数据生命周期总览：本地是唯一事实源，经多渠道**单向加密上传**至对象存储（热副本、自动调度）与百度云（冷备、手动上传）。

![05 渠道模型 · 系统架构](docs/ui/05-channel-model.png)

### 06 · 备份与同步 · 主视图（明亮 / 暗色）

> 概览统计卡片、主备份位置、渠道列表与实时状态徽标；明暗主题为对等实现。

![06 备份与同步 · 主视图](docs/ui/06-main-view-light-dark.png)

### 07 · 新增渠道 · 向导（明亮 / 暗色）

> 四步向导：选择渠道类型 → 连接参数（S3 兼容协议，内置各云预设）→ 加密与策略 → 确认保存；测试连接与密码强度校验内置于流程。

![07 新增渠道 · 向导](docs/ui/07-wizard-light-dark.png)

### 08 · 渠道状态矩阵（明亮 / 暗色）

> 渠道健康度一目了然：健康 / 警告 / 失败 / 未配置 / 冷备，状态判定来自单一事实源。

![08 渠道状态矩阵](docs/ui/08-status-matrix-light-dark.png)

## 快速开始

### 环境要求

- Python 3.10+（仅标准库，无第三方依赖）
- Windows / macOS / Linux

### 0. 直接作为桌面程序运行（可选，推荐）

> 把 9 个一级模块的界面原样作为桌面应用：内嵌本地服务 + 内嵌浏览器，无需打开浏览器标签页。

```bash
python desktop.py            # 桌面壳（单实例 / 托盘 / 关闭即最小化并询问是否停服）
```

> **开机自启动**：系统 → 接入设置 → ⑦ 桌面常驻 → 「开机自启动」开关。
> 系统登录后自动启动并静默驻留托盘；开关状态取自系统真实自启项，设置失败会回滚并提示原因。
> 浏览器/独立服务模式下该开关不可用（无系统自启权限），会显示禁用与原因。

> 数据目录解析顺序：`PMEM_HOME` 环境变量 > 数据目录 `pmem_config.json` 的 `home` 字段 > 可移植默认目录
> （打包产物为可执行文件同级目录；不用当前工作目录，避免双击 / 托盘 / 开机自启三种启动方式落到不同位置）。
> 从开发环境迁移数据到桌面版，见 [docs/guides/DESKTOP-MIGRATION.md](docs/guides/DESKTOP-MIGRATION.md)。

> 也可直接用发布产物（GitHub Release，每平台提供「绿色版」与「安装版」两种）：

> - **Windows**
>   - 绿色版：`Evermem-windows-v*-portable.zip` —— 解压出 `Evermem` 文件夹，双击其中的 `Evermem.exe`，免安装
>   - 安装版：`Evermem-setup-v*.exe` —— 双击按向导安装（自动建立开始菜单 / 可选开机自启）
> - **macOS**
>   - 绿色版：`Evermem-macos-v*.app.zip` —— 解压出 `Evermem.app` 后双击（未签名首次：右键 → 打开）
>   - 安装版：`Evermem-macos-v*.dmg` —— 打开后把 `Evermem.app` 拖入「应用程序」
> - **Linux**
>   - 绿色版：`Evermem-linux-v*-portable.tar.gz` —— 解压后进入 `Evermem/` 目录执行 `./Evermem`（GitHub 下载会丢执行位，先 `chmod +x Evermem`）
>   - 安装版：`Evermem-linux-v*.deb` —— Debian / Ubuntu 系 `sudo dpkg -i` 安装
>
> **完全不懂技术的用户请直接看**：[docs/guides/USER-GUIDE.md](docs/guides/USER-GUIDE.md)（零基础使用说明：下载哪一个文件、
> 双击后没反应/被杀软拦截/白屏怎么办、首次运行如何设置数据位置、如何更新不丢数据）。

### 1. 启动 Web 界面

```bash
cd web
python server.py          # 默认端口 8765
# 打开 http://127.0.0.1:8765
```

### 2. 使用命令行

```bash
export PMEM_HOME="<你的数据目录>"   # Windows: set PMEM_HOME=...
python mem.py recall "查询词"       # 检索记忆
python mem.py add --type procedure --title "..." --body "..." --tags a,b   # 沉淀经验
python harvest.py scan --days 7 --dry-run   # 预览收割（确认后去掉 --dry-run）
python mem.py hot --apply          # 同步热层到宿主必读文件
```

> 未设置 `PMEM_HOME` 时数据目录按「持久化配置 > 可移植默认目录」解析（源码态为脚本所在目录，打包态为可执行文件同级目录）；
> 所有路径走 `paths.py` 单一入口，代码中不存在写死的绝对路径。

## 使用说明

### 三条命令流水线

| 想做什么 | 命令 |
| --- | --- |
| 查记忆 | `mem.py recall "查询词" [--limit 5] [--all]` |
| 存记忆 | 写 Markdown 到 `notes/<type>s/`，然后 `mem.py reindex` |
| 自动挖候选 | `harvest.py scan --days 7 --dry-run`，确认后去掉 `--dry-run` |
| 导入外部记忆 | `memimport.py preview --file 画像.md` → `memimport.py import --file 画像.md` |
| 同步热层 | `mem.py hot --apply --target <项目>/.workbuddy/memory/MEMORY.md` |
| 清理体检 | `mem.py gc`（默认只体检；`--apply` 执行，`--prune` 才删原文） |
| 导出画像 | `mem.py profile --limit 5 [--out 画像.md]` |
| 自检 | `tests/test_recall.py`、`tests/test_recipes.py`、`tests/test_paths_autostart.py`、`scripts/frontend_smoke.py`、`scripts/check_all.py` |

### 数据导入（主菜单一个模块，内含两个子模块）

| 子模块 | 用途 | 产物 |
| --- | --- | --- |
| **文档导入** | 存量 docx / xlsx / pdf / pptx 切块 | 文本块进块库，供 AI 提炼成笔记 |
| **其他记忆导入** | 别的工具导出的记忆搬进来 | 直接落成笔记（默认 `staged`） |

**「其他记忆导入」分两步，顺序不能反：**

1. **① 导出记忆提示词** —— 页面给一份可直接复制的提示词（唯一事实源在
   `templates/usage-profile.prompt.md` 的 `COPY:BEGIN/END` 区间，改模板即生效）。
   粘到任意 AI 工具的新会话，让它按「指令 / 身份 / 职业 / 项目 / 偏好」产出你的使用画像。
2. **② 粘贴导入记忆** —— 把拿到的画像整段贴回下方导入框，解析成条目后勾选导入。

支持四种输入，格式自动识别：

```bash
python memimport.py preview --text "## 偏好
[2026-09-27] - 输出先给结论再给依据"          # ① 画像导出格式（## 分类 + [日期] - 条目）
python memimport.py preview --file 导出.json   # ② JSON（items/notes/memories 均可）
python memimport.py preview --file 笔记.md     # ③ Markdown（带不带 frontmatter 都收）
python memimport.py import  --dir "<其他记忆库目录>/notes"   # ④ 目录批量收 .md/.json
```

导入前会给出计划：每条标注 **可导入 / 疑似重复 / 已存在**（按内容哈希判重，重复导入天然幂等），
默认只勾可导入项，确认后写入正式笔记目录，**状态为 `staged`**——不参与检索召回，
人工在「记忆浏览」逐条确认后点「转正」才生效。导入只读取源文件，绝不改动或删除原目录。

### 候选审核流程

1. `harvest.py scan` 自动收割 → 候选进入 `notes/candidates/`（`status: staged`）；
2. Web「候选审核」页执行**多角色评审并自动处理**：高分转正、重复/低质归档、保留观察、**涉密/危险留人工**；
3. 人工终审：逐条查看正文、转正 / 存疑 / 归档；
4. `mem.py reindex` 后正式笔记进入检索池。

### 备份与同步

```bash
python backup.py status            # 查看各渠道状态
python backup.py --dry-run         # 预览将同步的内容
python backup.py                   # 执行增量同步
python backup.py --restore         # 从渠道恢复
```

详见 [docs/design/BACKUP-DESIGN.md](docs/design/BACKUP-DESIGN.md)。

跨机器或「开发环境 → 桌面版」的数据迁移（白名单、禁止项、校验与回滚）见
[docs/guides/DESKTOP-MIGRATION.md](docs/guides/DESKTOP-MIGRATION.md)；
仓库同步范围、提交规范与发布检查清单见
[docs/dev/REPO-RELEASE-CHECKLIST.md](docs/dev/REPO-RELEASE-CHECKLIST.md)。

### 分层清理（Retention）

记忆不是日志——**漏掉一条关键经验的代价，远高于多存 2MB 文本**。所以恒忆不做定时删除，
只做「分层降级 + 汇总压缩 + 冷存打包」：

| 层 | 内容 | 触发 | 动作 |
| --- | --- | --- | --- |
| T1 | 正式笔记 | — | **永不自动删除**，只提示 suspect/superseded 人工复核 |
| T2 | 候选池 | ≥60 天未处理 | 滚动移入归档区（可逆，文件保留） |
| T3 | 归档区 | ≥180 天 / ≥1000 条 / ≥200MB | 先写汇总摘要保住可检索性 → 打包冷存 zip |
| T4 | 证据流 | ≥90 天 | gzip 压缩（压缩 ≠ 删除） |

```bash
python mem.py gc                   # 只体检，不动文件（Web「统计诊断」页也有只读报告）
python mem.py gc --apply           # 执行：滚动归档 + 冷存打包 + 证据压缩
python mem.py gc --apply --prune   # 连已冷存/压缩的原文一起删（默认只压缩不删）
```

四条保障：受保护条目（`hot/keep/protect/pin`）永不清理；冷存前必写摘要；默认只压缩不删；
正式笔记永不自动删。详见 [docs/design/RETENTION.md](docs/design/RETENTION.md)。

### 导出使用画像（跨工具一致体验）

```bash
python mem.py profile --limit 5 --out 画像.md
```

本地按分类（指令/身份/职业/项目/偏好）挑候选，输出 `[YYYY-MM-DD] - 条目内容` 并附**覆盖率说明**
（明确哪些维度本地无依据，杜绝模型编造）。模板见 `templates/usage-profile.prompt.md`，
方法见 [docs/guides/PROFILE-EXPORT.md](docs/guides/PROFILE-EXPORT.md)。

## 架构设计

### 三层结构：按"被使用的确定性"分层

| 层 | 内容 | 生效方式 |
| --- | --- | --- |
| **热层** | 人工标 `hot: true` 的 ≤20 条 | 同步进宿主必读文件，会话开始即常驻，**不依赖检索** |
| **温层** | 全部笔记 | `recall` 检索，靠技能提醒触发 |
| **冷层** | `events/*.jsonl` 证据 | 只追加，用于溯源与证伪 |

### 数据流

```
AI 会话落盘 JSONL
   ↓ harvest.py（无需钩子）
候选池 notes/candidates/（staged）
   ↓ 多角色评审（六官）· 自动处置
转正(active) / 保留观察 / 归档 / 留人工(涉密危险)
   ↓ mem.py reindex
正式笔记（notes/<type>s/）→ 检索池 / 热层 / 备份
```

### 双轨制

- **代码** → Git 仓库（GitHub 公开仓库 `linhut/evermem`），含平台文档；
- **数据**（notes / events / 索引 / 配置）→ 永不进 Git，只经 `backup.py` 加密备份到对象存储 / 邮件 / 本地镜像 / 网盘冷备。

## 配置

### 环境变量

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `PMEM_HOME` | **数据目录**（代码与数据彻底分离） | 见下方解析顺序 |
| `PMEM_CHUNKS` | 文档块库目录（文档导入切块产物） | `<数据目录>/chunks` |
| `PMEM_SPACES` | 知识空间扫描根（界面「扫描根」） | `<数据目录>` |
| `PMEM_WEB_PORT` | Web 服务端口 | `8765` |
| `PMEM_SYS_PY` | 调用外部脚本所用的 Python 解释器 | 当前解释器 |
| `PMEM_NODE` | node 可执行文件（自检的 JS 语法检查用） | PATH 探测 |
| `PMEM_OPENSSL` | openssl 路径（备份加密归档用） | PATH → 常见安装位 |
| `PMEM_ARCHIVE_PASS` | 归档加密密码（≥16 位，等价于渠道字段；**勿写入脚本**） | 无（必填） |
| `PMEM_SMTP_PASS` | 邮件渠道 SMTP 密码 | 无（必填） |
| `PMEM_AUTO_HARVEST_SECONDS` | 自动收割间隔（秒） | `3600` |
| `PMEM_NO_AUTO_HARVEST` | 设为 `1` 关闭自动收割线程 | 未设（即开启） |

**数据目录解析顺序**（全走 `paths.py` 单一入口，代码中不存在写死的绝对路径）：

1. `PMEM_HOME` 环境变量（最高优先级）；
2. 数据目录下 `pmem_config.json` 的 `home` 字段（界面「数据位置」写入，跨会话一致）；
3. 安装版：系统数据目录（Windows `%APPDATA%\EvermemData`、macOS `~/Library/Application Support/Evermem`、Linux `$XDG_DATA_HOME/evermem`）；
4. 绿色版 / 源码态：程序（或脚本）所在目录。

> 刻意**不使用当前工作目录**——双击 exe、托盘启动、开机自启三种方式的 cwd 各不相同，
> 用 cwd 会让同一份数据在不同启动方式下落到不同位置。
> 数据目录与代码目录分离后，源码目录里的 `notes/` 等可作**调试数据区**（`.gitignore` 已排除，不进版本库）。

### 备份渠道（`pmem_backup.json`）

- 渠道类型：`local`（增量镜像）/ `archive`（全量快照，保留 N 份）/ `remote`（ssh/scp）/ `mail`（SMTP 附件）/ `s3`（对象存储）/ `baidu-pan`（网盘冷备）
- 对象存储凭证与**归档加密密码**均为配置项（Web 向导填写），**代码中无任何写死的密钥**；
- 归档包使用 AES-256-CBC（openssl pbkdf2，20 万次迭代）加密后出本机，明文密钥永不落盘。

## 隐私与安全

- **数据不出本地**：全量记忆数据仅存本机，备份前加密；
- **涉密免责**：涉及国家秘密、警务、未公开政务项目的信息一律不得写入笔记；合规官会自动检测敏感特征并否决入档；
- **进 Git 前自查**：正文只留方法论，敏感细节（密钥、内网 IP、身份证号、手机号、涉密文件名全称）一律用占位符；
- **危险命令拦截**：含 `rm -rf`、`del /s`、`DROP TABLE` 等危险操作的候选自动留人工，绝不归档隐藏。

## 文档

> 完整索引见 [docs/README.md](docs/README.md)。

**使用与运维**

| 文档 | 说明 |
| --- | --- |
| [docs/guides/USER-GUIDE.md](docs/guides/USER-GUIDE.md) | 零基础使用说明（下载哪个文件、首次运行、排障） |
| [docs/guides/USAGE.md](docs/guides/USAGE.md) | 详细使用手册（命令流水线与文件布局） |
| [docs/guides/DESKTOP-MIGRATION.md](docs/guides/DESKTOP-MIGRATION.md) | 数据迁移（开发环境 → 桌面版，白名单与回滚） |
| [docs/guides/MULTI-MACHINE.md](docs/guides/MULTI-MACHINE.md) | 多机部署指南 |
| [docs/guides/PROFILE-EXPORT.md](docs/guides/PROFILE-EXPORT.md) | 使用画像导出 |

**设计与规格**

| 文档 | 说明 |
| --- | --- |
| [docs/design/ARCHITECTURE.md](docs/design/ARCHITECTURE.md) | 架构设计（分层、目录、路径解析、宿主集成） |
| [docs/design/BACKUP-DESIGN.md](docs/design/BACKUP-DESIGN.md) | 备份与同步设计规格 |
| [docs/design/STATUS-FLOW.md](docs/design/STATUS-FLOW.md) | 记忆生命周期状态流转 |
| [docs/design/RETENTION.md](docs/design/RETENTION.md) | 分层清理（保留策略） |
| [docs/design/DISTILL-RULES.md](docs/design/DISTILL-RULES.md) | 记忆提取规范（什么该进库） |
| [docs/design/RECIPES.md](docs/design/RECIPES.md) | 配方治理（四层作用域与版本化） |

**维护与发布**

| 文档 | 说明 |
| --- | --- |
| [docs/dev/REPO-RELEASE-CHECKLIST.md](docs/dev/REPO-RELEASE-CHECKLIST.md) | 仓库同步范围、提交规范与发布检查清单 |
| [docs/dev/PLATFORM.md](docs/dev/PLATFORM.md) | 平台总纲与运营治理 |
| [docs/dev/TOOLS.md](docs/dev/TOOLS.md) | 脚本与工具清单 |
| [docs/dev/CODE-SIGNING.md](docs/dev/CODE-SIGNING.md) | 代码签名与分发注意事项 |
| [CHANGELOG.md](CHANGELOG.md) | 变更日志 |

## 贡献指南

欢迎任何形式的贡献——使用反馈、Issue、功能建议、Pull Request。
**完整规范见 [CONTRIBUTING.md](CONTRIBUTING.md)**，要点如下：

1. **Fork** 本仓库并创建特性分支：`git checkout -b feat/xxx`
2. **提交规范（中英双语）**：标题用 `type(scope): English summary — 中文摘要`
   （如 `fix(web): fix promote 404 — 修复转正假成功`）；重要变更在 body 里分中/英各写一段说明。
3. **质量门槛**（提交前必须全部通过）：
   - `python -m py_compile mem.py harvest.py backup.py paths.py web/server.py`
   - `node --check web/index.js && node --check web/channel.js && node --check web/i18n.js`
   - `python scripts/frontend_smoke.py`（前端契约冒烟）
   - `python -m unittest discover -s tests`（回归测试）
   - `python scripts/check_all.py`（完整自检，需允许本地端口绑定）
4. **零依赖是硬约束**：核心引擎与 Web 后端只能用 Python 标准库。
5. **纪律**：不得将任何记忆数据、密钥、涉密内容提交入库；不得写死本机盘符与用户目录；
   文档示例中的单位 / 人名一律用占位符；新功能需同步更新 README 与 CHANGELOG。

参与本项目即表示同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)；
安全类问题请按 [SECURITY.md](SECURITY.md) 的私密通道报告。

## 许可

[MIT](LICENSE) © 2026 Jose-AI · 仓库 [github.com/linhut/evermem](https://github.com/linhut/evermem) · 官网 [linhut.cn](https://www.linhut.cn)

---

*恒忆 Evermem · 经验自动进库 · 跨会话复用 · 全本地零云端*
