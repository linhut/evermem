# 变更日志

## [0.2.4] - 2026-10-01（跨环境可用性与发行规范）

### 全新环境数据根自检（重要修复，提交 3caf154）

- **`paths.ensure_data_root()`**：desktop/server 启动时统一自检——预建 `notes/`、`events/`、
  `updates/` 并做可写探测；数据根不可写/不可用（如 PMEM_HOME 指向文件、只读目录）时明确
  提示引导并退出（rc=5），杜绝「界面正常打开但什么都存不下」的假成功。
- **修复 desktop.py 缺失 `import paths`**（数据根自检引入的 NameError）。
- **实测**：全新数据根首次启动自动创建完整目录结构（此前只建 `index.json`，其余目录
  要到首次写入才创建或报错）。

### 发行版本安装规范（文档）

- **`docs/DISTRIBUTION-PLAN.md`**：明确两个发行形态——免安装绿色版（onedir，解压即用、
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

- 正式数据根迁至 `F:/EvermemData/db`（用户级 `PMEM_HOME` 环境变量）；白名单复制保留源作回滚；
  代码目录作为调试数据区（`.debug-data/`）。

### 分发形态（2026-10-01）

- `docs/CODE-SIGNING.md`：Windows 签名（EV/OV 无免费路径，单位 OV 为性价比选项）、macOS 公证
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

- 新增 `docs/DESKTOP-MIGRATION.md`：开发环境 → 桌面工具的数据导出 / 迁移 / 导入 / 校验 / 回滚完整步骤。
- 新增 `docs/REPO-RELEASE-CHECKLIST.md`：GitHub 同步范围、提交规范、打包与发布检查清单。

### 面向零基础用户的分发改进

- **产物命名统一**：GitHub Releases 文件从 `evergem-<平台>-v*` 改为 `Evermem-<平台>-v*`，与产品名一致。
- **新增图标资源**：`scripts/make_icon.py` 生成 `assets/icon.ico`（Windows）与 `assets/icon.icns`（macOS），打包产物在资源管理器 / Finder / Dock 中显示统一图标。
- **Windows 版本信息**：打包时自动生成 `assets/version_info.txt`，exe 属性中显示产品名、版本、版权等信息，有助于降低 SmartScreen 误报概率。
- **自动创建 GitHub Release**：`build.yml` 在 tag 触发时若 Release 不存在则自动创建（此前会提示 release not found 导致上传失败）。
- **生成 SHA256SUMS.txt**：每平台打包完成后自动生成校验文件并随 Release 上传。
- **新增版本入口**：UI「系统 → 版本与更新」显示当前版本，并提供一键跳转到 GitHub Releases 最新页。
- **新增 `docs/USER-GUIDE.md`**：零基础中文使用说明（下载哪个文件、双击没反应/被杀软拦截/白屏怎么办、首次运行如何设置数据位置、如何更新不丢数据）。

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
- **新增 `docs/UI-MODULES.md`**：一级模块清单、卡片归属，以及「什么算一级模块」的判断标准，避免后续继续往一个模块里堆卡。
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

- **docs/RECIPES.md**：配方治理规范——四层作用域（core/org/project/session）、`scope/name@version` 命名、semver + 不可变基线、引用/播种双形态、禁止隐式覆盖、六类冲突仲裁流程。
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
  附覆盖率说明；配套 `templates/usage-profile.prompt.md` 与 `docs/PROFILE-EXPORT.md`。
- **docs/RETENTION.md**：清理机制评估与推荐方案（触发条件、策略、对检索与性能的影响、保障措施、收益风险权衡）。

- **README 双语重写**（README.md 中文 / README.en.md 英文）：按优质开源项目标准重构——徽章、特性矩阵、界面预览（System Diagram 4 图）、快速开始、使用说明、架构、配置、隐私安全、贡献指南、许可；公开维护就绪。
- **harvest 任务级提炼**：识别同一会话"多次失败→成功"完整任务链，产出 lesson 级经验候选（含任务意图/踩坑/最终方案）；防归档/转正后循环重生。
- **评审修正**：任务经验候选不再被新颖官按"主题相近"误判重复归档；涉密/危险否决一律留人工。

- **数据多渠道同步备份 v3**（规格 docs/BACKUP-DESIGN.md）：
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