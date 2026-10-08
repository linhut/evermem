# 恒忆 Evermem · 发行版本安装规范（免安装绿色版 / 安装版）

> 制定：2026-10-01 · 依据：v0.2.3 发布实测（PyInstaller onefile 冷启动受杀软拖慢、单文件解包开销）
> 适用范围：Windows / macOS / Linux 三平台两种发行形态的构建、安装、卸载、更新与验收。
>
> **实现状态（2026-10-07，v0.2.12）：6-1~6-7、6-9 已实现；6-8 保持文档化（默认不启用）；
> 6-10 依赖外部证书（见 CODE-SIGNING.md，单位 OV 为性价比选项，尚未购买）。**
> v0.2.12 修复：全新数据根（首次安装、或把「数据位置」指到空目录）无法保存第一条笔记（界面只显示
> 「内部错误」）；删除受限的环境（策略/安全软件拦截删除）里服务静默启动失败；发布自检 `check_all.py`
> 改为完全隔离并修掉三处假成功（写用例不再污染正式库、自启实例改动态空闲端口、失败返回非零退出码）。
> v0.2.12 新增：「接入设置 → ① 技能安装」新增 Marvis（腾讯马维斯）宿主，含前置条件守卫
> （环境未就绪返回 409 而非造出假目录）与写入后回读校验。
> v0.2.6 补齐：Linux deb（dpkg-deb 参数修正 + 启动器）、AppImage 构建路径修正、
> 三平台统一 `SHA256SUMS.txt`（新增 checksums 汇总 job，修复此前只剩 Windows 哈希）。
> v0.2.7 修复：checksums 汇总 job 补充 checkout（v0.2.6 因缺 git 上下文导致统一清单上传失败，
> 由 CI 手动补传），统一清单改由 CI 全自动生成上传。
> v0.2.8 修复：`harvest.py` 漏 `import os` 致自动收割静默失败；README / README.en / USER-GUIDE
> 下载产物命名与实际 Release 资产对齐（此前仍写单文件 `Evermem-windows-v*.exe`，用户按文档找不到文件）。
> v0.2.9 修复：写入侧笔记/候选统一原子写、读取侧解析容错（消除并发读半成品导致的接口 500
> 与读-改-写把笔记正文永久截短）；CI 并行 job 创建 Release 的竞态改为幂等；
> 「其他记忆导入 → 使用画像提示词」模板路径由数据根改正为代码根。

---

## 〇、更新清单决策（2026-10-01 定案，区别于初稿）

- **update-manifest.json 不进 GitHub Releases、不由 CI 生成**（用户拍板）。
- 清单 = 官网云服务器上的**固定文件**：`https://www.linhut.cn/evermem/update-manifest.json`，
  由维护者手动生成一次、长期有效。客户端更新检查默认先请求它。
- **清单内容只应写 `sources.mirrors` 等低频信息，不写死版本号**——版本判断始终由 GitHub
  Release 说了算（防止"忘更新清单 = 用户永远看到已是最新"）。
- 云清单 404 / 解析失败时自动降级到 GitHub 直连 + 镜像竞速，不阻塞检查。
- 手动更新方式：`scripts/gen_update_manifest.py merge` 生成后上传到云服务器（脚本 docstring 有用法）。

---

## 一、版本形态与差异对比

