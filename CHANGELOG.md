# 变更日志

## Unreleased

## [0.2.1] - 2026-09-29

### 桌面壳（Web 版直接作为桌面程序）

- **desktop.py**：QtWebEngine 内嵌本地 Web 服务，把 7 视图 Web 版直接作为桌面程序；
  单实例锁、系统托盘、明暗主题/中英语言菜单、F12 开发者工具、空闲端口、`PMEM_HOME` 数据目录。
- **关闭行为**：点关闭默认「最小化到托盘继续运行」，弹窗询问是否停止服务（涉及 MCP/后台钩子）；真正退出走托盘「停止服务并退出」。
- **开机自启**：`--register-autostart / --unregister-autostart`（Windows Run 键 / XDG autostart），菜单「开机自启」勾选项，`--autostart` 托盘静默常驻。
- **无头兜底**：Qt/WebEngine 不可用时自动回退「起服务 + 系统默认浏览器」。
- **打包**：CI 每平台只产出一个桌面运行包（`evergem-<平台>-v*`，Windows exe / macOS .app.zip / Linux 二进制），替代原 cli/web/gui 三件套；GUI 冒烟以 `--smoke` 自退并断言退出码 0。


## [0.2.0] - 2026-09-29

### 候选审核批量操作与筛选 / 核心经验详情 / 文档导入指引（2026-09-29）

- **候选审核**：列表加关键词搜索与三档筛选（状态 / 类型 / AI 建议），全部前端过滤、后端契约不变；
  每条加复选框，支持全选（三态）/ 反选 / 清空（都只作用于当前筛选可见条目）；
  批量转正 / 批量存疑 / 批量归档，执行后 Toast 汇报成功 / 失败条数与失败 id。
- **修复候选转正假成功**：候选不在主索引 docs 里，旧的单条「转正 / 存疑」调
  `/api/note/<id>/status` 永远 404，却照样提示「已处理」。新增
  POST `/api/candidates/status`（`{ids:[...], status}`，批量与单条共用，直接改候选文件并重建索引），
  前端按 `updated/failed` 如实反馈。
- **核心经验详情**：整条卡片可点，复用候选审核「内容」的 `#viewMask` 弹窗，
  展示元信息（类型/状态/创建/来源/标签/文件）+ 相关记忆（按标题检索 top5，异步补位）+ 正文全文；
  「移出核心经验」按钮 stopPropagation，不再误触卡片。
- **文档导入指引**：`#paneDoc` 中与切换条重名的 `<h3>文档导入</h3>` 移除，
  原位换成「导入步骤 ①→②→③ + 注意事项」说明文案；表单 / 按钮 / 块列表 / 预览原样保留。
- **沉淀**：`notes/procedures/dev-selfcheck-recurring-mistakes-*.md` 汇总 6 类反复踩坑
  （层级、哨兵值、i18n 覆盖、路由方法、资源定位、假成功验证），挂入项目必读工作纪律。

### 发布工程（v0.2.0）

- **跨平台打包**：新增 `.github/workflows/build.yml`，Windows / Linux / macOS 三平台矩阵，
  PyInstaller 分别产出 `evermem-gui`（PySide6 桌面包）、`evermem-cli`（mem.py 命令行）、
  `evermem-web`（内嵌前端资源的 Web 服务）各一，冒烟后重命名上传 Release（tag 触发时自动附加二进制）。
- **打包适配**：`mem.py` 打包态数据目录回退「当前工作目录」（`PMEM_HOME` 仍为最高优先）；
  `web/server.py` 打包态静态资源路径改指内嵌 `web/` 资源；构建依赖清单 `requirements-build.txt`（仅 CI 用，产物运行时不依赖）。
- **同步范围**：`build/ dist/ *.spec .venv/ venv/` 一律忽略；仓库仅含代码 + 平台文档 + CI + 构建清单，
  私有配置 / 个人数据 / 密钥 / 日志一律不跟踪（内部约定见记忆库，不写入对外文档）。

### 数据导入模块（主菜单「文档导入」→「数据导入」，下含两个子模块）

- **两级结构**：主菜单项改为**数据导入**；内含 **文档导入**（保持原样，切块进块库）
  与 **其他记忆导入**（外部记忆收进笔记库）两个子模块，用分段控件 `.seg` 切换（与按钮/卡片同圆角同描边，
  只靠底色区分选中；双语文案同步）。
