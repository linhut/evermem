# 项目长期记忆

## 品牌与项目命名（2026-09-27 定）

- **工具名：恒忆（Evermem）**，代号 pmem，作者 Jose-AI，MIT 许可，官网 www.linhut.cn。
- 定位：个人跨会话经验记忆系统——经验自动进库、跨会话复用、全本地零云端。
- 已落地：Web 版（网页 UI + pywebview 桌面封装，跨 Windows/macOS/Linux）、六视图、会话集成页。
- 仓库路径：C:/Users/Administrator/Documents/个人知识库/.memory/（进 Git），块库在 F:/知识库数据/chunks/。

## 当前项目方向：个人跨会话经验记忆系统

目标是把会话中的昂贵试错（如某命令尝试很多次才找到正确用法）沉淀为本地长期记忆，下一次会话在行动前直接复用，而不是依赖模型重新训练。

已确定的设计原则：

- 不做单一事实源，按写入者划分：执行证据用 JSONL 追加，知识正文用 Markdown 原子笔记，状态与索引用 SQLite。
- 索引可从 Markdown 与 JSONL 幂等重建；SQLite 不进 Git；汇总 Markdown 只是生成视图。
- 记忆分层：原始证据、情景、语义、程序配方、工作状态五层，程序配方是核心资产。
- 检索顺序：精确意图签名 → 失败指纹 → BM25 → 链接扩展 → 可选向量召回；向量只提供候选。
- 生命周期状态：staged / active / suspect / superseded / archived；自动抽取不得直接进 active。
- 形态：以插件为骨架（hooks + MCP + skill + agent/command），独立界面只做策展与导入。
- 多智能体：单一写者服务、命名空间隔离、子代理只交候选、冲突人工裁决。

## 宿主能力事实（已核实）

- 插件包结构：`.codebuddy-plugin/plugin.json`（name/version/commands/skills/hooks/mcpServers）+ `hooks/hooks.json` + `mcp/` + `skills/` + `agents/` + `commands/`。
- 钩子事件至少支持：PreToolUse（带 matcher 按工具名匹配）、SessionStart、UserPromptSubmit、SubagentStop。
- PreToolUse 返回值支持 blockingDetails（阻断）、modifiedInput（改写入参）、stdout 与 hookSpecificOutput（注入上下文）——门控三级能力成立。
- PreToolUse 传给钩子的 stdin 字段：hook_event_name、session_id、transcript_path、cwd、tool_name、tool_input。
- 钩子 stdout 契约：`continue:false` + `stopReason` 阻断；`hookSpecificOutput.permissionDecision:"deny"` + `permissionDecisionReason` 拒绝；`hookSpecificOutput.updatedInput` 改写工具入参；`hookSpecificOutput.additionalContext` 注入上下文；`suppressOutput` 抑制输出。
- 插件清单目录名可为 .codebuddy-plugin / .workbuddy-plugin / .claude-plugin；钩子文件路径固定为 hooks/hooks.json；环境变量 CODEBUDDY_DISABLE_EXTENDED_PLUGIN_HOOKS=1 会禁用插件钩子。
- 插件注册表为 ~/.workbuddy/plugins/installed_plugins.json；钩子在进程启动时加载，新增插件必须彻底重启 WorkBuddy（仅刷新页面无效）。
- **插件装了不等于启用**：必须在 ~/.workbuddy/settings.json 的 `enabledPlugins` 映射中把 `"name@marketplace"` 设为 true，否则会话启动时的 `enabledPluginIds` 不含它，钩子完全不加载。排查时看 daemon.log 的 `enabledPluginIds` 列表即可确认。
- **关键阻断：桌面端禁用第三方插件钩子。** app.asar 在启动子进程时硬编码注入 `CODEBUDDY_DISABLE_EXTENDED_PLUGIN_HOOKS: "1"`；且 conversation-hook 策略为 `allowedTrust: ["trusted"]`。因此插件的 hooks.json（PreToolUse 等）在 WorkBuddy 桌面端不会执行，这是产品信任模型，不是配置问题。
- 桌面端自己的会话钩子管线（仅 trusted 来源）：beforePrompt（composition=concat）、prepareConversationPrompt（reduce）、resolveCommand、contributeEnv:pre、resolveConversationConfig、refineConversationConfig。第三方用不了。
- 桌面端仍可用的插件扩展点：mcp/（MCP 工具，实测 sheetagent、weixinpay 均通过 CODEBUDDY_MCP_CONFIG 注入）、skills/、commands/、prompt/、agents/。
- **插件 MCP 的市场限制**：把插件登记为 `xxx@local` 这类不存在的 market 名时，enabledPluginIds 会包含它，但 mcpServers 不会注入 CODEBUDDY_MCP_CONFIG。已验证 github/weixinpay/sheetagent 等来自真实 marketplace 的插件才有 MCP 注入。
- **绕行：独立注册 MCP**：绕过插件机制，直接写 MCP 配置（command 用绝对路径 node，args 指向脚本），重启/新开会话后在连接器管理页点 Trust 生效。这是本地自建记忆服务的推荐通道。
- **MCP 配置文件名**：宿主代码里实际检查的是 `.mcp.json`（带点前缀），与系统提示所说的 `mcp.json` 不一致；稳妥做法是两者都写。
- **判断 MCP 是否真注入**：看 `printenv CODEBUDDY_MCP_CONFIG` 里的 server 列表，UI 显示绿色不等于当前会话已注入——MCP 配置是会话启动时快照，新加的 server 必须新开会话才生效。
- 可能的绕行路径：① 改 app.asar 把 "1" 改成 "0"（破坏完整性、升级被覆盖，不推荐）；② 用 codebuddy CLI headless 跑，不经桌面端注入；③ 接受降级，用 MCP 工具 + skill 规范 + 会话级注入实现门控。
- 回收站接口在本环境被安全策略拦截（Add-Type 与 COM 均被禁），删除只能用 rm，必须先备份再二次确认。

