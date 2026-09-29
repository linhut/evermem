# 数据备份与同步开源方案调研（对象存储 / 百度云）

> 调研日期：2026-09-28　｜　数据口径：GitHub 官方 API 实时拉取（Star / pushed_at / archived / license）
> 场景：恒忆（Evermem）记忆库 —— 本地数据 → 对象存储 → 百度云备份

---

## 0. 结论先行

1. **"百度云"要分清两个东西**：消费级**百度网盘**和**百度智能云 BOS**不是一回事。BOS 是标准 S3 兼容对象存储，可以干净地自动化；百度网盘的第三方开源客户端全部建立在已被官方停用的非官方接口上，**不能进自动化核心链路**。
2. **主力工具选 restic（或 kopia），不选 rclone 单独当备份**——你的数据是 290 个小 Markdown 笔记、长期累积、需要历史版本，去重 + 加密 + 校验 + 快照才是真需求；rclone 只会做"目录镜像"，误删会同步删掉远端。
3. **rclone 的正确角色是"传输层 + 网桥"**：用它把 OSS/COS/S3/MinIO/BOS 统一成一种后端，restic/kopia 可以直接跑在 rclone 后端上。
4. **恒忆当前 `backup.py` 只有 `local / archive / remote / mail` 四类渠道，没有任何对象存储或百度云实现** —— 这是新增功能，不是配置项。

---

## 1. 对比清单

### 1.1 核心工具

| 项目 | GitHub | Star | 最近 push | 归档 | 许可 | 支持的存储类型 |
|---|---|---|---|---|---|---|
| **rclone** | https://github.com/rclone/rclone | **59,959** | 2026-09-26 | 否 | **MIT** | 40+ 后端：AWS S3、阿里云 OSS、腾讯云 COS、MinIO、百度 BOS（走通用 S3）、WebDAV/SFTP/SMB/FTP、本地；**无消费级百度网盘** |
| **restic** | https://github.com/restic/restic | **36,291** | 2026-09-25 | 否 | **BSD-2-Clause** | 本地、SFTP、REST Server、**S3 兼容（OSS/COS/MinIO/BOS 通用后端）**、B2、Azure、GCS、以及把 rclone 当后端桥接 |
| **kopia** | https://github.com/kopia/kopia | **14,208** | 2026-09-27 | 否 | **Apache-2.0** | 本地、S3 兼容、GCS、Azure、B2、SFTP、WebDAV、rclone 桥接 |
| **Duplicati** | https://github.com/duplicati/duplicati | **15,034** | 2026-09-26 | 否 | **NOASSERTION**（LGPL 系变体，非干净 OSI） | S3 兼容、WebDAV、SSH、OneDrive/GDrive、本地 |
| **Duplicacy** | https://github.com/gilbertchen/duplicacy | **5,691** | 2026-08-06 | 否 | **NOASSERTION**（source-available，商业使用需付费授权） | 本地、S3 兼容、SFTP/WebDAV、GDrive |
| **Alist** | https://github.com/AlistGo/alist | **50,231** | 2026-09-19 | 否 | **AGPL-3.0**（传染性） | 聚合层：本地 + **百度网盘** + 阿里云盘 + S3/OSS/COS；对外输出 WebDAV |
| **s5cmd** | https://github.com/peak/s5cmd | **4,200** | 2025-06-13 | 否 | **MIT** | 仅 S3 兼容（并行传输） |
| **minio/minio** | https://github.com/minio/minio | **61,350** | — | **已归档** | **AGPL-3.0** | 自建 S3 兼容对象存储（服务端，非同步工具） |
| **minio/mc** | https://github.com/minio/mc | **3,513** | — | **已归档** | **AGPL-3.0** | S3 客户端（mirror/sync） |

### 1.2 同步能力矩阵