- **其他记忆导入 = ① 导出记忆提示词 + ② 记忆导入粘贴**：
  - ① 页面给出可直接复制的提示词（指令/身份/职业/项目/偏好 + `[YYYY-MM-DD] - 条目` 格式 + 代码块包裹 + 覆盖率说明）。
    唯一事实源是 `templates/usage-profile.prompt.md` 的 `COPY:BEGIN/END` 区间，
    由 GET `/api/profile/prompt` 读取——**前端不硬编码**，改模板即生效。
    复制走剪贴板 API，被浏览器拒绝时自动全选提示按 Ctrl+C。
  - ② 粘贴区沿用「来源 → 解析 → 列表勾选 → 导入」骨架，与文档导入视觉一致。
- **memimport.py（新）**：外部记忆导入引擎，零依赖。
  - 四种输入、格式自动探测：① 画像导出格式（`## 分类` + `[YYYY-MM-DD] - 条目`）
    ② 带/不带 frontmatter 的 Markdown（支持多篇拼接）③ JSON（`items/notes/memories` 等别名归一）
    ④ 目录批量收 `.md/.json`。
  - 导入前给计划：每条标 **可导入 / 疑似重复 / 已存在**，默认只勾可导入项。
  - 判重按**内容哈希**（id 带时间，不能用完整 id 判重，否则重复导入不幂等）。
  - 落点 `notes/<type>s/`，默认 `status: staged`——不参与检索召回，人工转正后生效。
  - 只读取源文件，绝不改动/删除被导入目录；`events/import.jsonl` 留审计。
- **API**：GET `/api/profile/prompt`（读提示词模板 COPY 区间）、POST `/api/memimport/preview`（只解析不写）、
  POST `/api/memimport/run`（写入，默认 staged）。
- **修复**：格式下拉默认传 `auto`，被 `fmt or detect_format()` 当成真实格式，画像塌成 1 条
  标题为分类名的笔记。哨兵值先归一再分派（同类哨兵：`all`/`*`/`any`/`0` 同坑）。

### 收割质量与治理（分层落地）

- **L1 收割质量**：任务级候选标题由原始口语指令蒸馏为动宾短语（`distill_intent`，正文仍保留原始指令全文）；
  踩坑取"真错误行"并过滤 Bash `Command:` 回显噪声、按 (命令,错误) 去重；最终方案不再截成 140 字残片
  （放宽到 600 字，脚本类方案附脚本正文前 40 行）。
- **L2 转正裁决唯一事实源**：新增 `promotion_decision()`（CLI 与 Web 共用），在评分与风险分级之上叠加
  **结构闸门**——任务级候选缺「任务目标/踩坑/最终方案」、方案为空、标题未蒸馏的一律留人工，不自动转正。
- **L3 热层保护**：自动收割转正的笔记默认不参与热层补足（64 条碎片不再稀释上下文），
  人工 pin 或 `mem.py hot --include-auto` 才放行。
- **否决原因可见性**：致否规则（危险命令、敏感、重复）排在规则列表首位，
  修正此前"否决原因显示成加分项（命令签名齐备）"的误导。

### 分层清理与画像导出

- **mem.py gc**：分层清理体检（T1 正式笔记永不删 / T2 候选池 ≥60 天滚动归档 / T3 归档区 ≥180 天或
  ≥1000 条或 ≥200MB 先写摘要再打包冷存 / T4 证据流 ≥90 天 gzip 压缩）。默认 dry-run，
  `--apply` 才动文件，`--prune` 才删原文。Web「统计诊断」页底部有同一份只读报告（GET /api/gc）。
- **mem.py profile**：导出使用画像草稿（指令/身份/职业/项目/偏好），按标签权重 3 / 标题权重 1 挑候选，
  附覆盖率说明；配套 `templates/usage-profile.prompt.md` 与 `docs/PROFILE-EXPORT.md`。
- **docs/RETENTION.md**：清理机制评估与推荐方案（触发条件、策略、对检索与性能的影响、保障措施、收益风险权衡）。