## 公文技能选型（本机实测 2026-09-25）

- **主用 gongwen-skill 完整版**（~/.workbuddy/skills/gongwen-skill，v1.12.74，用户自维护 linhut/gongwen-skill）：26 个 CLI 子命令，纯本地不联网，GB/T 9704-2012，覆盖 24 类公文，适配应急管理局/筹委会涉密材料。
- **market 版 gongwen-skill__skillhub 是残缺壳**（v1.12.55）：无 engine/、无 gongwen 包，SKILL.md 落后 19 个小版本，靠 install.py 联网 pip 装引擎；与完整版同名易冲突，不建议启用。
- **运行解释器必须用 C:/Python314/python.exe**：managed python 3.13.12 缺 python-docx 与 pydantic，`python -m gongwen` 会 ModuleNotFoundError。
- dknowc 深知公文写作 v3.3.0 为写作向互补（范文大纲、可信搜索溯源、红头文件），硬性要求 DKNOWC_API_KEY + 联网，涉密材料不可用。

- **最终形态（方案 B，已落地 MVP）**：不依赖宿主任何开关，用本地 CLI + skill。CLI 在**本项目** `个人知识库/.memory/mem.py`（零依赖 Python，BM25 + 中文 2/3-gram，JSON 索引可从 Markdown 幂等重建），技能在 `~/.workbuddy/skills/personal-memory/SKILL.md`（规定会话开始、行动前必 recall，收尾必 add）。笔记存于 `.memory/notes/{procedures,lessons,facts}/`，status 用 active/suspect/superseded；`.memory/.gitignore` 已排除 index.json 与 __pycache__。
- **记忆库位置约定**：笔记放项目内 `.memory/`（进 Git），不放任何 AI 工具的私有配置目录，换宿主不丢数据、不会被工具的配置清理误删。
- 检索调优：召回门槛需命中 34% 查询词；语料停用词规则仅在笔记 ≥20 条时启用（小语料会误杀关键词）。小语料常见词区分度不足属已知限制。
- 宿主命令含长中文时会被沙箱拦截（`sandbox-center cmd decisionRecord missing actual resource subject`），写笔记改用 Write 工具建文件再 reindex。
- **用户级技能热加载**：`~/.workbuddy/skills/<name>/SKILL.md` 建好后，Skill 工具立即能加载，无需重启或新会话；插件钩子与 MCP 则是启动时快照，必须重启。自建能力优先用 skill 承载。
- **专家包即"Agent 系统提示词"**：WorkBuddy 专家 = plugin.json + agents/{name}.md，存于 `$WORKBUDDY_CONFIG_DIR/plugins/marketplaces/my-experts/plugins/`（默认 ~/.workbuddy/plugins/marketplaces/my-experts/plugins/），每次与专家对话自动加载 Agent MD 正文。**frontmatter 支持 `skills: [{skill-name}]` 启动时预加载 Skill**——是"每次对话自动注入记忆技能"的原生通道；改完须 validate_expert.py + register_expert.py 才生效；agentName=MD 文件名、name 字段不可改。工具脚本在 WorkBuddy 内置 skill expert-manager/scripts/。
- **WorkBuddy 规则系统（官方文档 docs/ide/User-guide/Rules，asar 含"自定义规则"字样）**：多层规则=给 AI 的系统级指令。① 项目规则：项目 `.codebuddy/rules/` 下每规则一个文件夹含 RULE.mdc，进版本控制，可路径模式限定范围；② 用户规则：本机全局、跨项目、不进版本控制；③ CODEBUDDY.md：项目根纯 Markdown 默认全文加载（兼容 AGENTS.md）。**三种应用类型**：总是 alwaysApply（每会话自动、加载原文）；智能体请求 agent requested（按 description 相关性自动、只载名称描述、需要时再读原文）；手动 manual（@my-rule 触发、不自动加载）。规则内容加在 prompt 开头；**只加会话开始处→改后须新会话才生效**。优先级建议：核心 3-5 条设 always、其余 manual/requested（性能按需加载）。调试：问"当前应用了哪些规则？"AI 会列出。

