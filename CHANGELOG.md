# 变更日志

## [0.2.11] - 2026-10-08（修复浏览器 HEAD/OPTIONS 请求误报 501）

### 缺陷修复

- **Web 服务对 HEAD / OPTIONS 请求误报 501**：Python 标准库 `BaseHTTPRequestHandler` 对未实现的
  `do_HEAD` / `do_OPTIONS` 一律回 `501 Unsupported method`，而本服务只实现了 GET/POST。
  浏览器 / QWebEngine 探测资源（favicon、缓存检查）、`curl -I`、CORS 预检发出 HEAD/OPTIONS 时，
  前端会误显示「候选列表加载失败：HTTP 501」（历史收割证据：`501 Unsupported method ('HEAD')`）。
  已补 `do_HEAD`（复用 GET 路由、只回响应头不回 body）与 `do_OPTIONS`（回 Allow 头），
  实测：HEAD `/index.js` 200、OPTIONS `/api/candidates` 204、GET 与 POST 全部不受影响。
- 注：`server.py` 编译进打包产物（PyInstaller `--paths web` 收集为模块），**明文热改不生效**，
  本修复必须随 v0.2.11 重新打包分发；绿色版请更新此版本或同步官方包。

### 说明

- 本地明文副本（`_internal/web/server.py`）已同步本修复（CRLF）；源码态直接生效。

## [0.2.10] - 2026-10-07（仓库去敏与规范化 + 首启可用性修复 + Marvis 宿主接入）

### 安全与隐私

- **清除代码与全部提交历史中的真实单位名、姓氏称谓与本地绝对路径**，统一改为中性占位符：
  政务单位、业务部门、活动组委会、负责人、指挥中心；`<数据目录>`、`<工作区>`、`<项目目录>`、`python`。
  命名空间标识 `org:yjxt` / `org:mzw` 改为 `org:gov-a` / `org:org-b`。
  历史侧用 `git filter-repo --replace-text` / `--replace-message` 重写 **50 个提交与全部 tag**；
  12 组关键词全历史扫描 **0 命中**。重写前的完整镜像与 bundle 已离线备份。

### 跨平台

- **路径判定改为盘符无关**，不再假设 `C:` / `F:` 存在：`web/server.py` 的「来源是否本地文档」判定
  改按三类前缀（Windows 盘符 / UNC 共享 / POSIX 绝对路径）识别；`backup.py` 的目标盘枚举改为
  运行时探测（Windows 逐盘符、POSIX 走 `/`、`/Volumes`、`/media`、`/mnt`），openssl 由环境变量推导；
  `scripts/knowledge_scan.py` 的顶层目录识别、`scripts/scan_spaces.py`、`web/i18n.js`、`web/index.js`
  同步去盘符。

### 仓库结构

- 目录按 GitHub 规范整理：`docs/` 按 **design / guides / dev** 三分组（`git mv` 20 篇）并新增
  `docs/README.md` 文档索引；`docs/design/ARCHITECTURE.md` **整篇重写**——原文描述的是从未实现的
  PySide6 分层方案，现改为描述已实现架构（零依赖 Python + Web UI）。新增 `.gitattributes`
  （统一换行符、标注二进制与第三方资源）与 `.editorconfig`。
- 补齐开源社区文件：`CONTRIBUTING.md`、`SECURITY.md`、`CODE_OF_CONDUCT.md`、`CITATION.cff`，
  以及 `.github/` 下的 bug / feature issue 表单、PR 模板与 `dependabot.yml`。
- README 双语重写：改用动态徽章、补三类文档导航、环境变量表补全至 11 项；
  修正「私人库」这一事实性错误（仓库实为公开）。

### 修复

- **全新数据根上无法保存第一条笔记（新装即不可用）**：`ensure_data_root()` 只预建
  `notes/`、`events/`、`updates/`，没有建笔记类型子目录（`notes/lessons`、`notes/procedures`、`notes/facts`），
  而 `POST /api/note` 直接写 `notes/<类型>/…` → `FileNotFoundError`，界面只显示「内部错误」。
  首次启动、或用户把「数据位置」指到一个空目录时必现。修复：`paths.ensure_data_root()` 预建三类子目录，
  且 `web/server.py` 落盘前按需 `mkdir`（双保险）。
  实测：全新空目录 `POST /api/note` 由 500 `{"error": "内部错误：FileNotFoundError"}` → **200 `{"ok": true, "id": …, "status": "staged"}`**。
- **删除受限的环境里服务静默启动失败**：`ensure_data_root()` 的写探测用 `unlink()` 清理探测文件。
  在删除被策略/守卫拦截的环境里，这一步会失败——极端情况下守卫**直接终止进程**（无 traceback），
  表现为「服务起不来但看不到任何原因」。修复：探测文件**只写不删**（探测目的是「能不能写」而非「能不能删」），
  留一个已被 `.gitignore` 的 `.pmem-*` 覆盖的标记文件。

### 变更

- **`scripts/check_all.py` 回归自检改为完全隔离，并修掉三处「假成功」**：
  1. 写用例（`POST /api/note`）改打在**隔离数据根**（正式数据根的上一级 `_pmem_check_tmp`）上——
     原来直接在正式库里建笔记再用 `unlink()` 清理，清理失败就把测试笔记永久留在用户的记忆库里
     （本机已累积 14 条），且清理抛错会让脚本**中途终止：后段检查不跑、汇总行不打印**，输出看着却像全 OK。
  2. 两个自启实例改用**动态空闲端口**（原来写死 8765，若桌面端/绿色版已在运行，子进程 bind 失败，
     用例会静默打到「别人的实例」上，测的不是本次代码）。
  3. 汇总改为 `atexit` 兜底 + **失败返回非零退出码**（原来只有一行 print，异常中断则连汇总都没有，且永远 exit 0）。
- 新增 2 项断言：两个实例各自就绪、以及「测试笔记未污染正式库（且写入成功）」——
  后者刻意要求**必须真的取到 id**，否则断言是空的（不写「没拿到 id 就算通过」）。

### 新增

