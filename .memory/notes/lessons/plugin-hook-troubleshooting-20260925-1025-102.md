---
id: 20260925-1025-102
type: lesson
status: active
title: 排查插件钩子未触发要依次查三层开关
tags: [workbuddy, 排查, hooks]
env: win32
created: 2026-09-25
---

第一层：`~/.workbuddy/plugins/installed_plugins.json` 是否已注册插件。
第二层：`~/.workbuddy/settings.json` 的 `enabledPlugins` 映射是否为 true —— 装了不等于启用，这一层最容易漏。
第三层：环境变量 `CODEBUDDY_DISABLE_EXTENDED_PLUGIN_HOOKS` 是否为 1。

判断插件是否真被加载，看 `~/.workbuddy/logs/daemon.log` 中 `resolveConversationConfig` 日志的 `enabledPluginIds` 列表，不要相信 UI 上的绿灯。同理，判断 MCP 是否真注入，看 `printenv CODEBUDDY_MCP_CONFIG` 里的 server 列表。

钩子与 MCP 配置都是会话启动时快照，修改后必须新开会话或重启应用，当前会话不会变化。