| 维度 | 免安装绿色版（便携版） | 安装版 |
|---|---|---|
| 交付物 | `Evermem-portable-<平台>-v*.zip`（onedir 目录） | Windows `Evermem-setup-v*.exe`（Inno）· macOS `.dmg` · Linux `.deb`/`.rpm` |
| 安装动作 | **零安装**：解压即用，双击 `Evermem` | 运行安装向导：选择目录 → 开始菜单/桌面快捷方式 → 完成 |
| 写注册表/系统服务 | **不写**（开机自启开关由用户主动勾选，仅写 HKCU Run） | 写开始菜单、可选自启；卸载器登记 |
| 数据位置 | **程序目录同级**（可随 U 盘/目录整体移动）；`PMEM_HOME` 可覆盖 | 用户数据目录：Win `%APPDATA%\EvermemData` · macOS `~/Library/Application Support/Evermem` · Linux `$XDG_DATA_HOME/evermem` |
| 更新方式 | 现有 `update.py` P2/P3：下载新包 → 备份 `.old` → 替换 → 重启 | 安装版升级走 **setup 升级**（更新器下载新版 setup 静默安装），不做 exe 自替换（程序目录可能只读） |
| 卸载 | **删目录即卸载**（数据在目录内；若 PMEM_HOME 外置需另保留） | 卸载程序：删程序文件 + 快捷方式；**询问是否保留数据目录** |
| 权限要求 | 无 UAC（放入可写目录）；放 Program Files 会触发数据根拦截引导 | 安装需普通用户权限（装到 `%LOCALAPPDATA%\Programs` 免 UAC；装 Program Files 需管理员） |
| 杀软/冷启动 | onedir 不重复解包、杀软扫描一次目录即可，冷启动显著快于 onefile | 同左（onedir 内嵌） |
| 适用场景 | 优盘/多机搬运、绿色办公环境、快速试用 | 正式部署、零基础用户、系统集成 |

## 二、环境依赖（三平台）

| 平台 | 依赖 | 说明 |
|---|---|---|
| Windows 10/11 x64 | 无第三方运行时 | Python 3.12 exe 依赖 `vcruntime140.dll`（Win10+ 系统自带或随常见软件已装）；若报缺 VC 运行库，引导安装微软 VC++ 2015-2022 Redistributable（免费），或在 PyInstaller 打包时确认 vc runtime 随包 |
| macOS 12+（arm64/x64） | 无 | 未公证：首次需「右键 → 打开」或 `xattr -cr`（已有图文指引） |
| Linux x86_64 | 无（AppImage 自带 Qt） | 裸 ELF 需系统 Qt 库（见 CODE-SIGNING.md）；AppImage 形态免依赖 |
| 任意平台 | 无需 Python / Qt 预装 | 程序自包含；数据零初始化（首启自动建 `notes/ events/ updates/ index.json`） |

## 三、免安装绿色版规范

### 3.1 构建形态：PyInstaller **onedir**（v0.2.5 起，已替代 onefile；v0.2.6 起增加 brand 资源）

- 理由（v0.2.3 实测）：onefile 每次启动把 ~219MB 解包到 `%TEMP%`，叠加杀软实时扫描造成
  "打不开/打开极慢"（`--smoke` 设计 6s 自退，被拖到 180s+ 未完成）；onedir 文件就地、启动即快。
- 打包命令：`pyinstaller --onedir --windowed --name Evermem --paths web --hidden-import paths
  --add-data "web;web" --add-data "templates;templates" --add-data "VERSION;."
  --add-data "scripts;scripts" desktop.py`（各平台同构，分隔符按平台）。
- 产物目录 `dist/Evermem/`（exe + `_internal/`），打包为绿色版 zip/tar.gz。
- **产物命名约定（与 update.py `_asset_matches` 一致性维护）**：
  - 绿色版：`Evermem-windows-vX-portable.zip` / `Evermem-macos-vX.app.zip` / `Evermem-linux-vX-portable.tar.gz`
  - 安装版：`Evermem-setup-vX.exe`（Inno）/ `Evermem-macos-vX.dmg` / `Evermem-linux-vX.deb`、`.rpm`
  - 可选增强：`Evermem-linux-vX.AppImage`（linuxdeploy，continue-on-error）

### 3.2 目录结构（解压后）

```
Evermem/                      ← 整体即"安装目录"，可改名/移动/拷 U 盘
├── Evermem.exe               ← 入口（macOS: Evermem.app；Linux: Evermem）
├── _internal/                ← PyInstaller onedir 资源（web/templates/scripts/VERSION/Qt 库）
├── README-绿色版.txt         ← 一句话说明 + 数据位置
├── notes/  events/  updates/ ← 首次启动自动生成（数据=程序目录同级，随包移动）
└── index.json
```

### 3.3 安装 / 卸载 / 更新流程