- **「接入设置 → ① 技能安装」新增 Marvis（腾讯马维斯）宿主**：一键写入
  `~/.marvis/skills/custom/personal-memory/SKILL.md`。Marvis 的 custom 技能约定与 Claude/WorkBuddy 同构
  （`skills/<来源>/<技能名>/SKILL.md`，frontmatter 只需 `name` + `description`），因此同一份
  `templates/personal-memory.SKILL.md` 直接复用，不维护第二份模板。
  - **前置条件守卫（关键）**：`~/.marvis` 是指向 `%APPDATA%\Tencent\Marvis\User\<openid>` 的**符号链接**，
    未登录客户端时该链接不存在。此时若照目标路径直接 `mkdir`，会凭空造出 `C:\Users\<you>\.marvis` 真目录——
    界面显示「已安装」但 Marvis 根本读不到，还会挡住客户端日后建立同名链接（**假成功 + 破坏用户环境**）。
    故新增 `HOST_PREREQ` / `host_prereq()`：环境未就绪时 `/api/installhost` 返回 **409 + 具体原因**，
    前端禁用安装按钮并在该行下方显示原因，而非让用户点下去拿到一个假成功。
  - **写入后回读校验**：安装接口写完立即回读并与模板逐字比对，不一致返回 500
    （防磁盘满 / 被杀软拦截 / 被重定向时"提示成功但文件没落盘"），成功响应带 `bytes` 供界面回显。
  - **MCP 通道如实说明**：Marvis 的自定义 MCP 定义保存在客户端私有加密文件
    （`marvis_seckv/marvis_agent.mskv`，magic + 密文，外部不可写入），恒忆不尝试代写，
    仅在④兼容说明中写明"需在客户端内手动添加"，避免给出无效按钮。
  - 补齐接入设置区此前硬编码中文的 i18n：`已安装 / 未安装 / 安装 / 更新` 与④兼容说明四段正文。
  - 顺带修正用户指南里两处过期模块路径（「接入设置 → ③ 数据位置」实为「数据与维护 → ① 数据位置」、
    「⑦ 桌面常驻」实为「③ 开机启动」）。

### 验证

- 源码态端到端：宿主列表 5 项；`host_prereq` 真实/缺失两分支均按预期；`GET /api/hosts` 200 且带
  `ready`/`hint`；`POST /api/installhost{Marvis}` 200，落盘文件与模板逐字一致（4515 B）；未知宿主 400；
  重新加载显示已安装。
- 绿色版实测：真下载包解压目录 `_internal/web/*` 为明文且 exe 确实加载它（另起实例探测
  `/api/hosts` 已返回 5 个宿主），故本次改动可直接同步到部署目录、重启即生效，无需重新打包。

## [0.2.9] - 2026-10-07（并发安全加固 + 模板路径修正）

### 真实缺陷修复

- **并发读到半成品笔记导致接口 500（现象：多角色评审「候选列表加载失败：服务未响应」，稍后自愈）**：
  收割线程用 `Path.write_text` 写候选笔记（先截断再写入），界面此刻 glob 同一目录读取，
  会读到被截断的多字节字符，`read_text(encoding="utf-8")` 抛 `UnicodeDecodeError`；
  而 `parse_note` 只捕 `OSError`，异常穿透使**整个列表接口 500**。收割结束即自愈，
  故表现为"过一会儿又正常"。三层后果由轻到重：① 一条读失败拖垮整表；② 自动评审把"读空"的候选
  误判为低质而错误归档正常候选；③ **最严重**——改状态 / 改标签 / 编辑正文 / 取消核心经验等
  "读-改-写"端点读到截断内容后原样写回，**笔记正文被永久截短且不报错**。
  - 写入侧：`harvest.py` 抽出 `_atomic_write`（tmp + `os.replace`）用于候选与状态文件；
    `mem.py` 公开 `atomic_write` 供 `evermem_mcp.py`（3 处）与 `memimport.py` 复用。
  - 读取侧：`mem.parse_note` / `recipes.parse_note` 增捕 `UnicodeDecodeError` 返回 `None`；
    列表接口对单文件解析失败**降级为跳过并返回 `skipped` 计数**；"/api/note/<id>/<action>" 前置读失败
    一律返回 **409 放弃写入**，绝不把坏内容写回。
  - 前端：`api()` 非 2xx 时回显服务端真实 `error` 文本；候选列表失败提示改为带原因，
    并显示"N 条读取失败已跳过"。
  - 隔离复现验证：注入截断 UTF-8 候选文件后，修复前 `500 UnicodeDecodeError`，
    修复后 `200`（`total=1 / skipped=1`）。
- **「其他记忆导入 → 使用画像提示词」报「模板未找到或 COPY 区间缺失」**：模板本身未丢失
  （仓库与包内 `_internal/templates/` 均在，内容与用户提供原文逐字一致），真因是接口用了
  `mem.ROOT`——它等于 `paths.data_root()`（**数据根** `…/db`），而模板在**代码根**；
  同文件的 `SKILL_TEMPLATE` 用的正是 `CODE_ROOT`，仅此一处写错。改为 `CODE_ROOT` 后实测
  部署包内由 `ok:false` 变为 `ok:true`（585 字）。该卡片另改为**失败时回显实际查找路径**。

### 工程

- **CI 并行 job 创建 Release 的竞态改为幂等**：三平台 job 并行执行 check-then-create，
  后到者 `gh release create` 报 `HTTP 422 Release.tag_name already exists` 致整个 job 失败
  （v0.2.8 的 macOS job 即因此中断，其两个产物与统一校验清单双双缺失，靠 `gh run rerun --failed` 补齐）。
  现 create 失败后再确认一次：确已被并行 job 建好则放行，真的不存在才报错。

### 验证

- 发布前检查：`scripts/check_all.py` 38/38、`scripts/frontend_smoke.py` 6/6、
  `python -m unittest discover -s tests` 35 项 OK。
- 部署包端到端（打补丁后重启实测）：`/api/profile/prompt` `ok:true` 585 字、
  `/api/candidates` 200、`/api/hosts` 探针 `template:true`、`/api/stats` 200。

## [0.2.8] - 2026-10-07（自动收割缺陷修复 + 下载文档对齐）

### 真实缺陷修复

- **`harvest.py` 缺 `import os` 致自动收割静默失败**：`save_state()` 用 `os.getpid()` / `os.replace()`
  做状态文件原子写，但模块顶部从未导入 `os`，因此**每次收割都在保存游标那一步抛 `NameError`**，
  被 `web/server.py` 与 `desktop.py` 的 `except` 吞掉、只留一行 stderr。后果极具迷惑性：
  界面、检索、手动添加、候选生成全部正常，但 `harvest_state.json` 游标永不推进、收割结果重复写入——
  而自动积累经验恰恰是恒忆的核心能力。已补 `import os`；另以 AST 全仓扫描确认无其他同类漏导入。
