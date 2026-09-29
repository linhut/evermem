# 恒忆 Evermem · 使用流程（v2.0）

> 个人跨会话经验记忆系统。核心一句话：**做过的经验自动进库，下次直接用，不重复试错。**
> 版权 Jose-AI · MIT · 全本地零云端

---

## 一、三种使用入口（同一套数据）

| 入口 | 启动 | 适合 |
|---|---|---|
| **桌面端**（推荐） | `web/launcher.py`（pywebview 原生窗口 + Web UI） | 日常浏览/治理/导入 |
| **浏览器** | `web/server.py` → http://127.0.0.1:8765 | 临时查看 |
| **CLI / Agent** | `mem.py` · `evermem_mcp.py`（MCP 工具） | 会话中 recall、编写脚本、DSH/Claude 调用 |

```bash
# 桌面端（开发热预览：PMEM_DEV=1 改前端自动刷新）
python web/launcher.py
```

---

## 二、日常三个动作时刻

| 时刻 | 动作 | 目的 |
|---|---|---|
| **会话开始** | `recall "今天要做的事"` 或热层自动注入 | 不裸奔，先看有何可复用 |
| **行动之前** | 写方案→recall"方案"；审公文→recall"公文质量"；勘察→recall"勘察" | 配方当骨架/清单 |
| **收尾沉淀** | `add` 一条（收尾必 add） | 经验越用越多 |

---

## 三、记忆怎么进库（五通道，界面带来源图标）

| 图标 | 通道 | 途径 |
|---|---|---|
| 📄 | 文档提炼 | 导入页：F 盘→提取→对话提炼 |
| 🤖 | 自动收割 | harvest scan → 候选 staged |
| 🔌 | MCP 写入 | agent 调 mem_record（写前查重） |
| ✍️ | 手动/界面 | 新建笔记（默认 staged） |
| ✨ | AI 提炼 | 精读提炼（source 指针可回溯） |
| 💠 | DSH 会话 | 从 DSH zstd 会话挖掘 |

**原则**：自动/新建默认 staged，**人工确认才转正保护召回质量**（信噪比优先）。

---

## 四、治理四操作（桌面端）

```
候选审核页   转正 staged→active / 存疑 / 暂缓
浏览页       双击编辑 · 标记 suspect · 归档 superseded · ★进热层
热层页       查看 20 条注入预览 · 一键移出（有进有出）
数据导入页   子模块「文档导入」：选空间/任意盘目录 → 扫描统计 → 提取块库 → 块预览；子模块「其他记忆导入」：复制提示词 → 粘贴画像 → 解析勾选 → staged 收库
```

---

## 五、会话知识扫描（从 137 个历史会话挖索引）

```bash
python scripts/knowledge_scan.py
# 产出 knowledge-base.md + kb.json：22→137 会话索引
# 数据源：WorkBuddy 13（工具调用）+ atomcode 9（真实对话）+
#         DSH 115（zstd 压缩事件流，gongwen-skill 31/AI-DATA 26…）
```

---

## 六、多宿主注入（一站式配置）

会话集成页：**每个宿主的 skill + MCP 一键装**
- Skill：WorkBuddy / Claude Code / DSH / CodeBuddy（~/.xxx/skills/personal-memory/）
- MCP：WorkBuddy（mcp.json+.mcp.json 双写）/ Claude（.claude.json）/ DSH（settings.yaml mcp-support）
- 生效：WorkBuddy+DSH 需重启/Trust；Claude 重启 CLI 后见 `mcp__evermem__mem_*`
- CLI 等价：`mem.py recall` / `mem.py hot --apply`（热层同步到必读文件）

---

## 七、桌面端六视图

```
记忆浏览  搜索(Ctrl+K,BM25带分数)/类型·状态过滤/双击编辑/来源图标
候选审核  staged 转正/存疑
数据导入  文档导入（任意盘目录→扫描→提取→块预览）/ 其他记忆导入（提示词→粘贴→staged）
热层预览  ★20 条注入可见→移出
统计诊断  分布/引擎/热层数
会话集成  skill 安装·MCP 安装·热层同步·会话收割·宿主状态
```

---

## 八、命令行速查

```bash
PY=python                                   # 解释器：PMEM_SYS_PY 指定或当前 python
"$PY" mem.py recall "融合通信 方案" --all      # 检索（--all 含候选）
"$PY" mem.py add --title "经验" --body "正文" --type procedure
"$PY" mem.py hot --limit 20 --tokens 900 --apply --target <MEMORY.md>  # 热层同步
"$PY" harvest.py scan --days 3                  # 收割近3天→候选
"$PY" scripts/ingest.py extract "<数据目录>" --out-dir "<块库目录>"   # 文档分块提取
"$PY" scripts/check_all.py                              # 全面功能检查（PMEM_TEST_DIR 设样本目录可测 extract）
"$PY" scripts/knowledge_scan.py                         # 历史会话知识索引
"$PY" recipes.py scan                                   # 配方盘点：分层 + 同名/隐式覆盖检测
"$PY" recipes.py resolve project:evermem org:yjxt       # 求值顺序（就近优先，附归属组织）
"$PY" recipes.py lock                                   # 生成 .recipe-lock.json 依赖锁
```

---

## 九、文件与配置

```
<仓库根>（= 项目根）            核心（进 Git）
├── mem.py / harvest.py / scripts/ingest.py / evermem_mcp.py / scripts/knowledge_scan.py / scripts/check_all.py
├── web/  server.py + launcher.py + index.html/js（桌面封装）
├── notes/{procedures,lessons,facts}/ + candidates/（数量以 mem.py stats 为准）
├── index.json（派生，不进 Git）· events/ · kb.json + knowledge-base.md
├── tests/test_recall.py + test_recipes.py（回归）
└── USAGE.md（本文档）

<数据块库目录>/           文档块库（PMEM_CHUNKS）
环境变量：PMEM_HOME / PMEM_SYS_PY / PMEM_CHUNKS / PMEM_SPACES / PMEM_THEME / PMEM_HOT_TOKENS
来源图标：📄文档 · 💠DSH · 🧬atomcode · 🤖收割 · 🔌MCP · ✍️手动 · ✨AI
```

---

## 十、典型场景

**写方案**：开始 recall"方案"→ 命中编制要点（350 分）→ 照骨架写 → 收尾 add
**DSH/Claude 会话**：skill 自动指导 recall → MCP mem_read/record 原生调用 → 写前查重防重复
**清理历史**：knowledge_scan 看 137 会话索引 → 对高价值会话深提炼 → 进记忆库
**验证健康**：check_all 35 项 + 回归测试，随时可跑