| 动作 | 流程 |
|---|---|
| 安装 | 解压 zip 到任意**可写目录** → 双击 `Evermem.exe`。无注册表、无服务、无自启（用户可在菜单勾选自启） |
| 卸载 | 删除整个 `Evermem/` 目录。若用户设过 `PMEM_HOME` 指向外部，卸载前提示保留该目录 |
| 更新 | 程序内「版本与更新 → 内置下载 → 更新并重启」。P3 已适配 onedir：备份整个程序目录（`Evermem.old`）→ 解压 zip 替换 → 失败自动回滚 → 重启（仅 Windows 打包版；macOS/Linux 手动替换） |
| 数据迁移 | 整目录拷贝即可；跨机器用 `docs/guides/DESKTOP-MIGRATION.md` 白名单复制 |

### 3.4 验收标准

- [ ] 解压后双击，**冷启动 ≤ 10s**（无杀软拦截环境；杀软白名单后同样达标）
- [ ] 首启自动创建 `notes/ events/ updates/ index.json`，界面「数据位置」显示程序目录
- [ ] 目录移动到其他位置/U 盘，数据与功能不变（相对路径自洽）
- [ ] 卸载=删除目录后，系统无残留（不写注册表/服务；HKCU Run 仅在用户勾选自启时存在）
- [ ] 程序目录设为只读时：启动给出明确引导（rc=5 + 弹窗"请放到可写目录或设置 PMEM_HOME"），不静默运行

## 四、安装版规范

### 4.1 Windows：Inno Setup（免费，脚本入仓，CI 构建）

- 工具：Inno Setup 6（`iscc.exe`，CI 用 choco 安装）。
- 脚本：`installers/windows/evermem.iss`（进仓库，已含卸载数据保留对话框）。
- 安装向导流程：
  1. 欢迎 → 许可协议（MIT）
  2. 安装目录：默认 `{autopf}\Evermem`（Program Files；安装需管理员，runner 默认具备）
  3. **数据位置**：安装器在程序目录写 `install.marker`（`[Code] ssPostInstall`），
     `paths.py` 检测到 marker 即按"安装版"处理——数据根默认 `%APPDATA%\EvermemData`，
     与程序目录分离（程序只读、数据可写）。注册表 `HKCU\Software\Evermem` 记录安装/数据目录（信息用途）。
  4. 快捷方式：开始菜单「恒忆 Evermem」+ 卸载项；可选桌面图标
  5. 完成 → 启动
- 卸载流程：卸载程序（`unins000.exe`）删程序文件/快捷方式；**`CurUninstallStepChanged` 弹窗询问
  是否删除 `%APPDATA%\EvermemData`**（默认保留，6-6 已实现）。
- 更新：更新器检测到 install.marker（安装版）→ 下载 **setup 静默升级**（`/VERYSILENT
  /SUPPRESSMSGBOXES /NORESTART`，6-3 已实现），不替换 exe（目录可能只读）。

### 4.2 macOS：dmg（拖拽安装）+ 可选 pkg

- 交付：`Evermem-macos-v*.dmg`（hdiutil 制作，含 `Evermem.app` + Applications 快捷方式）；
  pkg（pkgbuild，静默装到 /Applications）作为组织内分发选项。
- 数据：首启自动用 `~/Library/Application Support/Evermem`（通过 `PMEM_HOME` 注入或首启引导）。
- 卸载：拖出废纸篓（App + 数据目录询问保留）。

### 4.3 Linux：deb / rpm

- 工具：`dpkg-deb` / `rpmbuild`（免费，CI 在 ubuntu 交叉打包，`scripts/make_installers.sh`）。
- 安装：`apt install ./evermem_*.deb`（AppImage 继续作为绿色版可选交付）。
- 数据：`$XDG_DATA_HOME/evermem`（deb/rpm 安装器写入 `/opt/evermem/install.marker`，
  `paths.py` 检测后数据根落到系统数据目录）。
- 卸载：`apt remove evermem`（数据目录默认保留，符合 Linux 惯例）。
- 说明：deb/rpm 为可选增强（CI `continue-on-error`，失败不阻塞发布）；绿色版 tar.gz 是 Linux 主资产。

### 4.4 安装版验收标准

- [ ] 向导安装到默认目录全程免 UAC，完成后开始菜单出现入口，首启数据落在 `%APPDATA%\EvermemData`
- [ ] 卸载后程序/快捷方式/环境变量移除，数据目录按用户选择保留或删除
- [ ] 程序目录只读（Program Files）时功能完整（写入全部走数据目录）
- [ ] 升级：旧版内点更新 → 下载 setup 静默升级 → 数据完好
- [ ] 绿色版与安装版可并存（见 6.4 实例锁）

