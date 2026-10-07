# 恒忆多机同步演练指南（MULTI-MACHINE）

> 场景：第二台电脑加入（家里/单位/同事实例），目标是"代码可更新、数据可迁移"。
> 原则：**代码走 Git，数据走 backup.py 云端**——双轨分离，与本项目 A8 边界一致。

## 一、总览

| 资产 | 同步通道 | 方向 |
|------|---------|------|
| 代码（.memory 引擎/Web/MCP/文档） | GitHub 私人仓库 `linhut/evermem`（origin） | 拉取/推送 |
| 数据（notes/events/索引/状态） | `backup.py` 云端目录（你的网盘/NAS 挂载点） | 本机→云端；恢复=云端→本机 |
| 个人文件/工作日志（.workbuddy、项目根） | 不进 Git、不走 backup（保持在原机或按需复制） | — |

## 二、新机器加入步骤（演练清单）

1. **准备**：安装 Python（≥3.10）、git；挂载同一网盘/NAS（得到与主机的 backup 云端目录）。
2. **拉代码**：
   ```bash
   git clone https://github.com/linhut/evermem.git
   cd evermem/.memory
   pip install -r requirements.txt   # 若引擎需要额外依赖（当前零依赖）
   ```
3. **拉数据（从云端恢复）**：
   ```bash
   python backup.py status              # 确认云端目录可读
   python backup.py --restore           # 云端 → 本地（覆盖同名）
   python mem.py reindex                # 恢复后重建索引
   python mem.py stats                  # 校验 71 条笔记等
   ```
4. **启动**：`python web/server.py`，浏览器开 `http://127.0.0.1:8765` 验证记忆浏览/候选/备份页。
5. **建立增量习惯**：新机器上的自动收割/评审/备份照常运行；`backup.py` 增量同步自动跳过未变文件。

## 三、冲突处理（诚实预期）

- 两台机器都可能产生笔记/候选 → 各自 upload 到云端的**同一同步目录**。
- **规则：最后上传者覆盖**（人工负责写节奏）；笔记 id 含时间戳，一般不会同 id 冲突。
- 若真冲突（同名同 id 不同内容）：以 check 比较后人工择一，`git` 只管代码不影响数据。
- **免责**：当前为"单写者 + 手动节奏"模型，未实现自动合并/冲突裁决（P2 待评估）；多机并发写入同一数据集的**自动合并能力尚不支持**，正式稳定前请勿两台同时高频写入。

## 四、验证清单（演练验收）

- [ ] `mem.py stats` 笔记数与主机一致
- [ ] `mem.py recall "任意主机上的经验"` 能命中
- [ ] Web 9 个一级模块均可打开、无 JS 报错（`scripts/frontend_smoke.py` 通过）
- [ ] 新机 `backup.py` 能增量同步回云端（主机可看到新机新增）
- [ ] `git pull` 能更新代码且不触碰数据（.gitignore 隔离生效）

## 五、频率建议

- 代码：改动即 `git push`；新机 `git pull`。
- 数据：主用机每日自动备份；低频机每周 `backup.py`。
- 月度回顾（MONTHLY-TEMPLATE）在两台间以主用机为准，另一台只读。