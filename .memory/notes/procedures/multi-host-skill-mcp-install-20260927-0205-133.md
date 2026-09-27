---
id: 20260927-0205-133
type: procedure
status: active
title: 恒忆 skill 与 MCP 的多宿主一键安装
tags: [MCP, skill, 多宿主, 安装, 部署]
env: win32
hot: true
source: 恒忆 Evermem（.memory/web/server.py /api/installhost /api/mcpinstall，实测 2026-09-27）
created: 2026-09-27
---

从恒忆"会话集成"页一键安装实测提炼。skill + MCP 双通道装到各 agent 宿主的方法与坑。

## 各宿主安装位置与格式

**Skill（标准 SKILL.md，用户级）**
- WorkBuddy：~/.workbuddy/skills/personal-memory/SKILL.md（用户级技能热加载，无需重启）
- Claude Code：~/.claude/skills/personal-memory/SKILL.md（Claude 读取 skills/ 目录）
- DSH：~/.dsh/skills/personal-memory/SKILL.md（$DSH_HOME/skills 用户级 root，目录被监视热刷新）
- CodeBuddy：~/.codebuddy/skills/personal-memory/SKILL.md

**MCP（stdio，evermem_mcp.py 为 server）**
- WorkBuddy：~/.workbuddy/mcp.json **和** ~/.workbuddy/.mcp.json 双写（宿主实际检查带点前缀的 .mcp.json）；需重启 + 连接器页 Trust
- Claude Code：~/.claude.json 的 mcpServers 键（stdio 省略 type 字段；缺 type 且只有 url 会静默丢弃）
- DSH：~/.dsh/settings.yaml 的 mcp-support.servers 块（需已安装 @deepseek-ai/dsh-mcp-client 插件）

## 安装要点

- JSON 宿主（WorkBuddy/Claude）：读原文件 → 合并保留既有 mcpServers → 写回（绝不覆盖其他服务器）
- DSH YAML：检测已有 serverName 跳过；无则安全追加块（注意缩进，勿破坏既有 settings）
- command 用托管 Python 绝对路径，args 指向 evermem_mcp.py 绝对路径
- 安装后提示：WorkBuddy/DSH 需重启或新会话生效；WorkBuddy 还须 Trust；Claude 重载/重启 CLI

## 界面与 API

- Web「会话集成」页：①skill 卡（hostList+installHost）②MCP 卡（mcpList+mcpInstall）
- GET /api/mcpsetup：三宿主 MCP 状态 + entry 预览
- POST /api/mcpinstall {host: workbuddy|claude|dsh}：写入配置
- POST /api/installhost {host: 名称}：复制技能模板到用户级

## 验证（2026-09-27 实测）

4 宿主 skill 全装 ✅（WorkBuddy/Claude/DSH/CodeBuddy）；3 宿主 MCP 全装 ✅（WorkBuddy/Claude/DSH）。
生效动作：WorkBuddy 重启+Trust、DSH 重启/重载 MCP、Claude 重启 CLI 后看 mcp__evermem__mem_read。

## 例外与边界

- CodeBuddy 的 MCP 配置文件未确认（~/.codebuddy 结构有限），skill 可用，MCP 待验证
- MCP 工具名命名空间 mcp__<serverName>__<tool>，改 serverName 会改工具可见名