- 验证：直接调用 `harvest.save_state()` 通过（修复前必抛 `NameError`）；完整 `harvest.cmd_scan()` 返回 0。

### 文档修正

- **下载产物命名与实际 Release 资产对齐**：`README.md`、`README.en.md`、`docs/guides/USER-GUIDE.md`
  此前仍写 Windows 为单文件 `Evermem-windows-v*.exe`、Linux 为"无后缀裸 ELF"（v0.2.3 时代形态），
  而实际产物自 v0.2.5 起已是「绿色版 + 安装版」两类，**用户照文档会找不到文件**。现统一为：
  Windows `Evermem-windows-v*-portable.zip` / `Evermem-setup-v*.exe`；
  macOS `Evermem-macos-v*.app.zip` / `Evermem-macos-v*.dmg`；
  Linux `Evermem-linux-v*-portable.tar.gz` / `Evermem-linux-v*.deb`，并分别给出解压与运行步骤。
- `docs/dev/REPO-RELEASE-CHECKLIST.md`：产物清单补全为六件表格；订正"Linux 仅裸 ELF、无 deb"的过时描述；
  新增「发布后核对 README / USER-GUIDE 下载表与实际资产一致」检查项。

### 工程与验证

- 发布前检查：`scripts/check_all.py` 38/38、`scripts/frontend_smoke.py` 6/6、
  `python -m unittest discover -s tests` 全绿。
- 官方 Windows 绿色版实测：SHA256 与 `SHA256SUMS.txt` 逐字符一致；`--smoke` 退出码 0；
  真实窗口启动监听 `127.0.0.1:8765`，`/api/health`、`/api/stats`、`/api/version`、`/api/spaces` 均 200。

## [0.2.7] - 2026-10-02（发布链路修复）

### 真实缺陷修复

- **统一校验清单（SHA256SUMS）上传统一清单任务缺少 checkout 修复**：`checksums` job 未执行
  `actions/checkout`，`gh release upload` 因无 git 上下文报
  `failed to run git: fatal: not a git repository`，导致 v0.2.6 的发布构建实际失败
  （v0.2.6 Release 的 `SHA256SUMS.txt` 为人工补传）。已为 `checksums` job 补上
  `actions/checkout@v4`（`fetch-depth: 0`），并排除 `*.log` 构建日志进入校验清单。
  本次 v0.2.7 由 CI 全自动生成并上传统一清单，无需人工干预。
- **v0.2.6 发布配套文档补提交**：`.gitignore`（补充 `.gitout.txt`、`*.out.txt`，
  移除已不再使用的 `*.spec` 构建产物例外说明）、`docs/dev/BRAND.md`（新增「工程落地对照表」章节）、
  `docs/dev/DISTRIBUTION-PLAN.md`（v0.2.6 实现状态、deb/AppImage/校验清单修复说明）、
  `installers/windows/evermem.iss` 与 `scripts/gen_update_manifest.py` 注释版本号
  同步至 0.2.7 —— 以上随 v0.2.6 改动但滞留工作区，本次随发布一并提交。

### 工程与验证

- 验证：`scripts/check_all.py` 38/38 全绿；`python -m unittest discover -s tests` 全绿。
- 发布后验证：v0.2.7 Release 三平台产物齐全，CI 自动生成统一 `SHA256SUMS.txt` 并透传上传成功。

## [0.2.6] - 2026-10-01（缺陷修复 + 品牌视觉落地）

### 真实缺陷修复

- **空数据根下 `/api/stats` 500 修复**：`mem.load_index()` 中 `max(p.stat().st_mtime for p in NOTES.rglob("*.md"))`
  在全新安装/无笔记时抛 `ValueError: max() iterable argument is empty`。
  影响：**任何新用户第一次打开程序**，「统计诊断」必 500。已用 `default=0.0` 兜底，
  并新增回归测试 `tests/test_empty_datastore.py`（3 项）。
- **侧栏「核心经验」SVG path 语法错误修复**：原 path 属性 `d` 是多个无效路径段拼接，
  QtWebEngine 控制台报 `Expected number, "…9a9 9 0 0 0 18 0c…"`，图标渲染异常。已替换为合法火焰路径。
- **Linux deb 打包修复**：`dpkg-deb --build --root-owner` 参数不存在（dpkg 1.19+ 应为 `--root-owner-group`），
  导致 deb 从未产出；同时补充 `/usr/bin/evermem` 启动器、.desktop 文件与 256px 图标。
- **Linux AppImage 构建修复**：原脚本用 `./linuxdeploy`（文件实际在 `/tmp`）+ 只复制二进制，
  修复为 `linuxdeploy --appimage-extract-and-run` + 拷贝整个 onedir + wrapper。
  仍为 `continue-on-error` 可选增强，但不至于因明显路径错误直接挂掉。
- **Release 校验清单跨平台统一**：新增 `checksums` job，下载三平台产物后生成统一 `SHA256SUMS.txt`
  并覆盖上传；原各平台 job 上传自己的 `SHA256SUMS.txt` 互相 clobber，最终 Release 里只剩 Windows 哈希。

### 品牌 Logo 全面落地

- **应用图标**：`assets/icon.ico`（16/24/32/48/64/128/256）/`assets/icon.icns`（32/64/128/256/512/1024）/
  `assets/icon.png`（256px）统一替换为品牌 Logo；脚本 `scripts/make_icon.py` 改为从 `brand/png` 零依赖打包。
- **Windows 安装向导**：`installers/windows/evermem.iss` 设置 `SetupIconFile`、
  `WizardImageFile`（246x471 透明 PNG，比例 164:314）、`WizardSmallImageFile`（147x147 透明 PNG）。
- **桌面壳**：窗口标题栏/托盘图标从 `assets/icon.ico` 加载；新增启动 splash（显示 1.4s，非冒烟/非自启）；
  新增「帮助」→「关于恒忆」对话框，展示 64px Logo + 版本 + 官网/源码链接。
- **前端 UI**：`web/index.html` 增加 `<link rel="icon">` 与 Apple touch icon，侧栏品牌区改用 `/brand/evermem-logo.svg`；
  版本与更新页新增「关于恒忆」面板，含 64px Logo 与项目信息。
- **Web 品牌路由**：`web/server.py` 新增 `/brand/` 静态路由与 `/favicon.ico` 映射，
  并加入 PyInstaller `--add-data "brand;brand"`，冻结态下单点真相源仍为 `brand/`。
- **项目介绍页**：`README.md` / `README.en.md` 页眉嵌入 `brand/evermem-logo-full.svg`，版本徽章更新为 0.2.6。

