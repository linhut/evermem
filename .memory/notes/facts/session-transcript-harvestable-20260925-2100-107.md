---
id: 20260925-2100-107
type: fact
status: active
title: 会话过程数据全量落盘可直接收割无需钩子
tags: [workbuddy, 会话记录, 自动捕获, 关键]
env: win32
hot: true
created: 2026-09-25
---

WorkBuddy 把每个会话的完整执行历史写到 `~/.workbuddy/projects/<项目slug>/<sessionId>.jsonl`，不需要任何钩子或 MCP 就能离线读取。

记录结构：事件类型主要为 `function_call`（181 次）与 `function_call_result`（180 次），另有 reasoning、message、file-history-snapshot、session-meta。
- `function_call` 字段：name（工具名，如 Bash/Edit/Write/WebFetch）、arguments（入参）、callId、timestamp、cwd、sessionId。
- `function_call_result` 字段：name、callId（与调用配对）、status（completed 等）、output（含 text 输出）、timestamp、cwd。

意义：自动捕获试错过程不必依赖 PreToolUse 钩子（该产品禁用），直接收割这些 jsonl 即可。可配对调用与结果，提取命令、输出、失败与成功序列，识别"连续失败后成功"这类模式，自动生成记忆候选并落到证据层。

代价是只能事后收割，不能实时拦截；但满足"下次不再重复试错"这一核心目标。同理应检查 Claude Code（~/.claude/projects/）与 Codex 的会话落盘位置，同一套收割逻辑可复用。
