# 恒忆数据多渠道同步备份设计 v1

> 目标：数据（笔记/事件/索引）不再只依赖单一云端目录，支持**多渠道冗余备份**，并明确
> 各渠道的同步方向、冲突策略、频率、保留周期，以及失败告警与补偿机制。
> 代码与数据分离原则不变：数据只经备份系统进出，不进 Git/GitHub。

---

## 一、同步方向与冲突策略（全局铁律）

- **本地恒忆数据 = 唯一事实源（single source of truth）**。所有渠道都是它的**副本**。
- 默认方向 **upload（单向）**：本地 → 渠道。不做双向同步，**天然无跨渠道冲突**。
- **冲突解决 = 本地优先（local-wins）**：渠道数据永远被本地覆盖；渠道差异（如手动改了云端文件）不作为事实，除非执行 restore。
- **restore（恢复/回滚）**：从某渠道拉取回本地，**覆盖同名文件**，需要**双重确认**（Web 与 CLI 均强制）；恢复后建议 reindex。
- 多写者场景（多台电脑）：每台都 upload，**后上传者覆盖**——这不是平台要解决的冲突（单一写者原则延续：人工负责节奏）。

## 二、渠道模型（适配器抽象）

| 渠道 type | 形态 | 同步方式 | 保留周期 | 依赖 |
|-----------|------|---------|---------|------|
| **local** | 本机可写目录（网盘同步夹/WebDAV/NAS 挂载） | 增量镜像（mtime+size 跳过） | 无（镜像=当前态） | 无（零依赖） |
| **archive** | 本机归档目录（时间点快照） | 每次**全量打包**（zip/tar.gz）到 `snapshots/` | 保留最近 N 份（默认 7，超期删除） | 无（零依赖，zipfile/tarfile 标准库） |
| **remote** | 异地服务器（ssh/scp 可达） | 增量镜像（scp 按文件） | 可选保留 | openssh（`ssh`/`scp` 命令存在） |
| **mail** | 邮箱附件（SMTP 发送） | 每次**全量打包**作附件发送 | 邮件即历史（自留） | smtplib（标准库）+ SMTP 凭据 |
| **s3** | 对象存储（OSS/COS/S3/MinIO/BOS，S3 兼容） | **加密归档包**直传（openssl AES-256 + sha256），云端保留 N 份 | 保留最近 N 份（默认 30） | 零依赖（`s3client.py` 手写 SigV4）；无 openssl 时不可加密 |
| **baidu-pan** | 百度网盘（**冷备 · 人工上传**） | 生成加密归档包 + `UPLOAD.md` 清单，**不自动上传**（官方接口不稳定+违规风险） | 本地保留 N 份（默认 12） | openssl + 人工每周拖入网盘 |

**每个渠道一份配置**（见 §七示例），字段：
`type / name(备注) / enabled / scope(数据范围) / frequency_hours(频率) / direction(默认 upload) / 渠道特有字段 / retention(archive)`

## 三、频率与调度

- 每渠道独立 `frequency_hours`（默认 24）；全局 `auto` 开关控制是否启用定时。
- 调度判定：**距该渠道上次成功时间 >= frequency** 才执行（各自独立，互不阻塞）。
- server 后台线程按 `AUTO_CHECK_SECONDS`（默认 300s）轮询所有 enabled 渠道。
- 手动"立即备份"（Web/CLI）**忽略频率立即执行单渠道或全部**。

## 四、数据范围与增量/全量

- **数据范围**（与现有 scope 一致，每渠道可选）：`notes / events / index / meta`（meta=harvest_state/corpus/kb/knowledge-base/pmem_config）。
- **增量**（local/remote）：与渠道上次同步清单比对，mtime+size 未变且目标端存在 → 跳过。
- **全量**（archive/mail）：每次打当前全量快照（当前数据 ~4MB，zip 后更小；量大后可改差异打包）。
- **校验**：每次同步后对目标端做文件数/大小核对（verify）；不一致 → 记失败+告警。

## 五、失败告警与补偿机制

