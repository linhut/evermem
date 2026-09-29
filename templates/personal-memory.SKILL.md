---
name: personal-memory
description: 个人跨会话经验记忆。当任务涉及重复踩坑、命令用法、工具兼容性、环境限制，或用户提到"上次怎么做过""之前试过""记得吗""查记忆"时使用；在会话开始、执行高风险或易错操作前、以及任务收尾沉淀经验时必须调用。
---

# 个人跨会话经验记忆（pmem）

本地记忆库，用于避免重复试错。**不依赖任何宿主钩子或 MCP 通道**，纯本地 CLI 加 Markdown 笔记。

笔记目录由环境变量 `PMEM_HOME` 决定，未设则用脚本所在目录。它与任何 AI 工具的私有配置目录无关，换工具不丢数据；笔记进 Git，索引不进。

## 运行环境

```bash
# 跨平台写法：数据目录用环境变量，Python 用当前环境的解释器
export PMEM_HOME="<你的数据目录>"      # Windows 用 set PMEM_HOME=...
PY="python3"                          # macOS/Linux
# Windows 示例：PY="python"
MEM="$PMEM_HOME/mem.py"
```

本机配置示例（占位，换机器必改）：

```
PMEM_HOME=<数据目录>       # 例如 C:/Users/<you>/Documents/evermem-data/.memory
PY=<python 路径>           # 或直接用 PMEM_SYS_PY / python
```

**不要把真实绝对路径写进任何要分发到网络的文档或脚本里**——换机器必然失效且泄漏本机信息。

## 强制调用时机

1. **会话开始**：接到实质任务后，先用任务关键词执行一次 recall。
2. **行动前**：准备执行 shell 命令、调用不熟悉的 CLI、安装或配置工具之前，先 recall 该工具名。
3. **连续失败**：同一问题失败两次以上，recall 错误特征（用错误信息原文片段）。
4. **任务收尾**：产生了**已被验证**的结论、踩坑原因或可用配方，执行一次 add。

## 命令

```bash
"$PY" "$MEM" recall "查询词"          # 检索，默认 5 条
"$PY" "$MEM" recall "查询词" --limit 3
"$PY" "$MEM" recall "查询词" --all     # 含非 active
"$PY" "$MEM" show <id>                 # 看全文
"$PY" "$MEM" reindex                   # 笔记改动后重建索引
"$PY" "$MEM" stats                     # 统计
```

新增记忆建议直接写 Markdown 文件到 `$PMEM_HOME/notes/<type>s/`（中文长文本走 shell 参数易被沙箱拦截），然后执行 `reindex`。格式：

```
---
id: <YYYYMMDD-HHMM-NNN>
type: procedure | lesson | fact
status: active | suspect | superseded
title: 一句话标题
tags: [标签]
env: win32
created: 2026-09-25
---

正文：写清问题、无效做法及原因、已验证的正确做法、适用范围与例外、来源。
```

## 热层：保证一定被看到

检索依赖"我主动去查"，一旦没查就全盘失效。所以最高价值的记忆要进**热层**——同步到宿主每次会话必读的项目记忆文件，不检索也会出现在上下文里。

在笔记 frontmatter 加 `hot: true` 即可标记为热层候选，然后：

```bash
"$PY" "$MEM" hot --limit 12                      # 预览（只取人工标记的）
"$PY" "$MEM" hot --apply --target "<项目>/.workbuddy/memory/MEMORY.md"
"$PY" "$MEM" hot --apply --auto-fill --target "<项目>/.workbuddy/memory/MEMORY.md"   # 人工标记不足时算法补足
```

规则：热层**宁少勿多**，超过二十条就会挤占上下文、反而被忽略。只放"行动时能直接救命"的硬知识（命令、工具、环境限制）；架构、调研、移植这类元笔记不要进热层。

注意：宿主记忆文件同样是会话启动时快照，同步后要等下一个新会话才生效。

## 入库纪律（违反即产生不可信记忆）

- **只写已验证的内容**。没跑通的不写进正文，或标注为待验证并把 status 设为 suspect。
- **必须写适用范围与例外**。命令类记忆要写清系统、shell、工具版本。
- **正文中禁止出现密钥、令牌、内网地址、个人隐私**。
- 已有结论被推翻时，新建一条并把旧的 status 改成 superseded，**不要删除历史**。
- 检索**无命中就明确说无命中**，不要凭印象编造"我记得上次是这样"。

## 已知限制

- 语料很小（少于 20 条）时，常见词区分度不足，可能出现噪声命中；笔记增多后自动改善。
- 检索基于词面匹配加中文 2/3-gram，不理解同义词，查询时尽量用笔记里可能出现的原词。
- 索引是 JSON，可随时从笔记 `reindex` 重建；笔记是唯一权威，索引损坏不丢数据。
