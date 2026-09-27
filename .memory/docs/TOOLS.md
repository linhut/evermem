# 恒忆平台工具与资产全清单（2026-09-27）

> 平台总览：引擎、Web、注入、数据、文档、Git。维护入口 = 本文档 + PLATFORM.md。

## 一、引擎（CLI，`.memory/`，零依赖 Python）

| 文件 | 职责 | 入口示例 |
|------|------|---------|
| **mem.py** | 核心引擎：recall / add / hot / candidates / reindex / stats / show；索引、LRU 缓存、新近度、token 预算、候选 AI 评分 | `python mem.py recall "机房 搬迁"` |
| **harvest.py** | 会话收割（WorkBuddy jsonl / DSH zstd / atomcode → 候选，无钩子） | `python harvest.py signals --days 3` |
| **ingest.py** | 文档提取（docx/xlsx 等 → F:/知识库数据/chunks/ 块库） | `python ingest.py F:/机房搬迁`（用系统 Python） |
| scan_spaces.py | F 盘知识空间扫描，产出 corpus_spaces.json | `python scan_spaces.py` |
| knowledge_scan.py | 跨会话主题/失败模式扫描 → kb.json / knowledge-base.md | `python knowledge_scan.py` |
| batch_read_docs.py | .doc 老格式批量读取（走 editor_sdk） | `python batch_read_docs.py` |
| bench_verify.py | 工具验收 + 性能基准（全链路） | `python bench_verify.py` |
| bench_search.py | 检索质量基准：20 组标准查询，`--save` 存基线 | `python bench_search.py --save` |
| check_all.py | 全功能健康检查（35 项冒烟） | `python check_all.py` |
| **evermem_mcp.py** | MCP stdio 桥：mem_read / mem_record / mem_update / mem_hot | 配置进各宿主 MCP |
| fluent_preview.py | 前端热预览（开发模式） | 配合 launcher `PMEM_DEV=1` |
| app.py | 旧 PySide6 桌面版（**已弃用**，由 Web+pywebview 替代，保留可删） | — |

## 二、Web（`.memory/web/`）

| 文件 | 职责 |
|------|------|
| server.py | 零依赖 HTTP 服务 + 18+ API（notes/search/note/hot/stats/spaces/blocks/candidates/**backup(状态/保存/执行/恢复)**/…status/unhot/mcp…），三层缓存（索引/spaces/blocks） |
| index.html + index.js | 七视图：记忆浏览 / 候选审核（AI 徽章）/ 文档导入 / 核心经验 / 统计诊断 / 接入设置 / **数据备份** |
| launcher.py | pywebview 桌面封装（跨 Win/macOS/Linux），`PMEM_DEV=1` 热预览 |

## 三、注入 & 联动

| 通道 | 落点 | 状态 |
|------|------|:---:|
| skill | `~/.workbuddy/skills/personal-memory`（4 宿主已装） | ✅ |
| 热层 | WorkBuddy 项目 MEMORY.md（20 条）/ DSH ~/.dsh/AGENTS.md（12 条） | ✅ |
| 工作纪律 | 项目 MEMORY.md「工作纪律」节（每次会话自动注入） | ✅ |
| MCP | WorkBuddy（mcp.json+.mcp.json 双写）/ Claude ~/.claude.json / DSH settings.yaml | ✅ 已配置 |
| 规则/专家 | 用户规则 always/manual @mem、Agent MD skills 预加载（机制已核实） | ⏸ 可选未启用 |

## 四、数据资产

| 数据 | 位置 | 规模 |
|------|------|------|
| 正式笔记 | notes/{procedures,lessons,facts}/ | **65 条**（50 配方 / 6 教训 / 9 事实；active 64 / suspect 1） |
| 热层 | MEMORY.md MEMORY_HOT 区块 | 20 条（17 配方 / 3 事实） |
| 候选/归档 | notes/candidates/ + archive/ | 候选 0 / 归档 8（证据保留） |
| 索引 | index.json（派生，可重建） | ~1.3MB |
| 证据 | events/（JSONL） | 会话事件日志 |
| F 盘块库 | F:/知识库数据/chunks/ | 9 空间 9500+ 块 |
| 检索基线 | docs/bench-search-baseline-*.json | 20 组查询 20/20 |

## 五、文档（`.memory/docs/` + 根）

README / USAGE / PLATFORM v2（平台总纲）/ ARCHITECTURE（早期桌面设想）/ REVIEW-2026-09（全景复盘）/ MONTHLY-TEMPLATE + MONTHLY-2026-09（月度回顾）/ bench 基线 / TOOLS（本文档）

## 六、Git

- 仓库根：`C:/Users/Administrator/Documents/个人知识库`（.memory 为子目录）
- 5 个提交，纯本地无远程；.gitignore 排除 index.json/harvest_state.json/tmp_ui/ 等派生与临时物

## 七、性能基线（修复后实测，2026-09-27）

| API | 修复前 | 修复后 | 说明 |
|-----|:---:|:---:|------|
| /api/notes（记忆浏览） | 240-410ms | **6ms** | 根因：cached_index 误用 load_index(force=True) |
| /api/note 详情 | ~300ms | **6ms** | 同上 |
| /api/search | — | 35ms | 缓存命中后查询计算 |
| /api/hot | — | 40ms | |
| 首请求（进程冷启动） | — | ~115ms | 首次 json 载入 1.3MB 索引 |

**运维铁律**：改 mem.py 后**必须重启** server（进程是启动时代码快照）；server 缓存按 index.json mtime 失效，正常编辑笔记自动重建。