- **失败判定**：渠道执行异常（目标不可写/ssh 不通/SMTP 失败/verify 不一致）→ 记录该渠道 last_error + 失败时间 + 连续失败次数。
- **补偿**：① 下次轮询到期自动重试（成功即清空失败计数）② Web/CLI「立即备份」随时手动补偿 ③ archive 渠道失败不影响其他渠道（渠道隔离）。
- **告警**：① Web「数据备份」页渠道卡显示失败态（红）+ last_error ② 本地日志 `backup.log`（追加：时间/渠道/结果/错误）③ 可选**邮件告警**：配置 `alert_email`（或 mail 渠道本身）后，连续失败≥2 次时发告警邮件。
- **数据不一致（verify 失败）**：按失败处理并告警；restore 前会再次校验目标完整性。

## 六、接口设计

### CLI（`python backup.py`）
```
status                       # 全渠道状态（目标/范围/自动/上次/失败/历史）
--auto                       # 按频率执行所有到期 enabled 渠道（供计划任务/服务轮询）
--dry-run                    # 预览
[--channel <name>]           # 指定渠道执行（默认全部 enabled）
[--restore <name>]           # 从指定渠道恢复（覆盖本地，双重确认提示）
[--scope n,e]                # 覆盖 scope
```
### Web API
```
GET  /api/backup             # 全局状态 + 渠道投影（涉密字段只回 secret_key_set / archive_password_set 布尔位）
GET  /api/backup/providers   # 渠道契约唯一真源：fields（label/step/required/sensitive/min_len/hint）+ layout（连接参数的字段卡分组）
POST /api/backup/save        # 保存渠道数组 + 全局 auto；「留空=沿用旧值 / 涉密混淆」统一由 backup.from_request 裁决
POST /api/backup/test        # 测试渠道连接（s3: SigV4 探测；baidu-pan: 目录可写）
POST /api/backup/check       # 校验渠道完整性
POST /api/backup/run         # 立即执行（body: {channel?: name}，缺省全部 enabled）
POST /api/backup/restore     # 从指定渠道恢复（body: {channel})
POST /api/backup/log         # 最近 N 条备份日志
```

### 前端分层（web/）
```
index.js     视图装配层：8 个视图的路由，不含任何备份实现
channel.js   渠道模块：渲染 / 交互 / 状态（IIFE 命名空间 BK）
backup.py    领域层：字段契约、from_request（留空保留 + 混淆）、执行
```
三条模块纪律（改动前先对照，防再腐化）：
1. **字段只有一份**：行编辑器与向导的字段、分组、必填、敏感度全部取自 `/api/backup/providers`，`channel.js` 不维护第二份字段表；`layout` 定义「字段卡」分组（Endpoint·区域 / AccessKey ID·Secret 存本机 / Bucket/前缀路径）。
2. **状态只有一处**：`describe(c)` 是设计稿 04 状态矩阵的唯一实现，行徽标、标题计数、图例全部由它推导（图例直接用合成样本调用 describe 生成，口径不可能漂移）。
3. **定位只靠 data-ci**：行用渠道名定位而非 DOM 序号；单渠道操作只提交该渠道（其余沿用上次快照），不再顺带落盘别人未确认的编辑；点击走 `data-bk` 事件委托，杜绝内联 onclick 悬空函数。

### 新增渠道向导（4 步，对应设计稿 03）
```
1 选择渠道类型 → 2 连接参数（s3 显示服务商 chips + 三张字段卡 + 绿色安全提示）
              → 3 加密与策略（渠道名称 / 归档密码≥16 / 频率 / 保留 / 范围）
              → 4 确认并保存（人类可读摘要 + 仅保存 / 保存并立即备份）
```
状态流转闸门：步骤 2 必须点「测试连接」通过后才能进步骤 3；归档密码长度在步骤 3 校验；
服务商 chips 选中态用 `--on-accent`（明亮=白字 / 暗色=近黑字），用户手改过 Endpoint/Region 后切预设不再覆盖。

