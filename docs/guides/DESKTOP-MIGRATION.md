# 桌面版数据迁移指南（开发环境 → 桌面工具）

> 适用场景：知识数据已在开发环境（源码目录 / 独立数据目录）积累完成，现在要装桌面版单文件包（`Evermem-<平台>-v*`）并继续使用同一批数据。
> 原则：**代码走 Git，数据走白名单复制或备份恢复**；迁移只复制，不移动、不删除源数据。

## 〇、迁移前的两个前提

1. **先确认版本**：本文适用于 v0.2.3 及以后。v0.2.2 及更早的打包产物存在「数据根目录分裂」——核心检索读 `PMEM_HOME`，而配置、导入、备份恢复按代码位置推导，冻结态下会落到临时解包目录。**不要把正式数据导入旧版产物。**
2. **先停写再迁移**：关闭开发服务、桌面版、MCP 桥与会话收割任务，避免迁移过程中两边同时写入。

## 一、数据目录在哪里

| 角色 | 建议位置 | 说明 |
| --- | --- | --- |
| 程序 | `<安装目录>\Evermem\` | 只放 exe / app，不含任何个人数据 |
| 数据 | `<数据盘>\EvermemData\` | `notes/` `events/` 索引与状态文件都在这里 |
| 块库 | `<数据盘>\EvermemData\chunks\` | 文档切块产物，与外部扫描根分离 |

解析优先级（全项目统一，见 `paths.py`）：

```
PMEM_HOME 环境变量  >  数据目录/pmem_config.json 的 home 字段  >  可移植默认目录
```

打包产物的可移植默认目录是**可执行文件同级目录**；显式设置 `PMEM_HOME` 后，双击、托盘、开机自启三种启动方式都会指向同一个数据目录。

## 二、导出（开发环境）

应导出的白名单：

| 内容 | 说明 |
| --- | --- |
| `notes/` | 正式记忆 + 候选记忆（含 `candidates/archive/`） |
| `events/` | 原始证据与导入记录 |
| `index.json` | 可重建，但首迁建议携带，省一次全量重建 |
| `harvest_state.json` | 收割增量状态 |
| `corpus_spaces.json`、`kb.json`、`knowledge-base.md` | 知识库派生数据 |
| 块库目录（如 `chunks/`） | 独立复制；块库不在 `backup.py` 的默认备份范围内 |

**不得进入迁移包：**

| 内容 | 原因 |
| --- | --- |
| `pmem_backup.json` | 含混淆后的 AK/SK、SMTP 凭据、归档密码；换机即失效且属密钥外泄 |
| `.pmem-backup-last.json`、`backup.log` | 同步历史与日志 |
| `pmem_config.json` | 含原机器绝对路径，目标机重新配置 |
| `tools/`、`__pycache__/` | 第三方二进制与编译缓存 |
| `build/`、`dist/`、`*.spec` | 构建产物 |
| `tmp_chk/`、`tmp_ui/` | 临时诊断文件 |
| `*.tar.aes`、`*.sha256` | 历史备份产物 |

PowerShell 示例：

```powershell
$src    = "<开发环境数据目录>"
$export = "<迁移暂存目录>\evermem-data-export"
$items  = @(
  "notes", "events", "index.json", "harvest_state.json",
  "corpus_spaces.json", "kb.json", "knowledge-base.md"
)

New-Item -ItemType Directory -Path $export -Force
foreach ($item in $items) {
  $path = Join-Path $src $item
  if (Test-Path $path) { Copy-Item $path $export -Recurse -Force }
}

Compress-Archive -Path "$export\*" -DestinationPath "$export.zip" -Force
Get-FileHash "$export.zip" -Algorithm SHA256
```

记录下哈希值，目标机解压后比对，确认包在传输中没有损坏。

## 三、导入（桌面工具）

1. 目标数据目录若已有数据，**先整目录复制一份作为回滚点**，不要直接覆盖后删除源目录。
2. 解压迁移包到目标数据目录（保持 `notes/`、`events/` 等同级结构）。
3. 块库单独复制到 `chunks/`。
4. 设置数据位置（二选一）：
   - 环境变量：`setx PMEM_HOME "<数据目录>"`、`setx PMEM_CHUNKS "<块库目录>"`、`setx PMEM_SPACES "<允许扫描的资料根目录>"`
   - 界面：启动桌面版 → 系统 → 接入设置 → ③ 数据位置 → 保存后重启
5. 设置后**必须彻底退出并重新启动桌面版**（环境变量是新进程才读取）。

## 四、校验（不可跳过）

```powershell
$env:PMEM_HOME = "<数据目录>"
& "<Python>" "<源码目录>\mem.py" reindex
& "<Python>" "<源码目录>\mem.py" stats
& "<Python>" "<源码目录>\mem.py" recall "已知能命中的关键词"
```

| 校验项 | 通过标准 |
| --- | --- |
| 正式笔记数 | 与源环境一致（类型 / 状态分布一致） |
| 候选文件数 | `notes/candidates/` 计数一致 |
| 事件文件 | `events/` 文件数与大小基本一致 |
| 关键词召回 | 至少 3 组已知关键词能命中 |
| 界面一致性 | 记忆浏览 / 候选审核 / 统计诊断读到同一数据 |
| 块库 | 能浏览或重新提炼 |
| 写入位置 | 新建一条测试记忆 → 确认落在目标数据目录 → 删除测试记忆 |
| 备份恢复 | 配置渠道后 `--dry-run` 与 `status` 指向目标数据目录 |

## 五、回滚

1. 关闭桌面版。
2. `PMEM_HOME` 改回原目录（或删除该环境变量），或把 `pmem_config.json` 的 `home` 改回原值。
3. 重启桌面版验证。
4. 迁移后的数据先保留，确认稳定后再清理。

回滚不需要删除任何迁移数据，切换数据目录即可。

## 六、常见坑

| 现象 | 原因与处理 |
| --- | --- |
| 界面显示的路径与检索读到的不是同一个 | 旧版产物的数据根目录分裂；升级到 v0.2.3+ |
| 每次启动数据位置都不一样 | 不要把默认目录依赖成当前工作目录；设置 `PMEM_HOME` |
| 恢复「成功」但一个文件都没回来 | local 渠道恢复的本机清单为空；v0.2.3+ 已改为合并枚举 |
| 块库丢失 | 块库不在默认备份范围，需单独复制或扩充备份 scope |
| 开机自启开关点了没反应 | 浏览器模式没有系统自启权限；开关会显示禁用与原因 |
| macOS 勾选开机自启无效 | 旧版误用 Linux XDG 方案；v0.2.3+ 已改用 LaunchAgents |