## 工作纪律（每次会话自动注入，必须遵守）

- **文档类任务动笔前先查记忆**：接到任何"编写 / 优化 / 生成"类文档任务（通知、请示、报告、方案、讲话稿、函件、总结、自查报告等），动笔之前必须先执行一次恒忆检索：`mem.py recall "<文档类型+关键词>" --limit 5`。
  - 命中：先向用户展示命中经验的标题与要点（模板结构 / 检查清单 / 本地政策文号 / 踩坑），再动笔，可复用结构直接套用
  - 无命中：明确告知"恒忆记忆库无相关经验"，再按通用规范写作——不得假装查过或编造记忆
- **收尾沉淀**：任务产生了已验证的可复用经验（新模板、要点、踩坑、本地文号）时，写 Markdown 到 `.memory/notes/<type>s/`（id 格式 YYYYMMDD-HHMM-NNN 递增，frontmatter 含 type/status/title/tags/source）并 reindex。
- **禁令**：检索无命中就明说无命中，不凭印象编造"上次是这样"。

## 用户偏好

- 讨论方案时要求认真思考、给出取舍与失败边界，不急于实施。
- 参考过 dsh-memoir（DeepSeek Harness 本地记忆插件）与得到大脑类个人知识库产品。

<!-- MEMORY_HOT:START -->
## 核心经验（自动生成，勿手改；改笔记后重跑 mem.py hot --apply）

- (procedure) 用 WorkBuddy editor_sdk 读取 .doc 老格式文档：读取 .doc 老格式（olefile 提取乱码）的正规流程——用 WorkBuddy…
- (procedure) 恒忆 skill 与 MCP 的多宿主一键安装：从恒忆"会话集成"页一键安装实测提炼。skill + MCP 双通道装到各 agent…
- (fact) WorkBuddy 桌面端禁用第三方插件钩子：宿主 app.asar 在启动子进程时硬编码注入…
- (fact) 会话过程数据全量落盘可直接收割无需钩子：WorkBuddy 把每个会话的完整执行历史写到…
- (fact) SQLite 不能放网络盘 NAS 与 SMB NFS：SQLite 数据库**不能放在网络文件系统上**（NFS、SMB/CIFS…
- (procedure) 政府应急指挥信息化项目方案编制要点：从历史项目"五级联动视频会议系统初步设计方案 V3"提炼的编制框架…
- (procedure) 融合通信平台能力模型与开放接口经验：从历史项目"长沙市应急指挥中心融合通信优化升级方案 V4.2"提炼…
- (procedure) 机房整合与设备搬迁项目方案编制要点：从历史项目"政务云设备搬迁及机房撤并技术方案（2025-08）"与"机房整合工作方案（纯网…
- (procedure) 大型体育赛事场馆信息化勘察与保障要点：从第十三届全国少数民族传统体育运动会信息技术部实际工作提炼（二次勘察总结 +…
- (procedure) AI 生成公文成品质量检查清单：从 gongwen-skill 生成"工作提示函"与用户手动调整版的 OOXML…
- (procedure) 大型体育赛事场馆信息技术指南编制体系：从第十三届全国少数民族传统体育运动会《竞赛/非竞赛场馆（场地）信息技术指南》全套 22…
- (procedure) 系统上云部署方案编制要点：信息技术部"系统上云部署方案"模板归纳（天翼云）。任何系统上云可套用此结构。
- (procedure) 赛事网络规划图纸的组织方法：从运动会网络规划拓扑图（Visio，12 页、4000+ 图形元素）的架构分析提炼…
- (procedure) 测试赛倒排计划表编制方法：从秋千测试赛"网络及安全倒排计划表"提炼。测试赛保障用倒排计划（从赛日往前排任务）。
- (procedure) 场馆综合演练实施方案编制要点：从秋千项目综合演练实施方案（9月19日演练）提炼。测试赛前综合演练的编制框架。
- (procedure) 测试赛场地配合需求清单编制要点：从秋千测试赛"信息技术部需执委会配合事项"清单提炼…
- (procedure) 大型赛事信息技术服务方案总纲编制要点：从运动会《信息技术服务方案》（350 块，设计院编制）提炼…
- (procedure) 政府采购设备项目履约验收流程与质保期约定：从 IOCC 设备采购项目《政府采购项目履约验收书》提炼…
- (procedure) 测试赛赛时运行保障要点（秋千测试赛实录）：从秋千测试赛赛时 10 份每日运行报告（9月15-24日）提炼的真实保障经验…
- (procedure) 云网通信组场馆勘察要点与分工界面：从云网通信组座谈会发言稿提炼。与"场馆信息化勘察要点"（id…

<!-- MEMORY_HOT:END -->