| 项目 | 方向 | 增量 | 断点续传 | 加密 | 定时调度 | 部署方式 |
|---|---|---|---|---|---|---|
| **rclone** | 单向 sync/copy；`bisync` 双向（**标 experimental**） | ✅ 按 size+mtime/hash 跳过 | ✅ 分块传输 + 重试 | ✅ `crypt` 远端（文件名+内容） | ❌ 内建无，靠 cron/systemd；`rcd` 提供 API | CLI / Docker / `rclone rcd` 服务化（含 WebUI） |
| **restic** | 单向（只增快照，非同步） | ✅ 内容定义分块去重，极省 | ⚠️ 无传统断点续传，但中断可安全重跑（快照原子提交） | ✅ AES-256 + 认证，默认开 | ❌ 靠 cron / systemd timer | CLI / Docker / 社区 `rest-server` |
| **kopia** | 单向快照 | ✅ 去重 | ✅ 支持中断续传（upload 会话） | ✅ AES-256 / ChaCha20 | ✅ **内置调度 + retention policy** | CLI / Docker / `kopia server` + Web UI |
| **Duplicati** | 单向备份 | ✅ 去重+压缩 | ⚠️ 大文件场景不稳 | ✅ AES-256 | ✅ 内置调度 | CLI / Docker / 自带 Web UI + Windows 托盘 |
| **Duplicacy** | 单向备份 | ✅ 无锁并发去重 | ✅ | ✅ | ❌（Web 版付费才有） | CLI / Web GUI（付费） |
| **Alist** | 单向拷贝（本质是挂载/代理） | ❌ 无去重 | 部分驱动分片上传 | ❌ 无 | ❌ ❌ 无版本/保留/校验 | Docker / 二进制服务化 + Web UI |
| **s5cmd** | 单向 sync/cp | ✅ | ⚠️ 靠并行重试，非严格续传 | ❌ | ❌ | CLI / Docker |
| **minio/mc** | 单向 mirror | ✅ | 部分 | ❌ | ❌ | CLI / Docker |
| **bypy** | 单向 up/down（仅百度网盘） | ⚠️ 部分 | ❌ | ❌ | ❌ | CLI / Python 包 |
| **BaiduPCS-Go** | 单向（仅百度网盘） | ⚠️ | ❌ **v4.0.0 起接口变更，上传不再支持断点续传** | ❌ | ❌ | CLI / Docker |
| **juicesync** | 单向 | ✅ | ✅ | ❌ | ❌ | CLI（**已归档**） |

### 1.3 已知限制与坑点（重点看这部分）

- **rclone**
  - `bisync` 仍标注 experimental，冲突处理需人工确认，不建议对笔记目录做双向。
  - `crypt` 后文件名也加密 → 无法在对象存储控制台按文件名检索/单独取回一个文件，只能整库恢复。
  - **没有版本历史、没有保留策略**。`sync` 是镜像语义：本地误删 → 下次同步远端也被删。必须配合对象存储的**版本控制 + 生命周期**才有回滚能力。
  - 配置文件明文保存 AK/SK（可用 `rclone config` 加密配置文件或改用环境变量）。
- **restic**
  - **忘记密码 = 数据全丢**，没有后门。密码必须离线另存（建议打印/密码库双份）。
  - 仓库并发写受限：多机同时写同一 repo 需谨慎（`prune` 与 `backup` 并发可能出问题）。
  - `prune` 慢、吃内存（大库可能几个 GB 内存）。
  - 全量恢复要重建整棵快照树，量大时耗时。
- **kopia**
  - 版本间仓库格式偶有迁移；相对 restic 年轻，长周期（5 年+）可恢复性证据少。
  - 内存/CPU 占用高于 restic。
  - 优势很实在：**内置调度 + 保留策略 + Web UI**，少写一堆 cron 脚本。
- **Duplicati**：社区长期反馈**本地索引库易损坏**（频繁需要 "Repair"），大库性能衰减明显，恢复踩坑记录多；且许可不干净（NOASSERTION）。
- **Duplicacy**：CLI 免费但**商业使用需授权**，属于 source-available 而非开源；更新节奏放缓（最近 push 2026-08）。
- **Alist**：定位是"网盘聚合浏览/转 WebDAV"，**它不是备份工具**——没有校验、版本、保留策略、失败重试语义。拿它做备份属于误用。AGPL 有传染性。
- **minio / mc**：**两个仓库均已归档**，作为自建对象存储的生产选型需要重新评估（可考虑 RustFS、Garage 等替代）。自建还要自己扛磁盘可靠性和运维。
- **s5cmd**：只认 S3；最近 push 停在 2025-06，更新放缓；无加密无调度，只适合"大批量搬运"这一件事。

---

## 2. 百度云专题：这是本次调研最大的分叉点

### 2.1 百度网盘（消费级 pan.baidu.com）—— 不建议自动化

