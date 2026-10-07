# 仓库同步与发布规范（恒忆 Evermem）

> 目标：让他人 `git clone` 之后能直接读代码、跑测试、打包；仓库里没有个人数据、没有密钥、没有构建垃圾。
> 一句口诀：**能重建的不进仓，含个人数据的不进仓，只留「代码 + 平台文档 + CI + 构建清单 + 测试源码」。**

## 一、必须纳入版本控制

- 源码：`*.py`、`web/*.js`、`web/index.html`
- 文档：`README.md`、`README.en.md`、`USAGE.md`、`CHANGELOG.md`、`docs/**`
- 平台文件：`VERSION`、`.gitignore`、`requirements-build.txt`、`LICENSE`
- CI：`.github/workflows/**`
- 测试源码：`tests/**`
- 模板（不含真实值）：`templates/**`

## 二、绝不推送（已在 `.gitignore`，提交前仍需复核）

| 类别 | 内容 |
| --- | --- |
| 个人知识数据 | `notes/`、`events/`、`index.json`、`corpus_spaces.json`、`kb.json`、`knowledge-base.md` |
| 本机配置 | `pmem_config.json`（含机器绝对路径） |
| 凭证与备份配置 | `pmem_backup.json`（混淆后的 AK/SK、SMTP、归档密码）、`.pmem-*` |
| 日志与状态 | `*.log`、`.lock`、`.pmem-backup-last.json`、`harvest_state.json` |
| 构建产物 | `build/`、`dist/`、`*.spec`、`.venv/`、`venv/` |
| 备份产物 | `tools/`、`*.tar.aes`、`*.tar.aes.sha256`、`evermem-*.zip` |
| 临时文件 | `tmp_chk/`、`tmp_ui/`、`nul`、临时诊断脚本与截图 |

数据迁移不走 Git，走白名单复制或备份渠道，见 `docs/DESKTOP-MIGRATION.md`。

## 三、临时文件纪律

1. 开发过程中产生的诊断脚本、截图、夹具一律放 `tmp_chk/`（已 git 忽略）。
2. 用后即删；需要交付给用户的产物放仓库内正式位置或单独交付。
3. 收尾检查：`git status` 只出现预期变更；`git ls-files` 不含临时目录。

## 四、docs 同步范围清单

**原则：不逐份罗列，按规则判定。** 一条文档是否进仓，只看下面五条规则；新文档产生时按同一规则自判。

| 规则 | 判定依据 | 结论 |
| --- | --- | --- |
| **R1 引用性** | 被 `README.md`/`README.en.md`/`CHANGELOG.md`/代码链接引用 | 必留（删了会断链；断链比冗余更糟） |
| **R2 长期有效** | 规范、架构、流程、面向用户或协作者的说明、可复用模板 | 必留 |
| **R3 一次性快照** | 带日期的审计 / 复盘 / 月报 / 调研记录 | 不进仓（移入 `docs/archive/`，且只留最近一份） |
| **R4 可再生成** | 基准数据、构建产物、日志、缓存（跑个命令就有） | 不进仓（写进 `.gitignore`） |
| **R5 形态一致性** | 描述已废弃入口 / 旧命名 / 旧视图数 | 必改；改不动就删，**不留过时文档误导读者** |

### 4.1 必留（核心文档，14 份）

| 文档 | 命中规则 |
| --- | --- |
| `ARCHITECTURE.md` | R1 R2（架构总纲） |
| `BACKUP-DESIGN.md` | R1 R2（备份设计，README 引用） |
| `BACKUP-UX.md` | R2（备份 UX 设计依据；需补「已实施」状态标注） |
| `DESKTOP-MIGRATION.md` | R1 R2（用户迁移，README 引用） |
| `DISTILL-RULES.md` | R2（记忆提取规范，核心规则） |
| `MULTI-MACHINE.md` | R1 R2（README 引用） |
| `PLATFORM.md` | R2（平台总纲，月报模板的依据） |
| `PROFILE-EXPORT.md` | R1 R2（README 引用） |
| `RECIPES.md` | R1 R2（配方治理规范） |
| `REPO-RELEASE-CHECKLIST.md` | R1 R2（本文件） |
| `RETENTION.md` | R1 R2（README 引用） |
| `STATUS-FLOW.md` | R1 R2（README 引用） |
| `TOOLS.md` | R2（工具清单，协作者入口） |
| `USER-GUIDE.md` | R1 R2（零基础用户说明，README 引用） |
| `ui/*.png`（8 张界面图） | R1（README 界面预览直接引用；若后续改用图床则整体移出） |

### 4.2 不进仓（已在或应加入 `.gitignore`）

| 文档 | 命中规则 |
| --- | --- |
| `AUDIT-2026-09.md`、`AUDIT-STRUCTURE-2026-09-29.md` | R3（一次性审计快照） |
| `REVIEW-2026-09.md` | R3（一次性复盘） |
| `MONTHLY-2026-09.md` | R3（月度快照；模板另算） |
| `backup-sync-oss-research-20260928.md` | R3（一次性选型调研） |
| `bench-search-baseline-20260927.json` | R4（基准数据，可重跑生成） |
| `docs/archive/`（归档区） | R3 的落点，整目录忽略 |

`MONTHLY-TEMPLATE.md` 属 R2（可复用模板），保留。

### 4.3 落地（`.gitignore` 规则化，避免靠记忆）

```gitignore
# ===== 文档：一次性快照与可再生成产物不进仓（见 docs/REPO-RELEASE-CHECKLIST.md 第四节） =====
docs/archive/
docs/bench-*.json
docs/AUDIT-*.md
docs/REVIEW-*.md
docs/MONTHLY-20*.md
docs/*-research-*.md
```