### 工程与验证

- `scripts/render_logo.js` 扩展输出：16/24/32/48/64/128/256/512/1024 PNG + 安装向导横幅/小图。
- `scripts/make_installers.sh` 增加 `/usr/bin/evermem` 启动器与 .desktop（deb/rpm），修复根目录引用。
- `harvest.py`：防御 `--min-failures 0` 时 `max()` 空可迭代对象的潜在 ValueError。
- 验证：`scripts/check_all.py` 38/38 全绿；`python -m unittest discover -s tests` 35 项全绿；
  空数据根下 `/api/stats`、`/api/notes`、`/api/hot` 均 200。

## [0.2.5] - 2026-10-01（发行形态落地：绿色版 onedir + 安装版 + 更新清单改云固定文件）

### 绿色版（onedir 免安装，替代 onefile）

- **6-1 已实现**：build.yml `--onefile` → `--onedir`（消除每次启动全量解包 219MB 的开销，
  直接解决 v0.2.3 实测的"杀软下打开极慢"）；产物命名约定
  `Evermem-windows-vX-portable.zip` / `Evermem-macos-vX.app.zip` /
  `Evermem-linux-vX-portable.tar.gz`。
- **P3 更新适配 onedir**：`apply_update()` 绿色版分支——备份整个程序目录（`Evermem.old`）→
  zip 解压替换 → 失败自动回滚 → 重启（仅 Windows 打包版）。

### 安装版（安装向导 / 卸载 / 系统集成）

- **6-2** `paths.py`：新增 `install.marker` 检测（`is_installed()`）；安装版默认数据根 =
  `%APPDATA%\EvermemData`（macOS/Linux 对应系统数据目录），与程序目录分离、卸载不丢数据。
- **6-3** 升级分流：安装版检测到新版 → 下载 setup **静默升级**（`/VERYSILENT`）而非 exe 替换。
- **6-4** `installers/windows/evermem.iss`（Inno，入库）+ CI windows job 产 `Evermem-setup-vX.exe`。
- **6-5** `scripts/make_installers.sh`：macOS dmg（hdiutil）/ Linux deb（dpkg-deb）、rpm（rpmbuild），
  CI 接入（continue-on-error，可选增强）。
- **6-6** Inno 卸载页询问是否删除 `%APPDATA%\EvermemData`（默认保留）。
- **6-7** 实例锁按数据根哈希命名（`pmem-desktop-<hash>.lock`）：绿色版/安装版可并存，同数据根仍单实例。
- **6-9** 更新 UI 按发行形态分流：安装版按钮显示「下载安装包」，确认文案提示数据保留。

### 更新清单改云服务器固定文件（用户拍板）

- **update-manifest.json 不进 GitHub Releases、不由 CI 生成**（删除 fragment/merge/上传整条链）。
- `update.py` 默认清单地址 = `https://www.linhut.cn/evermem/update-manifest.json`；
  清单只应下发镜像列表（不写版本号，防"假最新"），404/不可用自动降级 GitHub 直连 + 镜像。
- 资产匹配按「平台 × 发行形态」分流（`_asset_matches(name, key, form)`），
  GitHub 源与清单源都按当前形态挑资产。
- `scripts/gen_update_manifest.py` 保留为手动工具（原 docstring 含 CI 流程说明，已更新）。

### 其它

- 前端：更新页文案随清单策略更新（i18n 中英同步）；`/api/version` 返回 `form`/`installed`。
- 验证：`check_all.py` 38/38、单元测试 32 项全绿；本地 onedir 构建 + GUI 冒烟（--smoke）rc=0；
  绿色版 zip 结构与更新解压逻辑对齐（顶层 `Evermem/` + exe）。
- 测试修订：默认清单断言、形态资产名、`test_safe_filename` 期望纠正（点号属安全字符）、
  移除过时的"未填清单不请求"用例。
- `.spec` 文件删除（构建完全命令行化）；README/README.en/UPDATE-DESIGN/DISTRIBUTION-PLAN 同步。

## [0.2.4] - 2026-10-01（跨环境可用性与发行规范）

### 全新环境数据根自检（重要修复，提交 3caf154）

- **`paths.ensure_data_root()`**：desktop/server 启动时统一自检——预建 `notes/`、`events/`、
  `updates/` 并做可写探测；数据根不可写/不可用（如 PMEM_HOME 指向文件、只读目录）时明确
  提示引导并退出（rc=5），杜绝「界面正常打开但什么都存不下」的假成功。
- **修复 desktop.py 缺失 `import paths`**（数据根自检引入的 NameError）。
- **实测**：全新数据根首次启动自动创建完整目录结构（此前只建 `index.json`，其余目录
  要到首次写入才创建或报错）。

### 发行版本安装规范（文档）

- **`docs/dev/DISTRIBUTION-PLAN.md`**：明确两个发行形态——免安装绿色版（onedir，解压即用、
  不写注册表/系统服务）与安装版（Inno/dmg/deb，安装向导、卸载、开始菜单快捷方式、
  系统集成），含差异对比、环境依赖、安装/卸载流程、文件目录结构、验收标准，
  以及缺失需求清单（6-1~6-10，供后续分别构建两个版本）。

### 发布渠道修复（提交 0b17666）

- Release 标题与 exe 文件属性描述（FileDescription）去掉「· 桌面壳」，
  现为「Evermem (恒忆) vX.Y.Z」。

## [0.2.3] - 2026-09-30（2026-10-01 补记：审计修复与更新链路）

### 双模型审计修复（2026-10-01，提交 b2be3b8）

- **安全**：CSRF Origin 校验（跨站 POST 403）；`/api/block`、`/api/scan` 路径根约束；候选归档空 ids 拒绝；
  恢复（tar/zip）路径穿越校验。
- **崩溃修复**：`/api/extract` 未定义标识符 `SYS_PY` → `PY_ABS`；do_GET/do_POST 异常兜底；
  `channel.js` 变量遮蔽（`t`→`ty`）修复备份页多渠道渲染中断。
- **数据正确性**：GC T3 冷存方向反转修复（新增 `tests/test_gc.py`）；新建笔记毫秒 id + 按 type 落目录；
  编辑接口 type/status 白名单；全项目原子写（`_atomic_write`，5 个模块）。
- **桌面壳**：补自动收割线程（同进程）；F12 真实开发者工具；托盘创建移出页面加载回调。
- **备份**：S3 保留策略双前缀修复；告警邮件密码解混淆；备份范围补 `update.json` 与块库 `chunks`；
  归档包落系统临时目录。
