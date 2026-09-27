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
--dry-run                    # 预览
[--channel <name>]           # 指定渠道执行（默认全部 enabled）
[--restore <name>]           # 从指定渠道恢复（覆盖本地，双重确认提示）
[--scope n,e]                # 覆盖 scope
```
### Web API
```
GET  /api/backup             # 全局状态 + 渠道列表（含每渠道上次/失败/到期）
POST /api/backup/save        # 保存渠道数组 + 全局 auto（body: {channels:[...], auto, alert_email}）
POST /api/backup/run         # 立即执行（body: {channel?: name}，缺省全部 enabled）
POST /api/backup/restore     # 从指定渠道恢复（body: {channel})
POST /api/backup/log         # 最近 N 条备份日志
```
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
     "frequency_hours": 168}
  ]
}
```

## 七、取舍与失败边界

1. **事实源单一化**是本设计的核心取舍：不做双向同步 → 牺牲"多机合并"，换「无冲突」和「可回滚」。多机场景靠频率错开 + 人工节奏。
2. **mail/remote 依赖外部**（SMTP 凭据、ssh 可达），默认 disabled；配置后即生效。SMTP 凭据建议用环境变量（`PMEM_SMTP_PASS`）避免明文入库；pmem_backup.json 本身也在备份范围（meta）——谨慎。
3. **archive 全量快照**随数据增长变大；当前 ~4MB 可接受，量破百 MB 时改差异快照。
4. **告警上限**：日志与 Web 状态是必选告警；邮件告警可选。连续失败告警防轰炸（≥2 次才发、成功即清）。
5. 涉密数据经 mail 渠道需自行评估合规（正文已去敏，快照含笔记全文——仅限内部邮箱）。

---

*实现基准：backup.py v3 + server API + Web「数据备份」渠道管理。与 PLATFORM 治理层"数据走云端备份、代码走 GitHub"一致。*