| 项目 | GitHub | Star | 最近 push | 许可 | 状态 |
|---|---|---|---|---|---|
| bypy | https://github.com/houtianze/bypy | 8,579 | **2025-04-02** | MIT | ❌ 已一年半未更新 |
| BaiduPCS-Go（活跃分支） | https://github.com/qjfoidnh/BaiduPCS-Go | 5,665 | 2026-09-09 | Apache-2.0 | ⚠️ 上游 iikira 仓库已归档 |
| juicesync | https://github.com/juicedata/juicesync | 599 | 2024-03 | — | ❌ 已归档 |

**为什么劝退：**

1. **官方接口已关**：百度 PCS API（`pcs.baidu.com`）自 2023 年起逐步停用，2024 年基本失效；现行 OpenAPI v2（`pan.baidu.com`）**只对通过审核的开发者开放**，个人自用拿不到稳定授权。
2. **断点续传已退化**：BaiduPCS-Go v4.0.0 更新日志明确写了「因接口变化上传不再支持断点续传」——对一个备份工具来说这是致命的。
3. **合规与封号风险**：第三方高速下载/分享解析属明确违反服务条款的行为，轻限速重封号。你的笔记是**个人长期资产**，不能押在随时会失效的接口上。
4. **Alist 的百度网盘驱动同理**：能挂载能看，但不能当可靠备份终点。

**可以怎么用**：作为**人工、低频的冷归档终点**——每月把加密归档包（一个 .tar.gz + 校验值）手动拖进网盘。这一步不需要任何第三方工具，也不需要自动化。

### 2.2 百度智能云 BOS —— 这才是"百度云备份"的正解

- BOS **原生 S3 兼容**：endpoint `s3.bj.bcebos.com`，SigV4 签名。
- 用法：在 rclone/restic/kopia 里选 **"Any other S3 compatible provider"**，填 endpoint + AK/SK 即可，与 OSS/COS/MinIO **同一套代码路径**。
- 成本参考（2026）：标准存储约 ¥0.12–0.15/GB/月，低频/归档约 ¥0.03–0.04/GB/月，出网流量约 ¥0.5/GB。

> 一句话：**要"百度云"就上 BOS，别上百度网盘。**

---

## 3. 推荐组合

### 组合 A（首选，推荐给恒忆）：restic + 对象存储主副本 + BOS 第二副本

```
本地 .memory/
   │  restic backup（去重 + AES-256 加密 + 校验）
   ▼
[主] 腾讯云 COS / 阿里云 OSS（开版本控制 + 生命周期）
   │  restic copy（仓库级复制，跨云异地）
   ▼
[备] 百度智能云 BOS（S3 通用后端）
   │  （可选，人工）月度加密归档包 → 百度网盘冷备
   ▼
百度网盘（手动，不进自动化）
```

**选型理由**

- 你的数据是 **290 个 Markdown、共 1.2MB** 的小文件集合，会持续增长、且需要"上个月的某个版本"。restic 的**内容分块去重**对这种场景几乎是最优解：每次备份只传改动的那几个块，一年下来仓库增长极小。
- **加密默认开启**——这点对你是硬需求：笔记里有应急管理局/民宗委的工作上下文，明文放公有云不合适。
- **许可干净（BSD-2-Clause）**，可随意集成进恒忆的 Python 后端，无 AGPL/商业授权风险。
- restic 支持把 **rclone 当后端**，所以 OSS/COS/S3/MinIO/BOS 全部不用 restic 单独适配——一个 rclone 配置解决所有云。
- 第二副本放 BOS，实现**跨厂商异地**，避免"主云一个故障全没了"。restic `copy` 是仓库级复制，恢复时直接用第二仓库，不用重新走第一云。
- 定时：Windows 用「任务计划程序」、Linux/macOS 用 systemd timer 或 cron，每天 1–2 次即可；**单一写者**，不要多机并发写同一仓库。

### 组合 B（轻量降级，如果你已有网盘会员 / 嫌 restic 重）：rclone crypt + 对象存储版本控制

```
本地 .memory/  ──rclone sync to crypt:oss──▶  阿里云 OSS（开版本控制 + 生命周期转归档）
                                          └─（可选）BOS 同样一份
百度网盘：每月手动上传一次加密归档包（网页版即可）
```

**选型理由**：一个二进制搞定 OSS/COS/S3/MinIO/BOS，配置成本最低，MIT 许可，59k star 生态最稳。
**代价（必须知道）**：rclone 没有快照概念，回滚能力完全依赖对象存储的**版本控制**；误删同步会扩散到远端，务必加 `--backup-dir` 或用 `copy` 代替 `sync`。

### 不推荐的组合

