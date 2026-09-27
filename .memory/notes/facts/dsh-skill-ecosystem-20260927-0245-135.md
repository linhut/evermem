---
id: 20260927-0245-135
type: fact
status: active
title: DSH 本地 skill 生态清单
tags: [DSH, skill, 生态, 资产]
env: win32
source: ~/.dsh/skills/（2026-09-27 实扫）
created: 2026-09-27
---

DSH（DeepSeek Harness）用户级 skills 目录（~/.dsh/skills/）已装的技能生态，可复用参考。

## 清单（11 个技能包）

| skill | 用途 |
|---|---|
| brainstorming | 创意工作（创建功能/组件/加功能时用） |
| finishing-a-development-branch | 实现完成、测试通过后的整合决策 |
| github-actions-docs | 编写/解释/自定义/迁移 GitHub Actions |
| gongwen-skill | 公文全流程（GB/T 9704 检查/优化/模板） |
| how-it-works | 解释内部机制（claude-mem 等如何工作） |
| modlens | 插片式"视觉"桥接纯文本模型（hard rule 风格） |
| personal-memory | 恒忆的跨会话经验记忆技能（本工具注入） |
| ppt-studio | 一站式生成原生 .pptx 演示文稿 |
| using-superpowers | 会话开始时建立技能发现与使用方式 |
| web-search | 联网搜索（最新信息/查找资料） |
| writing-skills | 创建/编辑/验证技能部署 |

## 启示

- DSH skill 生态 = 社区 superpowers 风格（using-superpowers/writing-skills/finishing-a-development-branch 是经典 superpowers 系列）
- 恒忆的 personal-memory 已与它们同目录共存，DSH agent 任务匹配时可互相协作
- 这些技能是"可用资产"：恒忆做同类功能（如公文）可参考 gongwen-skill / ppt-studio 的 SKILL.md 结构
- modlens 的"插件视觉"思路值得留意（视觉能力桥接）

## 例外与边界

- 描述从 SKILL.md frontmatter 提取；具体用法以各 SKILL.md 正文为准
- 部分 skill 有备份/平铺变体（如 ppt-studio.bak、modlens.md）