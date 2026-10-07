# 恒忆数据备份：渠道配置体验优化设计（BACKUP-UX）

> 目标：解决"渠道配置繁琐、用户体验不佳"，参考成熟开源备份工具（Rclone / restic / Duplicati / Borg）
> 的"多存储后端统一管理"理念，在不破坏现有数据安全与兼容性的前提下，让配置直观、易用、可测试。
> 现状实现见 docs/design/BACKUP-DESIGN.md；本文为 UX 优化方案与改动范围。

---

## 一、当前配置痛点（逐条）

| # | 痛点 | 影响 |
|---|------|------|
| 1 | **字段多而分散**：渠道卡片 6-10 个字段（名称/目标/频率/范围勾选/保留/SSH 端口/SMTP 四项），mail 渠道达 7+ 字段，一次看不过来 | 新用户不知道哪些必填、感知"繁琐" |
| 2 | **无向导**：新增渠道 = 选类型 → 空白表单逐字段手填；无"选后端→自动出模板"的流程 | 每一步都要理解，易错 |
| 3 | **默认值缺失**：频率/保留/范围虽有默认，但 UI 不显式呈现，用户被迫处理 | 绝大多数用户其实想要默认值 |
| 4 | **无连接测试**：填完只能"保存→立即备份"才知道目标是否可用（可写/可达/SMTP 通不通） | 试错成本高，失败原因难定位 |
| 5 | **配置与执行语义不清**："保存设置并立即备份"把两件事绑在一起，用户易误解 | 对自动备份节奏的预期混乱 |
| 6 | **渠道命名与分组混乱**：默认名 type-i，不直观；列表扁平无分组 | 多渠道时难以管理 |

## 二、参考项目设计理念（提炼可借鉴点）

| 项目 | 核心理念 | 借鉴到恒忆 |
|------|---------|-----------|
| **Rclone** | 统一"remote 后端"抽象（local/S3/WebDAV/...），每个 remote 一条配置；`rclone config` 交互向导 + `rclone lsd` 测试连接 | **Provider 抽象 + 向导式配置 + 连接测试** |
| **restic** | repository 初始化（init）+ 密码/密钥管理 + snapshot/forget 保留策略清晰 | **渠道=后端+通用参数分层；保留策略显式化** |
| **Duplicati** | Web 向导：选后端→填连接→测试→选目录→计划→加密/压缩→完成，每步可跳过用默认 | **三步向导 + 每步默认值可跳过** |
| **Borg** | repo init 即"建立可信连接"，与数据写分离；加密本地化 | **测试连接不破坏目标（只读探测/发送测试邮件）** |

## 三、优化方案

### 3.1 统一接口层：Provider 抽象（核心）
渠道配置从"扁平字段"收敛为 **provider + 通用参数 + provider 特有参数**：

```json
{
  "provider": "local",                 // 后端类型：local/archive/remote/mail
  "name": "坚果云",
  "enabled": true,
  "scope": ["notes", "events", "index", "meta"],
  "frequency_hours": 24,               // 通用参数（所有 provider 共有，有默认值）
  "retention": 7,                      // 通用（archive 特有但有默认）
  "target": "D:/坚果云/evermem"         // 各 provider 的"主连接"，语义统一
  // provider 特有参数收进 params：{"ssh_port":22} / {"smtp":{...}}
}
```

- provider **schema 模板**（server 暴露 `/api/backup/providers`）：每 provider 声明字段、类型、必填、默认值、占位提示——**前端据此动态渲染表单**，不再硬编码。
- 旧配置自动迁移：现有 channels 数组 → 新模型（target/frequency/retention/smtp 映射到 provider 参数，无感）。

### 3.2 向导式配置（新增渠道三步）
1. **选后端**：四张后端卡片（local 镜像 / archive 快照 / remote 服务器 / mail 邮箱），每张一句话说明 + 依赖提示（零依赖/需 ssh/需 SMTP）
2. **填连接**：仅渲染该 provider 的 schema 表单，**默认值自动填充**（频率 24、保留 7、范围全选、mail 端口 465），用户只管填目标
3. **测试连接**：`POST /api/backup/test`——local 检测可写；archive 试建目录；remote ssh 探测；mail 发一封测试邮件。**通过才允许保存**（可跳过，但强烈建议）

### 3.3 配置展示与操作分离
- 渠道列表**按 provider 分组**，卡片折叠显示：名称/目标/状态（上次/失败×N/到期）@更多
- 卡片上操作：立即备份 / 测试连接 / 恢复 / 编辑 / 删除 | 全局：自动备份开关 + 告警邮箱
- "保存"与"备份执行"彻底分离：保存只写配置；执行用独立按钮