## 五、验收总清单（两种形态通用）

- [ ] `check_all.py` 38/38 + 单元测试全绿
- [ ] 冻结态冒烟 `--smoke` 退出码 0（数据根隔离到临时目录）
- [ ] 全新机器（无 Python/Qt/PMEM_HOME）：双击可用，数据目录自动创建（已实测验证）
- [ ] 数据根不可写：启动引导明确，不静默假成功（本轮已实现 `ensure_data_root`）
- [ ] Release 资产命名与更新清单平台键一致（onedir 形态调整时同步）

## 六、当前尚未定义 / 缺失的安装需求（按优先级）

> **状态：全部 6-1~6-10 已于 2026-10-01 落地或文档化（随 v0.2.5 发布，v0.2.6 修复 deb/AppImage/校验清单）。**
> 下表"缺口"列已变为实现说明；仅 6-8 / 6-10 保持未实现（各自原因见表格）。

### P0（不落实则安装版/绿色版规范无法落地）—— ✅ 已实现

| # | 项目 | 实现 |
|---|---|---|
| 6-1 | **onedir 绿色版构建切换** | build.yml `--onefile` → `--onedir`；绿色版 zip/tar.gz/.app.zip 命名约定；update.py `_asset_matches(name, key, form)` 平台×形态分流；`apply_update()` 绿色版分支（备份程序目录 → zip 解压替换 → 回滚 → 重启） |
| 6-2 | **安装版数据位置注入** | `paths.py` 新增 `install.marker` 检测（`is_installed()`）；安装版默认数据根 = `%APPDATA%\EvermemData`（macOS `~/Library/Application Support/Evermem`、Linux `$XDG_DATA_HOME/evermem`）；`config_search_paths` 同步 |
| 6-3 | **安装版升级路径** | `update.apply_update()` 分流：检测到 install.marker → 下载 setup 静默安装（`/VERYSILENT`）而非 exe 替换 |

### P1（安装版体验必需）—— ✅ 已实现

| # | 项目 | 实现 |
|---|---|---|
| 6-4 | Inno `.iss` 脚本与 CI 集成 | `installers/windows/evermem.iss` 进仓；CI windows job：`choco install innosetup` + `iscc` 产 `Evermem-setup-v*.exe` 随 Release |
| 6-5 | macOS dmg / Linux deb、rpm 产物 | `scripts/make_installers.sh`：hdiutil dmg、dpkg-deb deb、rpmbuild rpm；CI 接入（`continue-on-error`） |
| 6-6 | 卸载数据保留对话框 | Inno `[Code] CurUninstallStepChanged`：卸载后弹窗询问是否删 `%APPDATA%\EvermemData`（默认保留） |
| 6-7 | 多形态实例锁区分 | `desktop.py` SingleInstance 锁文件按数据根 sha1 命名：`%TEMP%\pmem-desktop-<hash>.lock`——绿色版/安装版（数据根不同）可并存；同数据根仍单实例 |

### P2（体验增强）

| # | 项目 | 状态 |
|---|---|---|
| 6-8 | 文件关联（可选） | **未实现（保持文档化）**：`.md` 关联到记忆浏览风险大（接管用户 md 打开方式），需用户拍板后再做；安装版默认不注册任何文件关联 |
| 6-9 | 安装版自动更新 UI | ✅ 已实现：更新检查结果携带 `form`（portable/installer）；安装版按钮显示「下载安装包」，确认文案区分（数据保留提示） |
| 6-10 | 签名后体验 | **未实现（外部依赖）**：SmartScreen/Gatekeeper 拦截消除需购买代码签名证书——Windows EV ¥2500+/年、OV ¥1200+/年（单位名义最划算）；macOS 公证 $99/年（免费仅 xattr 引导）；Linux AppImage 免费。决策待用户（见 CODE-SIGNING.md） |

---

*规范为设计基线；实现顺序：6-1（绿色版提速）→ 6-2/6-3（安装版数据与升级）→ 6-4~6-7（安装器落地）→ P2 增强。
2026-10-01 晚已全部落地（含 6-9）；更新清单改由云服务器固定文件分发（见〇）。*
