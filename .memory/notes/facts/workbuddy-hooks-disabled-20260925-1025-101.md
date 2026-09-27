---
id: 20260925-1025-101
type: fact
status: active
title: WorkBuddy 桌面端禁用第三方插件钩子
tags: [workbuddy, hooks, 插件]
env: win32
hot: true
created: 2026-09-25
---

宿主 app.asar 在启动子进程时硬编码注入 `CODEBUDDY_DISABLE_EXTENDED_PLUGIN_HOOKS: "1"`，且 conversation-hook 策略 `allowedTrust` 仅为 `["trusted"]`。

因此第三方插件的 `hooks.json`（PreToolUse / SessionStart / SubagentStop 等）在 WorkBuddy 桌面端不会执行。这是产品的信任模型，不是配置错误。

代码里钩子能力完整存在：stdin 字段为 hook_event_name、session_id、transcript_path、cwd、tool_name、tool_input；stdout 支持 continue:false 阻断、hookSpecificOutput.permissionDecision:deny 拒绝、updatedInput 改写入参、additionalContext 注入上下文。

绕行选项：改 app.asar 把 1 改成 0（破坏完整性、升级被覆盖，不推荐）；用 codebuddy CLI headless 跑；接受降级改用本地 CLI 加 skill。
