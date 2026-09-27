---
id: 20260925-1954-106
type: procedure
status: active
title: 把 pmem 移植到另一个 agent 宿主的步骤
tags: [架构, 移植, claude-code, codex, dsh]
env: 通用
created: 2026-09-25
---

前提：记忆引擎与宿主解耦。笔记（Markdown，唯一权威）、索引（可从笔记重建）、检索（BM25）三者都不依赖宿主，原样复制即可；需要为每个宿主重写的只有触发层。

第一步，把笔记目录放到宿主无关的位置，例如 ~/.pmem/ 或知识库目录下的 .memory/，不要放在某个宿主的私有配置目录里（避免被该宿主的配置清理误删，也方便换宿主时不动数据）。

第二步，为新宿主写一份触发配置：
- Claude Code：在 .claude/ 或插件里加 hooks.json，PreToolUse 匹配 Bash/Edit 等工具名，钩子内调用 mem recall 并把结果通过 hookSpecificOutput.additionalContext 注入；必要时用 updatedInput 改写参数、用 permissionDecision:deny 阻断。同时把 mem 包成 MCP server 供主动调用。
- Codex：用 ~/.codex/config.toml 的 [mcp_servers.pmem] 注册一个 stdio server，再把调用纪律写进 .agents/skills/<name>/SKILL.md 与仓库的 AGENTS.md（AGENTS.md 在 agent 开始前生效，适合写"先 recall 再动手"）。
- DSH：用 dsh plugin add 安装插件，注册 memoir 类工具；回合结束的 turn-stopping 事件用于自动归纳候选。
- WorkBuddy：只能用 ~/.workbuddy/skills/<name>/SKILL.md 规定纪律，靠模型主动执行 CLI。

第三步，把 CLI 与 skill 里的绝对路径改成新位置，跑一次 reindex 与 recall 验证。

注意：检索与笔记格式保持一致，跨宿主才能共用同一份记忆；不要为每个宿主复制一份笔记，那样必然分裂。