- **CLI/工具**：新增 `mem.py set-status`；`--llm` 移除、`--purge/--no-purge` 互斥；`backup.py --scope` 生效；
  `recipes.py lock --project`；MCP 版本对齐 VERSION。
- **清理**：移除死代码（`app.py` / `web/launcher.py` / `scripts/fluent_preview.py`）；文档纠错
  （9 个一级模块、USAGE 入口改 desktop.py）；docs 一次性快照归档 `docs/archive/`。
- **冻结态打包**：`Evermem.spec` 与 `build.yml` 补 `VERSION` + `scripts/` 进包（修复桌面程序版本显示、
  收割、文档提取、热层同步四项功能）。

### 内置下载与一键替换（P2/P3，2026-10-01，提交 2dc94e1）

- **P2 内置下载**：`update.py download()`——Range 断点续传 + SHA256 必校验 + 镜像换源重试，
  落 `<数据根>/updates/`；UI「版本与更新」新增下载进度条；`POST /api/update/download|sources/test`。
- **P3 一键替换**：`apply_update()` 生成独立 `apply-update.bat`——延迟等待主进程退出 → 备份 `.old.exe` →
  替换 → 失败自动回滚 → 重启（Windows 打包版）；`POST /api/update/apply`。
- **同进程任务执行器**：新增 `_run_inline_task`（支持进度上报，规避冻结态子进程陷阱）。

### 数据与调试分离（2026-10-01）

- 正式数据根迁至独立数据盘目录（用户级 `PMEM_HOME` 环境变量指定）；白名单复制保留源作回滚；
  代码目录作为调试数据区（`.debug-data/`）。

### 分发形态（2026-10-01）

- `docs/dev/CODE-SIGNING.md`：Windows 签名（EV/OV 无免费路径，单位 OV 为性价比选项）、macOS 公证
  （$99/年，免费仅 xattr 引导）、Linux AppImage（免费，CI 已加 `continue-on-error` 步骤）。
- codegraph 接入：`.githooks/pre-push` 增量同步索引（`codegraph sync --quiet`，绝不阻断推送）。

### 桌面常驻：开机自启动开关

- **接入设置新增「③ 开机启动」**：小型开关「开机自启动」，系统登录后自动启动并静默驻留系统托盘。
- **状态取自系统真实值**：开关初始值、保存后状态都回读系统自启项；保存失败回滚开关并提示原因，不允许「点了就算成功」。
- **降级判定**：仅在桌面壳内可用（`PMEM_DESKTOP=1`），浏览器/独立 server 模式如实报 `unsupported` 并禁用开关。
- **跨平台自启动修复**：macOS 原错误使用 Linux XDG（`.config/autostart`），现改为 `~/Library/LaunchAgents/cn.linhut.evermem.plist`（launchd，`RunAtLoad`）；Linux 补全 XDG `.desktop` 必填字段。
- **Qt 菜单项同修**：勾选失败弹提示并把勾选态拉回系统真实状态。

### 数据根目录统一（重要修复）

- **新增 `paths.py`**：数据目录与代码目录的唯一解析入口（环境变量 > 持久化配置 > 可移植默认目录）。
- **修复冻结态目录分裂**：`mem.py` 按 `PMEM_HOME` 解析，而 `server.py` / `backup.py` / `memimport.py` / `harvest.py` / `recipes.py` / `evermem_mcp.py` 各自按 `__file__` 推导；PyInstaller 单文件下 `__file__` 落在临时解包目录，导致核心检索、界面配置、导入、备份恢复各指一个目录。现全部统一走 `paths.data_root()`。
- **默认目录不再用 cwd**：打包产物默认数据目录改为可执行文件同级目录（双击、开机自启、资源管理器启动时 cwd 各不相同，用 cwd 会让数据落到不同位置）。
- **配置文件位置统一**：`pmem_config.json` 写入数据目录，界面保存的位置就是引擎读取的位置（旧位置仍可读，平滑兼容）。
- **备份恢复修复**：local 渠道恢复不再只用本机清单枚举（本机为空时「恢复成功」却一个文件没拷），改为「本机清单 ∪ 渠道根实际文件」。
- **回归测试**：新增 `tests/test_paths_autostart.py`（优先级、配置位置、冻结态默认值、自启动降级与平台分支）。

### 文档

- 新增 `docs/guides/DESKTOP-MIGRATION.md`：开发环境 → 桌面工具的数据导出 / 迁移 / 导入 / 校验 / 回滚完整步骤。
- 新增 `docs/dev/REPO-RELEASE-CHECKLIST.md`：GitHub 同步范围、提交规范、打包与发布检查清单。

### 面向零基础用户的分发改进

- **产物命名统一**：GitHub Releases 文件从 `evergem-<平台>-v*` 改为 `Evermem-<平台>-v*`，与产品名一致。
- **新增图标资源**：`scripts/make_icon.py` 生成 `assets/icon.ico`（Windows）与 `assets/icon.icns`（macOS），打包产物在资源管理器 / Finder / Dock 中显示统一图标。
- **Windows 版本信息**：打包时自动生成 `assets/version_info.txt`，exe 属性中显示产品名、版本、版权等信息，有助于降低 SmartScreen 误报概率。
- **自动创建 GitHub Release**：`build.yml` 在 tag 触发时若 Release 不存在则自动创建（此前会提示 release not found 导致上传失败）。
- **生成 SHA256SUMS.txt**：每平台打包完成后自动生成校验文件并随 Release 上传。
- **新增版本入口**：UI「系统 → 版本与更新」显示当前版本，并提供一键跳转到 GitHub Releases 最新页。
- **新增 `docs/guides/USER-GUIDE.md`**：零基础中文使用说明（下载哪个文件、双击没反应/被杀软拦截/白屏怎么办、首次运行如何设置数据位置、如何更新不丢数据）。

### 多源更新检查（可访问性，P0）

