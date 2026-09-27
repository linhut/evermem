---
id: 20260925-1025-103
type: procedure
status: active
title: 桌面端自建记忆服务的可行路线
tags: [workbuddy, mcp, 记忆系统]
env: win32
created: 2026-09-25
---

已验证不可行：桌面端插件钩子（产品禁用）；插件 MCP（把插件登记为 xxx@local 这类不存在的 market 名时 mcpServers 不注入）；直接写 ~/.workbuddy/mcp.json 与 .mcp.json（当前会话 CODEBUDDY_MCP_CONFIG 仍只有内置六个 server，mcp-approvals.json 为空）。

可行路线：本地 CLI 加 skill。存储在 ~/.workbuddy/pmem/，笔记为 Markdown（type 分 procedure / lesson / fact，status 分 active / suspect / superseded），索引为 JSON 且可从笔记幂等重建，检索用 BM25 加中文 2/3-gram。skill 规定会话开始与关键行动前必须执行 recall，获得验证过的经验后执行 add。

命令：python mem.py recall "查询词"；python mem.py add --type lesson --title "..." --body "..."；python mem.py reindex；python mem.py stats。
