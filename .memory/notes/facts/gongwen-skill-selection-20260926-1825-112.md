---
id: 20260926-1825-112
type: fact
status: active
title: 本机公文技能选型与版本差异
tags: [公文, skill, 工具, 选型]
env: win32
created: 2026-09-26
---

本机有两套 gongwen-skill，容易混淆：

- **完整版**（`~/.workbuddy/skills/gongwen-skill`，v1.12.74，源码 GitHub linhut/gongwen-skill）：26 个 CLI 子命令，纯本地不联网，遵循 GB/T 9704-2012，覆盖 24 类公文，适配应急管理局与筹委会的涉密材料。日常公文用它。
- **market 版**（`gongwen-skill__skillhub`，v1.12.55）：残缺壳，没有 engine 目录与 gongwen 包，SKILL.md 落后 19 个小版本，靠 install.py 联网 pip 装引擎。与完整版同名易冲突，不建议启用。

另有 dknowc 深知公文写作 v3.3.0 作为写作向补充（范文大纲、可信搜索溯源、红头文件模板），但硬性要求 DKNOWC_API_KEY 且必须联网，**涉密材料不可用**。

判断方法：先确认调用的是哪个路径下的技能；涉密场景只用本地完整版。