- **README 双语重写**（README.md 中文 / README.en.md 英文）：按优质开源项目标准重构——徽章、特性矩阵、界面预览（System Diagram 4 图）、快速开始、使用说明、架构、配置、隐私安全、贡献指南、许可；公开维护就绪。
- **harvest 任务级提炼**：识别同一会话"多次失败→成功"完整任务链，产出 lesson 级经验候选（含任务意图/踩坑/最终方案）；防归档/转正后循环重生。
- **评审修正**：任务经验候选不再被新颖官按"主题相近"误判重复归档；涉密/危险否决一律留人工。

- **数据多渠道同步备份 v3**（规格 docs/BACKUP-DESIGN.md）：
  - 渠道模型：local（增量镜像，零依赖）/ archive（全量快照 zip，保留 N 份）/ remote（ssh/scp 增量镜像，可选）/ mail（SMTP 附件，可选）。
  - 每渠道独立：范围（notes/events/index/meta）、频率（小时）、启用开关、失败记录与连续失败计数。
  - 全局：自动备份（后台线程按频率轮询）、告警邮箱（连续失败≥2 发邮件，可选）、备份日志 backup.log、最近 20 条历史。
  - 同步后校验（文件数/大小）；换目标后增量不误跳（目标端存在校验）；旧单渠道配置自动迁移。
  - Web「数据备份」页升级为**渠道列表管理**（新增/删除/编辑各渠道、立即备份单渠道或全部、从渠道恢复、查看日志）；API：GET /api/backup、GET /api/backup/log、POST /api/backup/{save,run,restore}。
- 修复：GET /api/backup/log 路由错置于 POST（补 GET 分支）；增量同步换目标空同步缺陷（v2 修复，v3 保留目标端存在校验）。

## v0.1.0（2026-09-27）· 首个可发布版本

### 定位
恒忆 Evermem：个人跨会话经验记忆平台（通用知识库）。经验自动进库、跨会话复用、全本地零云端。

### 功能（全部经测试验证）
- **核心引擎 mem.py**：级联检索（意图签名/失败指纹/BM25/链接扩展）、新近度加权、热层同步与 token 预算、候选池治理（容量/TTL/AI 评分）、入库存档（add/reindex/stats/show）。
- **会话收割 harvest.py**：多宿主（WorkBuddy/DSH/atomcode）会话落盘 → 候选，无钩子依赖。
- **文档导入 ingest.py / scan_spaces.py / knowledge_scan.py**：F 盘语料 → 块库 → 提炼。
- **MCP 桥 evermem_mcp.py**：mem_read / mem_record（写前相似治理）/ mem_update / mem_hot，WorkBuddy/Claude/DSH 三宿主已配置。
- **Web 界面**（server.py，15+ API + 三层缓存）：六视图（浏览/候选审核 AI 徽章/文档导入/核心经验/统计诊断/接入设置），性能基线列表 6ms。
- **skill personal-memory**：4 宿主已安装，强制调用时机规则。
- **注入通道**：热层（WorkBuddy 20 条 + DSH 12 条）+ 工作纪律（每次会话自动注入）。
- **治理**：AI 启发式评分 + 人工终审双审核、状态机（staged→active→suspect→superseded）、写前相似治理、热层有进有出。
- **数据与代码分离**：数据（笔记/事件/索引）不进版本库，走 `backup.py` 云端备份增量同步。

### 测试（发布前全绿）
- check_all.py：35/35 通过（引擎/MCP/Web API/边界/前端/数据健康）
- bench_verify.py：16/16 通过（CLI/MCP/Web/回归 + 性能基线）
- bench_search.py：20/20 预期命中，top1 均值 167.0
- tests/test_recall.py：6 组全过（含防误召回、staged 夹具自建自删）

### 数据资产（本地，不进仓库）
- 正式笔记 65 条（procedure 50 / lesson 6 / fact 9），热层 20，F 盘块库 9 空间 9500+ 块。
- 平台文档：PLATFORM v2 / REVIEW / TOOLS / MONTHLY 模板+首报。

### 已知限制
- 检索为词面级（BM25 中文 2/3-gram），同义词依赖标签；向量检索待语料破千后引入。
- 候选 AI 评分为启发式规则，人工终审兜底；LLM 精审接口需自行配置 PMEM_AI_REVIEW（涉密环境保持离线）。
- 热层 auto-fill 补足质量存疑，热层补充一律人工评审。