已跟踪的文件需先移出索引再归档（**执行前确认，勿直接删**）：

```bash
git rm --cached docs/AUDIT-2026-09.md docs/AUDIT-STRUCTURE-2026-09-29.md \
                docs/REVIEW-2026-09.md docs/MONTHLY-2026-09.md \
                docs/backup-sync-oss-research-20260928.md docs/bench-search-baseline-20260927.json
mkdir -p docs/archive && git mv <上述文件> docs/archive/   # 或移到<工作区> notes/
```

### 4.4 新增文档时的自判顺序

1. 会不会被 README 引用？→ 是则必留。
2. 半年后还成立吗？→ 否（带日期/一次性）则不进仓。
3. 能不能一条命令重新生成？→ 能则不进仓。
4. 描述的是不是当前形态？→ 不是则先改，改不了就删。

## 五、提交规范

- 分支：`feat/<主题>`、`fix/<主题>`、`docs/<主题>`。
- **提交说明必须中英双语**标题：`type(scope): English summary — 中文摘要`。
  例：`feat(desktop): add launch-at-login toggle — 桌面设置页新增开机自启动开关`
- body 分中英文各一段，说明动机、影响范围与验证方式。
- 一次提交一件事；重构与功能分开提，便于回滚与评审。

## 六、提交前检查清单

- [ ] `git status` 干净，只含预期变更
- [ ] `git ls-files` 复核：无个人数据、无凭证、无构建产物、无临时目录
- [ ] `git grep` 本机路径（`C:/Users/<你>`、盘符根目录）零命中
- [ ] 提交说明中英双语
- [ ] 新增接口：先直接请求验证（对的方法 + 错的方法），再接前端
- [ ] 前端改动：真实渲染与点击验证，断言数据侧而非只看提示
- [ ] 会改数据的验证：单条样本跑完立即回滚

## 七、测试与冒烟

```bash
python scripts/check_all.py          # 38 项整体自检（含 Web API、前端契约、Python 语法）
python scripts/frontend_smoke.py     # 前端元素/路由/事件委托契约
python -m unittest discover -s tests # 全部单元测试（18 项）
```

> 注意：`tests/` 没有 `__init__.py`，discover **不要加 `-t .`**（会报 Start directory is not importable）。
> 单个模块也可用 `python -m unittest tests.test_update_check`。

## 八、打包与发布

打包链路：`.github/workflows/build.yml`，push tag `v*` 触发，Windows / macOS / Linux 三平台矩阵。

**发布前：**

- [ ] 更新 `CHANGELOG.md` 与 `VERSION`
- [ ] 三平台本地或 CI 构建通过
- [ ] GUI 冒烟 `--smoke` 退出码 0（真实校验页面加载，不是「服务就绪即通过」）
- [ ] 冻结态数据根目录验证：设置 `PMEM_HOME` 后核心检索、界面配置、导入、备份恢复指向同一目录
- [ ] 开机自启开关：开启 → 重启验证 → 关闭 → 验证系统项已移除
- [ ] 文档与界面文案同步（含英文）

**发布动作：**

```bash
git tag -a v0.2.3 -m "release: v0.2.3 — 中文摘要"
git push origin main --tags
```

Release 由 CI 自动创建并上传三平台产物（若 tag 对应的 Release 已存在则复用，不存在则自动创建）。产物分「绿色版（解压即用）」与「安装版」两类：

| 平台 | 绿色版 | 安装版 |
| --- | --- | --- |
| Windows | `Evermem-windows-v*-portable.zip` | `Evermem-setup-v*.exe`（Inno Setup） |
| macOS | `Evermem-macos-v*.app.zip` | `Evermem-macos-v*.dmg` |
| Linux | `Evermem-linux-v*-portable.tar.gz` | `Evermem-linux-v*.deb` |

另附 `SHA256SUMS.txt`（全平台统一校验清单）。发布后核对 README / `docs/USER-GUIDE.md` 的下载表是否与上述命名一致——历史上曾出现文档仍写单文件 `Evermem-windows-v*.exe` 而实际已改为 portable.zip + setup.exe 的脱节。

## 九、已知待清理项（下个版本处理）

| 项 | 说明 |
| --- | --- |
| 本机打包受限 | WorkBuddy 沙箱的批量删除保护会中断 pip 安装（site-packages 覆盖写触发 safe-delete guard），本机装不了 PySide6+PyInstaller。**打包走 GitHub Actions**：提交 tag 即触发三平台构建 |
| 无代码签名与公证 | Windows 无 EV/OV 代码签名，macOS 未公证（首次需系统设置或 `xattr` 放行），Linux 有 `.deb` 但无 AppImage。后续若面向完全零基础用户规模化分发，需考虑商业签名 |
| ~~`app.py` 与 `web/launcher.py`~~ | **2026-10-01 已清理**：确认无外部引用后移入 `_trash/` 并从索引移除 |
| 核心经验同步目标 | 当前固定写宿主项目 `.workbuddy/memory/MEMORY.md`，未做成可配置项 |
| 块库备份范围 | `backup.py` 的 `SCOPE_GROUPS` 未覆盖块库，需单独处理或扩充 scope |

**已在本轮处理并移除的项：**

- ~~产物名与产品名不一致~~ → 已统一为 `Evermem-<平台>-v*`
- ~~程序内无版本显示~~ → UI「系统 → 版本与更新」已显示当前版本并跳转到 Releases
- ~~`VERSION` 未注入构建~~ → Windows 打包已注入版本信息；运行时 `/api/version` 读取 VERSION 文件 |
