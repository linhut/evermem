---
id: 20260926-1010-109
type: fact
status: active
title: 同类开源记忆项目调研与差异点
tags: [调研, 选型, github, reme, vault]
env: 通用
created: 2026-09-26
---

GitHub 上与本项目最接近的四个项目：

ReMe（agentscope-ai）：理念"Memory as File, File as Memory"，本地优先，无外部数据库。BM25 加 wikilink 扩展，行级 chunk；可选 embedding 经 RRF 融合。目录为 .reme/ 下的 session（对话源 jsonl）、resource、daily、digest（personal/procedure/wiki）、metadata。流程 capture→index→consolidate→recall。核心检索与文件读写不需要 LLM；auto_memory/auto_dream 需要 LLM key。宿主集成：Claude Code 用 HTTP MCP 加 Stop hook，DSH/Hermes/OpenClaw 用插件，QwenPaw 进程内嵌入。**Codex 这类只能挂 Skill 的宿主，自动捕获不可用**。

Vault-Agent-Memory：raw/ Markdown → 编译进本地 SQLite → CLI/MCP 检索。分层 L0 身份、L1 核心事实、L2 近期上下文、L3 深层知识，另设 Task Ledger 存运行时状态。frontmatter 有 trust（0–1）、expires_at、valid_from/until、supersedes_id、status。值得借鉴的是 trust 字段与"临时状态不进长期记忆"的边界。

agentmemory：功能最全但强依赖宿主钩子。PostToolUse 捕获→SHA-256 去重→隐私过滤→LLM 压缩→BM25 加向量→SessionStart 注入，含 Ebbinghaus 衰减与知识图谱。中文需另装 jieba，否则退化为整串分词。

PRAANA：终端编码 agent（非可嵌入组件），退出时提取 learnings 写入本地 SQLite，下次启动 /digest 浮现。

**差异点结论**：上述项目在钩子被禁用的宿主里都无法自动捕获（ReMe 自述 Codex 场景如此）。本项目的 harvest.py 直接读会话落盘 jsonl 配对 function_call 与 function_call_result，无需钩子即可自动捕获，这是真正的差异。可借鉴 ReMe 的 wikilink 与目录结构、Vault 的 trust 与分层。
