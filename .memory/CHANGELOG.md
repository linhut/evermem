# 变更日志

## Unreleased

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