- ❌ restic/kopia + **百度网盘**（无稳定接口，随时失效）
- ❌ Alist 当备份引擎（无校验/版本/保留）
- ❌ Syncthing 与 restic 混用同一目录（双向同步会与快照语义打架）

---

## 4. 需要你补充的前提（这些不定，选型没法收敛）

| # | 待确认项 | 为什么影响选型 | 我的默认假设 |
|---|---|---|---|
| 1 | **数据是否含涉密/敏感内容** | 涉密材料不能上任何公有云 → 只能走「本地加密归档 + 内网 MinIO/NAS」，公有云只放非敏感子集 | 假设笔记含工作上下文，按**必须先加密再出本机**处理 |
| 2 | **数据量级与增长预期** | 当前 1.2MB / 290 文件（整库 29MB）；若未来放附件、图片、生成的 HTML，量级会跳一个数量级 | 按 <1GB、年增长 <2× 估算，成本可忽略（几分钱/月） |
| 3 | **备份频率 / RPO** | 能容忍丢多久的数据？写入即备份（需钩子）vs 每小时 vs 每日 | 默认**每日 1 次 + 手动触发** |
| 4 | **恢复时效 / RTO 与保留策略** | 需要多久恢复完？要保留多少个历史版本、多久？ | 默认保留 30 天日快照 + 12 个月月快照 |
| 5 | **容灾要求** | 是否需要跨云第二副本？是否接受"只有本地 + 单云"？ | 默认**要第二副本（BOS）** |
| 6 | **数据驻留 / 合规** | 是否必须境内区域？是否有等保/保密要求？ | 默认**境内地域**（广州/上海/北京） |
| 7 | **预算** | 本量级下对象存储费用≈0，成本主要在**出网流量**和你的运维时间 | 默认 <¥20/月可接受 |
| 8 | **信任模型 / 许可偏好** | 是否接受 AGPL（Alist/MinIO）或商业授权（Duplicacy）？ | 默认**只接受 OSI 宽松许可：MIT/BSD/Apache** |
| 9 | **运行环境** | Windows 常开？有 NAS/服务器？是否要保持恒忆"零依赖 Python"的约束？ | 默认 Windows 主力 + 保持零第三方依赖（restic 走外部二进制调用） |
| 10 | **是否要双向同步** | 若"手机/笔记本多端互相同步"是硬需求，需要额外引入 Syncthing，且**不要和 restic 共用目录** | 默认**单向备份**，不做双向 |

> 第 1 条是决定性的：如果涉密，整套方案会从"上云"变成"本地加密归档 + 私有化对象存储"，后面所有选型重来一遍。**请先答这条。**

---

## 5. 落到恒忆的改造点（功能设计的前提）

当前 `backup.py` 的渠道类型只有：

```python
CHANNEL_TYPES = ("local", "archive", "remote", "mail")
```

`check_channel` 目前只支持 `local` / `archive`。要支持本次调研的目标端，需要新增：

| 新增渠道类型 | 承载目标端 | 实现依赖 |
|---|---|---|
| `s3` | AWS S3 / 阿里云 OSS / 腾讯云 COS / MinIO / **百度 BOS** | 优先外部 `rclone` 二进制（零 Python 依赖）；无 rclone 时降级为「仅生成归档包 + 手工上传」 |
| `baidu-pan` | 百度网盘（**冷归档，手工/半自动**） | 不做自动上传；只生成加密归档包 + 校验值 + 上传清单，明确标注"需手动上传" |
| `snapshot` | restic/kopia 仓库（可选） | 外部二进制，管理快照与保留策略 |

设计上建议：**对象存储 = 一等公民（可自动、可测试连接、可定时）；百度网盘 = 二等公民（明确降级态，UI 上标注「冷备份 · 需手动上传」）**。这样既不吹牛，也不把不可靠链路藏起来。

---

## 6. 参考与数据口径

- 所有 Star / pushed_at / archived / license 均来自 GitHub REST API `https://api.github.com/repos/{owner}/{repo}`，拉取时间 2026-09-28。
- rclone 后端列表核对自官方 https://rclone.org（确认**不含**消费级百度网盘；BOS 走 "Any other S3 compatible provider"）。
- 百度网盘接口现状：PCS API 停用、OpenAPI v2 需审核、BaiduPCS-Go v4.0.0 「上传不再支持断点续传」。
- 价格为 2026 年公开刊例价的区间估算，实际以各家官网为准。