- **新增 `update.py`**：更新检查不再依赖直连 GitHub。顺序为「自建清单（可选，留空即不启用）→ GitHub 直连 + 镜像并行竞速，取最快成功者」，清单还能远程下发镜像列表（镜像站存活周期短，必须能远程改）。
- **失败必须明示**：全部源不可用时返回 `ok=false` + 每个源的 URL / 耗时 / 错误 + 手动下载入口，界面照实提示，**不允许静默返回「已是最新版本」**。
- **源可切换**：配置存数据目录 `update.json`（`channel` / `auto_check` / `manifest_url` / `sources` / `mirrors`），保存后回读真实值；配置被改坏则退回默认，不让检查崩。
- **只缓存成功结果**（24 小时），失败不缓存，否则用户没法重试。
- **CI 自动产出清单**：每平台构建时生成资产片段（含 sha256），`manifest` 作业汇总为 `update-manifest.json` 并上传到 Release；输出名带前缀，避免与客户端配置 `update.json` 同名。
- **UI**：「版本与更新」新增「检查更新」，展示新版本 / 已是最新 / 检查失败（含每个源的耗时与手动下载）；下载走外链在浏览器打开，只给第一个非直连镜像作为「镜像加速下载」。
- **只检查不安装**：本阶段不下载、不替换任何文件（下载与替换、断点续传、回滚属后续阶段）。
- **回归测试**：新增 `tests/test_update_check.py`（10 组，全部离线：版本比较、清单降级、全源失败明示、HTTP 状态码可读化、缓存、配置读写与坏配置、GitHub 源 sha256、平台资产匹配、清单生成脚本）。
- **实测**：自建清单未部署 → HTTP 404 后由 GitHub 直连（约 600ms）与两个镜像（约 700ms）兜底成功；把源改成不可达地址 → 明确返回「全部更新源不可用」并列出尝试明细。

### 界面结构梳理：一级模块拆分

- **「版本与更新」提升为一级模块**：原为「接入设置」的第 ⑨ 张卡，现独立为侧栏入口，内含「① 更新检查 ② 更新源」两张卡。
- **新增一级模块「数据与维护」**：原「接入设置」的③④⑤三张卡（数据位置 / 核心经验同步 / 经验沉淀）移入——这三项是本机的设置与维护动作，与「接入别的 AI 工具」不是一回事。
- **「接入设置」收敛为 4 张卡**：① 技能安装 ② MCP 工具接入 ③ 开机启动（原「⑦ 桌面常驻」改名）④ 兼容说明，编号重排，顺带修掉此前缺 ⑥ 的断号。
- **父模块不再套同名卡**：一级模块的页头就是模块名，内容直接分卡，不再出现「版本与更新 › 版本与更新」这类同名嵌套（此前「数据导入」踩过同样的坑）。
- **新增 `docs/design/UI-MODULES.md`**：一级模块清单、卡片归属，以及「什么算一级模块」的判断标准，避免后续继续往一个模块里堆卡。
- **防白页回归**：`scripts/frontend_smoke.py` 新增第六项「视图路由一致性」——侧栏 `data-view` ↔ `VIEWS` ↔ `render` 分支 ↔ 模板函数，四方交叉校验（加侧栏入口却漏 render 分支会直接白页）。

### 更新清单改为「可只下发镜像列表」（修掉一个假最新）

- **问题**：清单写死版本号，命中后即返回、不再问 GitHub。维护者忘了覆盖上传 →
  用户永远看到「已是最新」。已实测复现：GitHub 上是 0.2.9、清单停在 0.2.3，界面仍显示最新版。
- **改法**：`from_manifest()` 把镜像列表与版本号解耦——清单即使没有 `channels`，
  也会先把 `sources.mirrors` / `sources.download_only_mirrors` 交给主流程，
  版本号继续由 GitHub 直连 + 镜像竞速给出（清单自身记为"未命中"，不算错误）。
- **结果**：清单可以是约 400 字节的「只下发镜像」版本，**上传一次长期有效**；
  镜像站失效时改一次清单即可，不用发新版客户端（镜像 8 小时内就有从可用变限流的）。
- **回归测试**：新增「清单只下发镜像时，版本仍来自 GitHub」用例（22 组），
  防以后有人把清单改回版本真相源。

## [0.2.2] - 2026-09-30

### 配方管理（作用域隔离与跨项目共享）

- **docs/design/RECIPES.md**：配方治理规范——四层作用域（core/org/project/session）、`scope/name@version` 命名、semver + 不可变基线、引用/播种双形态、禁止隐式覆盖、六类冲突仲裁流程。
- **recipes.py**（新增，零依赖）：`scan`（分层盘点 + 同命名空间同名 P0 + 隐式覆盖 P1 检测）/ `resolve`（就近优先求值链，主 scope + 归属组织）/ `lock`（生成 `.recipe-lock.json` 依赖锁）。
- 存量笔记兼容：frontmatter 扩展字段对 `mem.py` 解析零破坏；未标 scope 默认归项目层。

### 全项目审计与加固（2026-09-29）

- **修复数据丢失隐患**：Web API `edit` 未传正文时不再用截断摘要覆盖全文，改读原文件保留。
- **去除硬编码本机路径**：`app.py`（SYS_PY/CHUNKS/SPACES 默认值）、`scripts/check_all.py`/`bench_verify.py`/`bench_search.py`/`knowledge_scan.py`、`templates/personal-memory.SKILL.md`、USAGE/TOOLS 文档中的用户路径全部参数化或占位化（`PMEM_SYS_PY`/`PMEM_TEST_DIR` 等环境变量）。
- **Web 服务加固**：Host 白名单校验（防 DNS rebinding / 恶意网页调用本地 API）；笔记标题/标签 frontmatter 注入防护。
- **测试补强**：新增 `tests/test_recipes.py`（16 项）；`check_all.py` Web API 自启 server（消除"未起服务→14 项假失败"）、extract 用例支持 `PMEM_TEST_DIR` 跳过。

### 桌面版稳定性（白屏修复）

