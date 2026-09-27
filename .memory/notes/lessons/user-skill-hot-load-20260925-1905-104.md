---
id: 20260925-1905-104
type: lesson
status: active
title: 用户级技能无需重启即可加载，MCP 与钩子必须重启
tags: [workbuddy, skill, mcp, 排查]
env: win32
created: 2026-09-25
---

把 `SKILL.md` 放到 `~/.workbuddy/skills/<name>/` 后，用 Skill 工具**立刻就能加载成功**，不需要重启应用，也不需要新开会话。

对比其他通道：插件钩子与 MCP 配置都是会话启动时快照，改完必须重启或新开会话；UI 上显示绿灯不等于当前会话已注入。

所以自建能力优先用 skill 承载，把需要重启的通道（插件钩子、自定义 MCP）视为不可用或需额外验证。判断某通道是否真生效，一律看运行时证据（技能看能否加载、MCP 看 CODEBUDDY_MCP_CONFIG 的 server 列表、插件看 daemon.log 的 enabledPluginIds），不看界面状态。