### 3.4 默认值填充与预设
- provider 模板自带默认值（前端下拉即得，看不懂的直接存）
- 常用预设：local→"本机网盘目录"、archive→"本机快照目录/<快照目录>"、mail→"SMTP 465 默认"——一键填入

### 3.5 兼容性与数据安全
- **配置兼容**：pmem_backup.json schema 向后兼容（channels 数组仍有效，新字段叠加）；旧渠道迁移脚本（已有 load_cfg 迁移逻辑，扩展 provider 映射）
- **数据安全**：SMTP 密码不落明文到配置（优先 `PMEM_SMTP_PASS` 环境变量，配置里只存 host/port/user；测试连接不发真实数据、只发测试邮件）；测试连接全程只读探测/试建，不触碰已有备份数据；恢复仍有双重确认
- **不变性**：渠道执行逻辑（run_channel 各 provider）作为**适配器层**保持稳定，UX 改动不触碰数据流；备份状态/审计/日志机制不变

## 四、改动范围（可落地分阶段）

| 阶段 | 改动 | 文件 | 说明 |
|------|------|------|------|
| **P1 接口层** | Provider schema 定义 + 默认值表 | backup.py（新增 `PROVIDERS` schema + `test_connection(provider, cfg)`） | CLI 也可 `backup.py test --channel X` |
| P1 后端 | `/api/backup/providers`（模板+默认值）、`/api/backup/test`（测试连接）、save 兼容新模型 | web/server.py | |
| **P2 前端向导** | 新增渠道改三步向导（后端卡片→动态表单→测试→保存）；渠道卡按 provider schema 渲染 | web/index.js + index.html（新增 modal 向导） | 核心体验提升 |
| P2 分组展示 | 渠道列表按 provider 分组 + 折叠信息；状态更清晰 | web/index.js | |
| P3 预设 | 常用预设一键填充 | web/index.js + backup.py PROVIDERS | |
| 文档 | BACKUP-DESIGN/README 增补 | docs/* | |

**建议实施顺序**：P1 接口层（schema + 测试，半天）→ P2 向导（核心 UX，1 天）→ P3 预设。兼容与安全约束贯穿（见 3.5）。

## 五、失败边界说明
- Provider 抽象不改变执行引擎（数据流不动），只改变"配置形态与交互"——风险集中在 schema 映射与迁移，用迁移脚本 + 现有配置回归测试覆盖
- mail 测试连接需要真实 SMTP，未配置凭据时按钮给出明确引导，不阻塞其他渠道
- 向导式新增比"卡片直填"多一层交互，但对新手更友好；老用户仍可走"编辑现有渠道"的快速路径

## 六、开源项目调研借鉴落地（2026-09-28）

### 调研结论（GitHub 成熟项目）

| 项目 | 可借鉴设计 | 采纳方式 |
|------|-----------|---------|
| **Borgmatic** | 单文件声明式配置（备份什么/存哪/留多久/前后钩子）；`config generate` 交互向导生成带注释模板；好默认值；一条命令跑全流程 | 配置保持"一份 pmem_backup.json 声明"；默认值显式呈现；新增 **`backup.py check` 命令**做完整性校验 |
| **rclone** | `config` 交互向导；remote 分组存 conf；**`obscure` 密码封装**；**`check` 校验 hash 一致性** | ✅ 已落地 `check`（云端 vs 本地文件存在+大小校验）+ `obscure`（SMTP 密码混淆存储）；Web 渠道卡片加「校验完整性」按钮 |
| **Kopia**（除本文外调研） | 保留策略（policy）与 repository 分离，策略模板化 | 保留策略在渠道内独立字段 + 默认档（7 份），高级可调 |

### 已落地（本轮）
1. **`backup.py check`**：local 校验文件存在+大小、archive 校验 zip 完整性；CLI `--channel` 可选；Web「校验完整性」按钮 + 结果 toast。
2. **`obscure` 密码封装**：mail 渠道 SMTP 密码保存时混淆（ob1: 前缀）存储，运行期 deobscure；环境变量 `PMEM_SMTP_PASS` 仍优先。

### 待实施（向导式新增渠道，方案）
1. 新增渠道改**三步向导弹窗**：选后端卡片（local/archive/remote/mail 一句话说明）→ 动态表单（仅该后端字段，**默认值自动填充**：频率 24/保留 7/范围全选）→ **测试连接**（local 可写/remote ssh/mail 测试邮件）→ 保存。字段 schema 由后端 `/api/backup/providers` 下发。
2. 常用预设一键填入（"本机网盘目录/NAS"等模板）。
3. 配置展示按 provider 分组 + 折叠；保存与执行彻底分离。