- **白屏修复**：GPU 受限环境（远程桌面/虚拟机/沙箱）QtWebEngine 默认无法创建 GL 上下文导致页面加载失败；`desktop.py` 默认启用软件渲染（`--no-sandbox --disable-gpu --disable-dev-shm-usage`，可用 `QTWEBENGINE_CHROMIUM_FLAGS` 覆盖）。
- **冒烟真实化**：`--smoke` 现在校验 `loadFinished`（页面真实加载成功才退出码 0），不再"服务就绪即通过"；无 Qt 回退路径同样支持冒烟自退。
- **修复自启注册**：`--register-autostart` 的 winreg 子键路径改为相对形式（原 `HKCU\` 缩写前缀不被 winreg 支持，导致 FileNotFoundError）。
- **tasklist 子进程解码加固**：单实例检测加 `errors="ignore"`，避免非 UTF-8 系统输出崩掉读取线程。

### 检索修复

- **强信号规则误杀修复**：查询含拉丁/标识符词元（如 `GUI`）且仅出现在笔记标题时被误判"零命中"返回空；现在同时检查标题索引。新增回归用例 2c。

### 发布准备

- 仓库内本机路径/示例盘符全面清理复核（`git grep` 零泄漏）；开发临时脚本统一放入 git 忽略目录并清理。


## [0.2.1] - 2026-09-29

### 桌面壳（Web 版直接作为桌面程序）

- **desktop.py**：QtWebEngine 内嵌本地 Web 服务，把 7 视图 Web 版直接作为桌面程序；
  单实例锁、系统托盘、明暗主题/中英语言菜单、F12 开发者工具、空闲端口、`PMEM_HOME` 数据目录。
- **关闭行为**：点关闭默认「最小化到托盘继续运行」，弹窗询问是否停止服务（涉及 MCP/后台钩子）；真正退出走托盘「停止服务并退出」。
- **开机自启**：`--register-autostart / --unregister-autostart`（Windows Run 键 / XDG autostart），菜单「开机自启」勾选项，`--autostart` 托盘静默常驻。
- **无头兜底**：Qt/WebEngine 不可用时自动回退「起服务 + 系统默认浏览器」。
- **打包**：CI 每平台只产出一个桌面运行包（`Evermem-<平台>-v*`，Windows exe / macOS .app.zip / Linux 二进制），替代原 cli/web/gui 三件套；GUI 冒烟以 `--smoke` 自退并断言退出码 0。


## [0.2.0] - 2026-09-29

### 候选审核批量操作与筛选 / 核心经验详情 / 文档导入指引（2026-09-29）

- **候选审核**：列表加关键词搜索与三档筛选（状态 / 类型 / AI 建议），全部前端过滤、后端契约不变；
  每条加复选框，支持全选（三态）/ 反选 / 清空（都只作用于当前筛选可见条目）；
  批量转正 / 批量存疑 / 批量归档，执行后 Toast 汇报成功 / 失败条数与失败 id。
- **修复候选转正假成功**：候选不在主索引 docs 里，旧的单条「转正 / 存疑」调
  `/api/note/<id>/status` 永远 404，却照样提示「已处理」。新增
  POST `/api/candidates/status`（`{ids:[...], status}`，批量与单条共用，直接改候选文件并重建索引），
  前端按 `updated/failed` 如实反馈。
- **核心经验详情**：整条卡片可点，复用候选审核「内容」的 `#viewMask` 弹窗，
  展示元信息（类型/状态/创建/来源/标签/文件）+ 相关记忆（按标题检索 top5，异步补位）+ 正文全文；
  「移出核心经验」按钮 stopPropagation，不再误触卡片。
- **文档导入指引**：`#paneDoc` 中与切换条重名的 `<h3>文档导入</h3>` 移除，
  原位换成「导入步骤 ①→②→③ + 注意事项」说明文案；表单 / 按钮 / 块列表 / 预览原样保留。
- **沉淀**：`notes/procedures/dev-selfcheck-recurring-mistakes-*.md` 汇总 6 类反复踩坑
  （层级、哨兵值、i18n 覆盖、路由方法、资源定位、假成功验证），挂入项目必读工作纪律。

### 发布工程（v0.2.0）

- **跨平台打包**：新增 `.github/workflows/build.yml`，Windows / Linux / macOS 三平台矩阵，
  PyInstaller 分别产出 `evermem-gui`（PySide6 桌面包）、`evermem-cli`（mem.py 命令行）、
  `evermem-web`（内嵌前端资源的 Web 服务）各一，冒烟后重命名上传 Release（tag 触发时自动附加二进制）。
- **打包适配**：`mem.py` 打包态数据目录回退「当前工作目录」（`PMEM_HOME` 仍为最高优先）；
  `web/server.py` 打包态静态资源路径改指内嵌 `web/` 资源；构建依赖清单 `requirements-build.txt`（仅 CI 用，产物运行时不依赖）。
- **同步范围**：`build/ dist/ *.spec .venv/ venv/` 一律忽略；仓库仅含代码 + 平台文档 + CI + 构建清单，
  私有配置 / 个人数据 / 密钥 / 日志一律不跟踪（内部约定见记忆库，不写入对外文档）。

### 数据导入模块（主菜单「文档导入」→「数据导入」，下含两个子模块）

- **两级结构**：主菜单项改为**数据导入**；内含 **文档导入**（保持原样，切块进块库）
  与 **其他记忆导入**（外部记忆收进笔记库）两个子模块，用分段控件 `.seg` 切换（与按钮/卡片同圆角同描边，
  只靠底色区分选中；双语文案同步）。
- **其他记忆导入 = ① 导出记忆提示词 + ② 记忆导入粘贴**：
  - ① 页面给出可直接复制的提示词（指令/身份/职业/项目/偏好 + `[YYYY-MM-DD] - 条目` 格式 + 代码块包裹 + 覆盖率说明）。
    唯一事实源是 `templates/usage-profile.prompt.md` 的 `COPY:BEGIN/END` 区间，
    由 GET `/api/profile/prompt` 读取——**前端不硬编码**，改模板即生效。
    复制走剪贴板 API，被浏览器拒绝时自动全选提示按 Ctrl+C。
  - ② 粘贴区沿用「来源 → 解析 → 列表勾选 → 导入」骨架，与文档导入视觉一致。
- **memimport.py（新）**：外部记忆导入引擎，零依赖。
  - 四种输入、格式自动探测：① 画像导出格式（`## 分类` + `[YYYY-MM-DD] - 条目`）
    ② 带/不带 frontmatter 的 Markdown（支持多篇拼接）③ JSON（`items/notes/memories` 等别名归一）
    ④ 目录批量收 `.md/.json`。
  - 导入前给计划：每条标 **可导入 / 疑似重复 / 已存在**，默认只勾可导入项。
  - 判重按**内容哈希**（id 带时间，不能用完整 id 判重，否则重复导入不幂等）。
  - 落点 `notes/<type>s/`，默认 `status: staged`——不参与检索召回，人工转正后生效。
  - 只读取源文件，绝不改动/删除被导入目录；`events/import.jsonl` 留审计。
- **API**：GET `/api/profile/prompt`（读提示词模板 COPY 区间）、POST `/api/memimport/preview`（只解析不写）、
  POST `/api/memimport/run`（写入，默认 staged）。
- **修复**：格式下拉默认传 `auto`，被 `fmt or detect_format()` 当成真实格式，画像塌成 1 条
  标题为分类名的笔记。哨兵值先归一再分派（同类哨兵：`all`/`*`/`any`/`0` 同坑）。

