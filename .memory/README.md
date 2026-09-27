# .memory — 个人跨会话经验记忆

把 AI 会话中的试错过程沉淀成本地知识，下次直接复用，不再从零试起。

**核心主张**：不依赖任何 AI 宿主提供的钩子或 MCP 通道。笔记是本地 Markdown（唯一权威），索引可随时重建，自动捕获靠收割会话落盘记录实现。

版权所有 (c) 2026 Jose-AI · <https://www.linhut.cn> · 许可协议 MIT（见 LICENSE）。

## 数据目录与跨平台

数据目录由环境变量 `PMEM_HOME` 决定，未设置则用脚本所在目录：

```bash
export PMEM_HOME="<你的数据目录>"    # Windows: set PMEM_HOME=...
```

Python 用当前环境的解释器（`sys.executable`），**代码里不存在写死的绝对路径**。所有路径走 pathlib，读写显式 utf-8，因此 Windows / macOS / Linux 通用。

打包分发时需注意：PyInstaller 不能交叉编译，三个平台要各构建一次（架构设计见 `docs/ARCHITECTURE.md`）。

## 为什么不用现成方案

调研过的同类项目（见 `notes/facts/similar-oss-memory-projects`）：ReMe、Vault-Agent-Memory、agentmemory、PRAANA 都比本工具成熟，但**它们在钩子被禁用的宿主里都无法自动捕获**（ReMe 自述 Codex 场景如此）。本工具的 `harvest.py` 直接读会话落盘 jsonl，无需钩子即可自动捕获，是目前的差异点。

## 目录

```
.memory/
├── mem.py               检索、笔记管理、热层同步
├── harvest.py           会话收割（无需钩子的自动捕获）
├── notes/               笔记，唯一权威，进 Git
│   ├── facts/           稳定事实
│   ├── lessons/         经验教训
│   ├── procedures/      可执行配方
│   └── candidates/      自动收割的候选，status=staged，待验证
├── events/              证据层，JSONL，只追加
├── tests/               回归测试
├── README.md
├── index.json           索引，可重建，不进 Git
└── harvest_state.json   收割进度，不进 Git
```

## 三条命令流水线

| 想做什么  | 命令                                                             |
| ----- | -------------------------------------------------------------- |
| 查记忆   | `mem.py recall "查询词"`                                          |
| 存记忆   | 直接写 Markdown 到 `notes/<type>s/`，然后 `mem.py reindex`            |
| 自动挖候选 | `harvest.py scan --days 7 --dry-run`，确认后去掉 `--dry-run`         |
| 同步热层  | `mem.py hot --apply --target <项目>/.workbuddy/memory/MEMORY.md` |
| 自检    | `tests/test_recall.py`                                         |

`PY` 为当前环境的 Python（Windows 示例：`C:/Python314/python.exe`；macOS/Linux：`python3`）。  
命令均可加 `--help` 查看参数。

## 三层结构：按"被使用的确定性"分层

| 层  | 内容                      | 生效方式                        |
| -- | ----------------------- | --------------------------- |
| 热层 | 人工标 `hot: true` 的 ≤20 条 | 同步进宿主必读文件，会话开始即常驻，**不依赖检索** |
| 温层 | 全部笔记                    | `recall` 检索，靠技能提醒触发         |
| 冷层 | `events/*.jsonl` 证据     | 只追加，用于溯源与证伪                 |

这样分层是因为：**整条链最弱的一环是"用"**。存储与采集再好，模型不主动检索就归零；热层把最值钱的经验绕过检索直接送到上下文里。

## 日常怎么用

1. **开工前**：用任务关键词跑一次 `recall`。
2. **执行易错命令前**：`recall` 该工具名。
3. **连续失败两次以上**：`recall` 错误信息原文片段。
4. **收尾**：产生了**已验证**的结论，写进笔记并 `reindex`。
5. **每周一次**：跑 `harvest.py scan --dry-run`，有价值的候选转 active（改 `status` 并移出 `candidates/`）。

## 笔记格式

```
---
id: YYYYMMDD-HHMM-NNN
type: procedure | lesson | fact
status: active | suspect | superseded
title: 一句话标题
tags: [标签]
env: win32
hot: true          # 可选，标记进热层
created: 2026-09-26
---

正文：问题、无效做法及原因、已验证的正确做法、适用范围与例外、来源。
```

## 纪律

- 只写已验证的内容；未验证的标 `staged` 或 `suspect`。
- 命令类记忆必须写清系统、shell、工具版本。
- 禁止写入密钥、令牌、内网地址、个人隐私。
- 结论被推翻时新建一条并把旧的标 `superseded`，不删历史。
- 检索无命中就明说无命中，不凭印象编造。
- **热层宁少勿多**，超过二十条就挤占上下文、反而被忽略。

## 已知限制

- 笔记少于 20 条时常见词区分度不足，可能有噪声命中。
- 检索基于词面匹配加中文 2/3-gram，不理解同义词。
- 收割器的失败判定仍会漏掉真信号（见 `notes/lessons/harvest-tuning-pitfalls`）。
- 宿主记忆文件是会话启动时快照，同步热层后要等下一个新会话才生效。

## 版本控制与涉密声明

- 本仓库 **默认纯本地**，未配置远程；如需异地备份可加**私有**远程，但**涉密内容绝不 push**（公共平台一律不传）。
- 笔记进 Git 前自查：正文只留方法论，敏感细节（密钥、内网 IP、身份证号、手机号、涉密文件名全称）一律用 XXX 占位。
- 涉及国家秘密、警务、未公开政府项目的信息**一律不写入笔记**，只保留公开口径的方法论。
- `index.json`、`harvest_state.json`、`tmp_ui/`、日志等派生与临时文件已被 `.gitignore` 排除，不进版本库；笔记与脚本始终跟踪。

## 数据备份与同步（数据与代码分离）

- **双轨制**：代码（本仓库）→ GitHub 私人仓库；**数据与知识 → 云端备份，绝不进 Git**（notes/events/索引已被 .gitignore 排除）。
- 备份命令：`python backup.py status`（查看）/ `--dry-run`（预览）/ 直接执行（增量同步）/ `--restore`（恢复）。
- 目标配置（自定义云端位置）：编辑 `pmem_backup.json` 写入 `{"target": "<本机可写云端目录>"}`，或设环境变量 `PMEM_BACKUP_TARGET`。
- 云端位置示例：坚果云 / OneDrive / 网盘同步夹、NAS / WebDAV 的本地挂载路径（先挂载后填写）。
- 增量机制：按文件 mtime+size 跳过未变文件，重复执行低成本；本地清单 `.pmem-backup-last.json` 记录上次状态（不随仓库上传）。

## 当前状态

- 笔记 20 条（active 13 / staged 7），证据 251 条。
- 已完成：CLI 检索、自动收割、热层同步、回归测试。
- 待清理：探索期遗留的探针插件与无效 MCP 配置（见下节）。
- 路线：自动索引 → 双向链 → SQLite/FTS5 → 工具化（配置化 + 安装脚本 + 宿主适配器）。

## 探索期遗留（可安全删除）

以下都是验证"钩子与 MCP 是否可用"时留下的产物，结论已入库，文件本身无用：

- `~/.workbuddy/plugins/local/memory-probe/`（探针插件）
- `~/.workbuddy/mcp.json` 与 `~/.workbuddy/.mcp.json`（宿主不读）
- `installed_plugins.json` 中的 `memory-probe@local` 条目
- `settings.json` 的 `enabledPlugins` 中的同名条目

删除前建议确认；两个 json 都有 `.bak-<时间戳>` 备份可回滚。
