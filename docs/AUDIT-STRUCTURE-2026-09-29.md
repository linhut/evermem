---
title: 目录结构审计与优化建议
date: 2026-09-29
status: 建议稿（仅供评审，未执行）
---

# 目录结构审计评分与优化建议（2026-09-29）

> 依据仓库根（项目根）当前跟踪清单审计。**本方案仅供评审，默认不执行任何调整**；
> 每项建议均标注影响范围与风险规避；改动均需单独确认后再落地。

## 一、现状结构

```
仓库根（= 项目根）
├── 元/文档：README.md(中文默认) · README.en.md · USAGE.md · CHANGELOG.md · LICENSE · VERSION · .gitignore · requirements-build.txt
├── 引擎与入口（根，共 7 个 .py）：mem.py · memimport.py · harvest.py · backup.py · s3client.py · evermem_mcp.py · app.py
├── web/        （6）server.py · launcher.py · index.html · index.js · i18n.js · channel.js
├── scripts/    （9）bench_search · bench_verify · check_all · frontend_smoke · batch_read_docs · scan_spaces · knowledge_scan · ingest · fluent_preview
├── docs/       （24，含 ui/ 截图 8、过程/时效文档 5、平台文档 11、基准数据 1）
├── templates/  （2）personal-memory.SKILL.md · usage-profile.prompt.md
├── tests/      （1）test_recall.py
└── .github/workflows/ build.yml
```

## 二、评分（0~10）

| 维度 | 得分 | 说明 |
| --- | --- | --- |
| 组织合理性 | 8.5 | 引擎/入口在根、工具归 `scripts/`、前端在 `web/`、文档在 `docs/`，边界清晰 |
| 命名规范 | 8.0 | 大体清晰；少数"导入类"入口名相近易混（`memimport` / `ingest` / `harvest`） |
| 层级划分 | 8.5 | 无多余深层嵌套；`scripts/`、`docs/` 一层放全，结构扁平 |
| 冗余 / 重复 | 7.5 | `docs/` 混入过程性/时效性文件；`bench_*` 与 `check_all` 职责略有重叠 |
| **合计** | **8.1** | 已属良好；剩余为"可选优化"，不属缺陷 |

## 三、审计发现明细

### A. 合理且建议保留
- **引擎/入口平铺于根**：`mem.py` 等被 `web/server.py`、`evermem_mcp.py`、`app.py` 直接 `import mem`，
  亦有 `web/server.py` 子进程按 `BASE/…` 调引擎。**搬到 `src/` 包化会破坏全部 import 与 CI，属高风险反模式，不建议。**
- **scripts/ 收纳开发/验证工具**：与核心模块清晰隔离，已达标。
- **web/ / templates/ / tests/ / .github/**：均为单一职责，无需拆分。

### B. 可优化项（可选，均低风险）
| 条目 | 问题 | 建议 | 影响范围 | 风险规避 |
| --- | --- | --- | --- | --- |
| `docs/` 混入过程/时效文档 | `AUDIT-2026-09`·`REVIEW-2026-09`·`MONTHLY-2026-09`·`MONTHLY-TEMPLATE`·`backup-sync-oss-research` 属"过程/笔记"，与 ARCHITECTURE/PLATFORM 等常驻文档混放 | 可新建 `docs/process/` 收纳时效性文档（纯移动，不加工） | 仅文档路径；涉及 README「文档」目录、其他 docs 相对链接 | 移动前 grep 全仓库引用并同步；无代码 import，回归零影响 |
| `docs/bench-search-baseline-*.json` | 基准数据放在 `docs/` | 就地保留亦可；或移入与 `scripts/bench_search.py` 相邻 | `bench_search --save` 的默认写入位置 | 先核对脚本写盘路径再动 |
| `scripts/` 内 9 个工具平铺 | 可再分 `bench/ check/ scan/` | 低收益、且需同步 `check_all.py` 内子进程路径 | `scripts/check_all.py` 三处子进程引用 | 需改 `check_all`；暂缓，收益小 |
| 三个"导入类"入口名相近 | `ingest`(文档切块) / `memimport`(外部记忆进笔记) / `harvest`(会话收割) 语义已不同但名近 | **不改名**，DELETE 说明；在 `docs/TOOLS.md` 已明确各自输入输出 | — | 改名会动 `server.py`、`check_all` 子进程路径，收益低风险存，不建议 |
| 空/小测试 | `tests/` 仅 1 个单测 | 后续补充；本轮不动 | — | — |

### C. 不建议改动项（明确否决）
- 引擎包化到 `src/`、根文件重命名、跨文件批量移动——均会增加回归面且无实际收益。

## 四、结论与建议执行顺序
1. **优先（可选，纯文档整理）**：`docs/process/` 收编时效/过程文档；更新引用——低风险，可随时做。
2. **暂缓**：`scripts/` 再分桶、基准数据文件移动——需额外同步内部路径，收益有限。
3. **不做**：重命名导入类入口、引擎 `src/` 化。

> 说明：本报告为"优化建议方案"，以上均不破坏现有功能；请确认要落地哪几项后，我再逐项执行并回归验证（`scripts/check_all.py` 36 项 + 服务冒烟）。