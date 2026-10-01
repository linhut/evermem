# 恒忆 Evermem · 发行版本安装规范（免安装绿色版 / 安装版）

> 制定：2026-10-01 · 依据：v0.2.3 发布实测（PyInstaller onefile 冷启动受杀软拖慢、单文件解包开销）
> 适用范围：Windows / macOS / Linux 三平台两种发行形态的构建、安装、卸载、更新与验收。

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

### 3.1 构建形态：PyInstaller **onedir**（替换当前 onefile）

- 理由（v0.2.3 实测）：onefile 每次启动把 ~219MB 解包到 `%TEMP%`，叠加杀软实时扫描造成
  "打不开/打开极慢"（`--smoke` 设计 6s 自退，被拖到 180s+ 未完成）；onedir 文件就地、启动即快。
- 打包命令：`pyinstaller --onedir --windowed --name Evermem --paths web --hidden-import paths
  --add-data "web;web" --add-data "templates;templates" --add-data "VERSION;."
  --add-data "scripts;scripts" desktop.py`（各平台同构，分隔符按平台）。
- 产物目录 `dist/Evermem/`（exe + `_internal/`），压缩为 `Evermem-portable-<平台>-v*.zip`。

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
| 更新 | 程序内「版本与更新 → 内置下载 → 更新并重启」（P3 已实现：备份 `.old.exe` → 替换 → 回滚） |
| 数据迁移 | 整目录拷贝即可；跨机器用 `docs/DESKTOP-MIGRATION.md` 白名单复制 |

### 3.4 验收标准

- [ ] 解压后双击，**冷启动 ≤ 10s**（无杀软拦截环境；杀软白名单后同样达标）
- [ ] 首启自动创建 `notes/ events/ updates/ index.json`，界面「数据位置」显示程序目录
- [ ] 目录移动到其他位置/U 盘，数据与功能不变（相对路径自洽）
- [ ] 卸载=删除目录后，系统无残留（不写注册表/服务；HKCU Run 仅在用户勾选自启时存在）
- [ ] 程序目录设为只读时：启动给出明确引导（rc=5 + 弹窗"请放到可写目录或设置 PMEM_HOME"），不静默运行

## 四、安装版规范

### 4.1 Windows：Inno Setup（免费，脚本入仓，CI 构建）

- 工具：Inno Setup 6（`iscc.exe`，CI 用 choco 或便携版安装）。
- 脚本：`installer/evermem.iss`（进仓库）。
- 安装向导流程：
  1. 欢迎 → 许可协议（MIT）
  2. 安装目录：默认 `%LOCALAPPDATA%\Programs\Evermem`（免 UAC）；允许改 Program Files（需管理员）
  3. **数据位置**：安装器写用户环境变量 `PMEM_HOME=%APPDATA%\EvermemData`（`[Registry] HKCU\Environment`
     或 `setx`），并预建该目录——保证"程序只读、数据可写"的系统集成规范
  4. 快捷方式：开始菜单「恒忆 Evermem」+ 卸载项；可选桌面图标
  5. 完成 → 启动
- 卸载流程：卸载程序（`unins000.exe`）删程序文件/快捷方式/环境变量项；**弹窗询问是否保留
  `%APPDATA%\EvermemData`**（默认保留）。
- 更新：更新器检测到新版后**下载 setup 静默升级**（`/VERYSILENT`），不替换 exe（目录可能只读）。

### 4.2 macOS：dmg（拖拽安装）+ 可选 pkg

- 交付：`Evermem-macos-v*.dmg`（hdiutil 制作，含 `Evermem.app` + Applications 快捷方式）；
  pkg（pkgbuild，静默装到 /Applications）作为组织内分发选项。
- 数据：首启自动用 `~/Library/Application Support/Evermem`（通过 `PMEM_HOME` 注入或首启引导）。
- 卸载：拖出废纸篓（App + 数据目录询问保留）。

### 4.3 Linux：deb / rpm

- 工具：`dpkg-deb` / `rpmbuild`（免费，CI 在 ubuntu 交叉打包）。
- 安装：`apt install ./evermem_*.deb`（AppImage 继续作为绿色版交付）。
- 数据：`$XDG_DATA_HOME/evermem`；桌面入口 `.desktop`（安装包内建）。
- 卸载：`apt remove evermem`（数据目录默认保留，符合 Linux 惯例）。

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

### P0（不落实则安装版/绿色版规范无法落地）

| # | 缺口 | 说明与建议实现 |
|---|---|---|
| 6-1 | **onedir 绿色版构建未切换** | build.yml 从 `--onefile` 改 `--onedir` + zip 打包；更新清单平台键/下载链随产物名更新；P3 替换逻辑对 onedir 兼容（替换整个目录或 exe+_internal 校验） |
| 6-2 | **安装版数据位置注入未定义** | Inno 写 `PMEM_HOME=%APPDATA%\EvermemData`；macOS/Linux 首启引导或安装器注入；需在 `paths.py` 增加"安装版默认数据目录"优先级（安装标记 → APPDATA） |
| 6-3 | **安装版升级路径未实现** | 更新器"安装版检测"：发现 install 标记 → 下载 setup 静默升级而非 exe 替换；`update.apply_update` 需分流 |

### P1（安装版体验必需）

| # | 缺口 | 说明 |
|---|---|---|
| 6-4 | Inno `.iss` 脚本与 CI 集成 | 脚本进仓；CI windows job 产 `Evermem-setup-v*.exe` 并随 Release |
| 6-5 | macOS dmg / Linux deb、rpm 产物 | hdiutil / dpkg-deb / rpmbuild 步骤进 CI |
| 6-6 | 卸载数据保留对话框 | Inno 自定义卸载页询问是否删 `%APPDATA%\EvermemData` |
| 6-7 | 多形态实例锁区分 | 现单实例锁 `%TEMP%\pmem-desktop.lock` 与形态无关——绿色版/安装版并存时需按数据根区分锁文件，或文档声明"同数据根仅允许一个实例" |

### P2（体验增强）

| # | 缺口 | 说明 |
|---|---|---|
| 6-8 | 文件关联（可选） | `.md` 关联到记忆浏览（谨慎：避免接管用户 md 打开方式） |
| 6-9 | 安装版自动更新 UI | 更新检查识别安装版 → 显示"下载安装包"而非"更新并重启" |
| 6-10 | 签名后体验 | 获得签名后 SmartScreen/Gatekeeper 拦截消失（见 CODE-SIGNING.md） |

---

*规范为设计基线；实现顺序建议：6-1（绿色版提速）→ 6-2/6-3（安装版数据与升级）→ 6-4~6-7（安装器落地）→ P2 增强。*
