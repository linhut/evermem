---
hot: true
id: 20260927-0245-134
type: fact
status: suspect
title: 各 agent 会话数据的可提取性地地图
tags: [会话, 多宿主, 提取, atomcode, DSH]
env: win32
source: 恒忆侦察（~/.atomcode、~/.dsh、~/.workbuddy 等，2026-09-27 实扫）
created: 2026-09-27
---

按 CCswitch 会话位置表全面扫描后，本机各 agent 会话数据的可提取性结论。

## 谁有真实会话文本（可提炼）

- **WorkBuddy**：~/.workbuddy/projects/**/*.jsonl —— 工具调用全（callId/tool/arguments/output/status），但**用户消息多为系统注入**（system-reminder/craft_mode/task-notification），真实对话文本少
- **atomcode**：~/.atomcode/sessions/<hash>/*.jsonl —— **每行含真实 user/assistant 文本**（字段 v/started_at/ts/iso/session_id/turn_id/user/assistant），2026-09-17 前后 9 会话。jsonl 需**逐行解析**（每行一对象，无 type 字段）
- **DSH（重要修正）**：$DSH_HOME/sessions/ 两级目录 `<工作区路径URL编码>/<session-id>/session.jsonl.zstd` —— **117 个 zstd 压缩会话**（2026-08 起），含真实事件流：user/message、assistant/message、tool/call+result、session/title。**必须流式解压**（zstandard.stream_reader，frame 无内容大小头；直接 decompress 报错）。工作区分布：dsh-manager 38、gongwen-skill 31、AI-DATA 26、stock-terminal 7、中文文档目录 6、AI-PPT 3 等。**教训：找会话不能只搜 *.jsonl，要按官方文档确认压缩/格式（zstd/加密/sqlite）**

## 谁没有（数据事实，已深挖确认）

- **Claude Code**：~/.cache/claude/projects 不存在；~/.cache 全目录为空——无会话
- **Codex**：~/.codex sqlite 全深挖——state_5 的 threads/projects 表 0 行；logs_2 的 logs 表 3000 行是 **Rust 应用运行日志**（websocket/认证诊断，无对话）；goals/queue/memories 空——无会话正文
- **Gemini/OpenClaw/Hermes/OpenCode**：目录不存在；~/.local/share 仅 Kingsoft（WPS）
- **~/.workbuddy/sessions/*.json**：进程心跳（pid/sessionId/cwd/heartbeat），非对话
- **~/.gongwen-skill/sessions/*.json**：gongwen 命令调用记录（list-types 等命令+参数），非对话

## CCswitch 会话位置表（参考）

Claude Code ~/.cache/claude/projects/｜Codex sessions 目录｜OpenCode ~/.local/share/opencode/｜OpenClaw ~/.openclaw/agents/*/sessions/｜Gemini ~/.cache/gemini/tmp/*/chats/｜Hermes ~/.hermes/state.db

## 启示

- knowledge_scan.py 已支持 WorkBuddy + atomcode + DSH（zstd）三种格式
- 找 agent 会话的通用方法：①官方文档确认存储位置与格式（zstd/jsonl/sqlite）②按格式解压/解析 ③不能只按常见扩展名搜
- DSH 117 会话可全量提炼