### 配置（pmem_backup.json）
```json
{
  "auto": true,
  "alert_email": "me@example.com",
  "channels": [
    {"type": "local", "name": "坚果云", "enabled": true, "target": "D:/坚果云/evermem-backup",
     "scope": ["notes","events","index","meta"], "frequency_hours": 24},
    {"type": "archive", "name": "本机快照", "enabled": true, "target": "F:/evermem-snapshots", "retention": 7},
    {"type": "remote", "name": "阿里云服务器", "enabled": false, "target": "user@1.2.3.4:/backup/evermem",
     "ssh_port": 22, "frequency_hours": 48},
    {"type": "mail", "name": "邮箱副本", "enabled": false,
     "target": "backup@example.com", "smtp": {"host": "smtp.example.com", "port": 465, "user": "me@example.com", "pass": "***"},
     "frequency_hours": 168},
    {"type": "s3", "name": "对象存储主副本", "enabled": false,
     "endpoint": "https://oss-cn-hangzhou.aliyuncs.com", "region": "oss-cn-hangzhou",
     "bucket": "evermem-backup", "prefix": "archive",
     "access_key": "AK...", "secret_key": "ob1:...", "archive_password": "ob1:...",
     "frequency_hours": 24, "retention": 30},
    {"type": "baidu-pan", "name": "网盘冷备", "enabled": false,
     "target": "F:/evermem-cold", "archive_password": "ob1:...", "frequency_hours": 168, "retention": 12}
  ]
}
```

### 凭证与密钥（可后填，发布可移植）

- **对象存储凭证**（endpoint/AK/SK）与**归档加密密码**（archive_password）都是**渠道配置项**：创建渠道时可留空，之后在渠道卡内补填保存即可；**保存时留空 = 保留旧值**（不会误清空已存密钥）。
- 凭证以 `backup.obscure` 轻混淆落盘（防明文，非强加密）；`pmem_backup.json` 已在 `.gitignore`，**不进版本库/发布包**。
- **归档密码丢失 = 加密包永久不可解密**（AES-256 无后门），务必另行安全存档（密码库/打印双份）。
- 密码也可走环境变量 `PMEM_ARCHIVE_PASS`（优先于渠道字段），适合服务化部署。

## 八、环境变量一览（部署/发布用）

| 变量 | 作用 | 默认 |
|---|---|---|
| `PMEM_WEB_PORT` | Web 服务端口 | 8765 |
| `PMEM_SYS_PY` | MCP 安装使用的 Python 解释器 | 当前解释器 |
| `PMEM_CHUNKS` / `PMEM_SPACES` | 块库/空间数据根 | 库内 `chunks`/`BASE`（不再写死盘符） |
| `PMEM_ARCHIVE_PASS` | 归档加密密码（全局兜底） | 无（渠道字段优先） |
| `PMEM_OPENSSL` | openssl 可执行文件路径 | PATH → Git 常见安装位 |
| `PMEM_SMTP_PASS` | mail 渠道 SMTP 密码 | 无 |
| `PMEM_S3_ENDPOINT/AK/SK/BUCKET/REGION` | s3client 命令行自测用 | 无 |

> 发布原则：代码不写死机器路径（用户目录/盘符）；数据位置与凭证全部走「环境变量 > 配置文件 > 默认值」，换机器/换用户可直接部署。

## 七、取舍与失败边界

1. **事实源单一化**是本设计的核心取舍：不做双向同步 → 牺牲"多机合并"，换「无冲突」和「可回滚」。多机场景靠频率错开 + 人工节奏。
2. **mail/remote 依赖外部**（SMTP 凭据、ssh 可达），默认 disabled；配置后即生效。SMTP 凭据建议用环境变量（`PMEM_SMTP_PASS`）避免明文入库；pmem_backup.json 本身也在备份范围（meta）——谨慎。
3. **archive 全量快照**随数据增长变大；当前 ~4MB 可接受，量破百 MB 时改差异快照。
4. **告警上限**：日志与 Web 状态是必选告警；邮件告警可选。连续失败告警防轰炸（≥2 次才发、成功即清）。
5. 涉密数据经 mail 渠道需自行评估合规（正文已去敏，快照含笔记全文——仅限内部邮箱）。

---

*实现基准：backup.py v3 + server API + Web「数据备份」渠道管理。与 PLATFORM 治理层"数据走云端备份、代码走 GitHub"一致。*