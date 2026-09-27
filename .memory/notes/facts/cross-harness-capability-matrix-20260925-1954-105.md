---
id: 20260925-1954-105
type: fact
status: active
title: 跨宿主记忆系统能力矩阵
tags: [架构, claude-code, codex, dsh, workbuddy, 选型]
env: 通用
created: 2026-09-25
---

同一套记忆引擎在不同 agent 宿主上的可行性不同，差异全在"触发层"：引擎（Markdown 笔记 + 索引 + CLI + 生命周期）可原样移植，能否在行动前强制回忆则取决于宿主的钩子能力。

Claude Code：Hooks 是一等能力（官方文档明确"run custom code at key points in the agent lifecycle"），MCP 原生支持，Skills/commands/memory 从 .claude/ 与 ~/ 自动加载，另有插件与 marketplace 机制。结论：门控三级（注入上下文 / 改写参数 / 硬阻断）全部可实现，是最理想的宿主。

OpenAI Codex：MCP 支持（~/.codex/config.toml 的 [mcp_servers.] 表，CLI 用 codex mcp，TUI 用 /mcp）；Skills 为仓库本地的 .agents/skills/，结构是 SKILL.md 加 scripts/、references/、assets/；AGENTS.md 提供仓库级指令且在 agent 开始工作前生效。**未见生命周期钩子能力**（仅有 shell 命令的 approval-policy）。结论：可靠 MCP 加 skill 实现提示级门控，无法自动拦截。

DeepSeek Harness（DSH）：dsh-memoir 证明其插件机制成熟，确认存在 agent/turn-stopping 事件用于自动蒸馏，另有 slot 机制注册原生 GUI、memoir_record/update/read 工具、BM25 召回与 Hot Memory。结论：写入侧最强（回合结束自动提醒归纳），读取侧靠工具调用与 Hot Memory 注入；是否存在 PreToolUse 级门控待核实。

WorkBuddy：插件钩子被产品禁用（硬编码 DISABLE_EXTENDED_PLUGIN_HOOKS=1），自定义 MCP 不注入，仅用户级 skill 可用且热加载。结论：只能走本地 CLI 加 skill 的提示级方案。