### 收割质量与治理（分层落地）

- **L1 收割质量**：任务级候选标题由原始口语指令蒸馏为动宾短语（`distill_intent`，正文仍保留原始指令全文）；
  踩坑取"真错误行"并过滤 Bash `Command:` 回显噪声、按 (命令,错误) 去重；最终方案不再截成 140 字残片
  （放宽到 600 字，脚本类方案附脚本正文前 40 行）。
- **L2 转正裁决唯一事实源**：新增 `promotion_decision()`（CLI 与 Web 共用），在评分与风险分级之上叠加
  **结构闸门**——任务级候选缺「任务目标/踩坑/最终方案」、方案为空、标题未蒸馏的一律留人工，不自动转正。
- **L3 热层保护**：自动收割转正的笔记默认不参与热层补足（64 条碎片不再稀释上下文），
  人工 pin 或 `mem.py hot --include-auto` 才放行。
- **否决原因可见性**：致否规则（危险命令、敏感、重复）排在规则列表首位，
  修正此前"否决原因显示成加分项（命令签名齐备）"的误导。

### 分层清理与画像导出

- **mem.py gc**：分层清理体检（T1 正式笔记永不删 / T2 候选池 ≥60 天滚动归档 / T3 归档区 ≥180 天或
  ≥1000 条或 ≥200MB 先写摘要再打包冷存 / T4 证据流 ≥90 天 gzip 压缩）。默认 dry-run，
  `--apply` 才动文件，`--prune` 才删原文。Web「统计诊断」页底部有同一份只读报告（GET /api/gc）。
- **mem.py profile**：导出使用画像草稿（指令/身份/职业/项目/偏好），按标签权重 3 / 标题权重 1 挑候选，
  附覆盖率说明；配套 `templates/usage-profile.prompt.md` 与 `docs/guides/PROFILE-EXPORT.md`。
- **docs/design/RETENTION.md**：清理机制评估与推荐方案（触发条件、策略、对检索与性能的影响、保障措施、收益风险权衡）。

- **README 双语重写**（README.md 中文 / README.en.md 英文）：按优质开源项目标准重构——徽章、特性矩阵、界面预览（System Diagram 4 图）、快速开始、使用说明、架构、配置、隐私安全、贡献指南、许可；公开维护就绪。
- **harvest 任务级提炼**：识别同一会话"多次失败→成功"完整任务链，产出 lesson 级经验候选（含任务意图/踩坑/最终方案）；防归档/转正后循环重生。
- **评审修正**：任务经验候选不再被新颖官按"主题相近"误判重复归档；涉密/危险否决一律留人工。

- **数据多渠道同步备份 v3**（规格 docs/design/BACKUP-DESIGN.md）：
  - 渠道模型：local（增量镜像，零依赖）/ archive（全量快照 zip，保留 N 份）/ remote（ssh/scp 增量镜像，可选）/ mail（SMTP 附件，可选）。
  - 每渠道独立：范围（notes/events/index/meta）、频率（小时）、启用开关、失败记录与连续失败计数。
  - 全局：自动备份（后台线程按频率轮询）、告警邮箱（连续失败≥2 发邮件，可选）、备份日志 backup.log、最近 20 条历史。
  - 同步后校验（文件数/大小）；换目标后增量不误跳（目标端存在校验）；旧单渠道配置自动迁移。
  - Web「数据备份」页升级为**渠道列表管理**（新增/删除/编辑各渠道、立即备份单渠道或全部、从渠道恢复、查看日志）；API：GET /api/backup、GET /api/backup/log、POST /api/backup/{save,run,restore}。
- 修复：GET /api/backup/log 路由错置于 POST（补 GET 分支）；增量同步换目标空同步缺陷（v2 修复，v3 保留目标端存在校验）。

## v0.1.0（2026-09-27）· 首个可发布版本

### 定位
恒忆 Evermem：个人跨会话经验记忆平台（通用知识库）。经验自动进库、跨会话复用、全本地零云端。

### 功能（全部经测试验证）
- **核心引擎 mem.py**：级联检索（意图签名/失败指纹/BM25/链接扩展）、新近度加权、热层同步与 token 预算、候选池治理（容量/TTL/AI 评分）、入库存档（add/reindex/stats/show）。
- **会话收割 harvest.py**：多宿主（WorkBuddy/DSH/atomcode）会话落盘 → 候选，无钩子依赖。
- **文档导入 ingest.py / scan_spaces.py / knowledge_scan.py**：F 盘语料 → 块库 → 提炼。
- **MCP 桥 evermem_mcp.py**：mem_read / mem_record（写前相似治理）/ mem_update / mem_hot，WorkBuddy/Claude/DSH 三宿主已配置。
- **Web 界面**（server.py，15+ API + 三层缓存）：六视图（浏览/候选审核 AI 徽章/文档导入/核心经验/统计诊断/接入设置），性能基线列表 6ms。
- **skill personal-memory**：4 宿主已安装，强制调用时机规则。
- **注入通道**：热层（WorkBuddy 20 条 + DSH 12 条）+ 工作纪律（每次会话自动注入）。
- **治理**：AI 启发式评分 + 人工终审双审核、状态机（staged→active→suspect→superseded）、写前相似治理、热层有进有出。
- **数据与代码分离**：数据（笔记/事件/索引）不进版本库，走 `backup.py` 云端备份增量同步。

### 测试（发布前全绿）
- check_all.py：35/35 通过（引擎/MCP/Web API/边界/前端/数据健康）
- bench_verify.py：16/16 通过（CLI/MCP/Web/回归 + 性能基线）
- bench_search.py：20/20 预期命中，top1 均值 167.0
- tests/test_recall.py：6 组全过（含防误召回、staged 夹具自建自删）

### 数据资产（本地，不进仓库）
- 正式笔记 65 条（procedure 50 / lesson 6 / fact 9），热层 20，F 盘块库 9 空间 9500+ 块。
- 平台文档：PLATFORM v2 / REVIEW / TOOLS / MONTHLY 模板+首报。

### 已知限制
- 检索为词面级（BM25 中文 2/3-gram），同义词依赖标签；向量检索待语料破千后引入。
- 候选 AI 评分为启发式规则，人工终审兜底；LLM 精审接口需自行配置 PMEM_AI_REVIEW（涉密环境保持离线）。
- 热层 auto-fill 补足质量存疑，热层补充一律人工评审。