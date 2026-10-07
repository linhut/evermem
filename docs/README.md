# 恒忆 Evermem · 文档索引

四类文档，按「你想干什么」选：

| 目录 | 面向 | 内容 |
| --- | --- | --- |
| [`guides/`](#guides--使用与运维) | 使用者、运维 | 怎么装、怎么用、怎么排障、怎么迁移与多机部署 |
| [`design/`](#design--设计与规格) | 想理解系统、想改规则的人 | 架构、备份规格、状态机、记忆提取与保留规则 |
| [`dev/`](#dev--维护与发布) | 维护者与发布者 | 仓库同步范围、发布检查清单、平台总纲、签名与分发 |
| [`ui/`](#ui--界面截图) | 所有人 | 界面设计稿（README 直接引用） |

---

## guides · 使用与运维

| 文档 | 说明 |
| --- | --- |
| [USER-GUIDE.md](guides/USER-GUIDE.md) | **零基础使用说明**：下载哪一个文件、双击没反应 / 被杀软拦截 / 白屏怎么办、首次运行如何设置数据位置、如何更新不丢数据 |
| [USAGE.md](guides/USAGE.md) | 详细使用手册：命令流水线、数据导入、候选审核、备份与分层清理、文件布局 |
| [DESKTOP-MIGRATION.md](guides/DESKTOP-MIGRATION.md) | 数据迁移：从开发环境搬到桌面版（白名单复制、禁止项、校验与回滚） |
| [MULTI-MACHINE.md](guides/MULTI-MACHINE.md) | 多机部署：代码走 Git、数据走备份通道的分工与操作步骤 |
| [PROFILE-EXPORT.md](guides/PROFILE-EXPORT.md) | 使用画像导出：跨工具一致体验的画像格式与覆盖率说明 |

## design · 设计与规格

| 文档 | 说明 |
| --- | --- |
| [ARCHITECTURE.md](design/ARCHITECTURE.md) | 架构设计：分层与模块职责、目录布局、路径解析、宿主集成矩阵、设计取舍 |
| [BACKUP-DESIGN.md](design/BACKUP-DESIGN.md) | 备份与同步设计规格：渠道模型、加密归档、增量与校验 |
| [BACKUP-UX.md](design/BACKUP-UX.md) | 备份模块的交互设计与改动范围 |
| [STATUS-FLOW.md](design/STATUS-FLOW.md) | 记忆生命周期状态流转（staged → active → suspect / superseded / archived） |
| [RETENTION.md](design/RETENTION.md) | 分层清理（T1–T4）：为什么不做定时删除，以及降级、压缩、冷存打包的做法 |
| [DISTILL-RULES.md](design/DISTILL-RULES.md) | 记忆提取规范：一条合格记忆的四个硬指标、三类笔记写法、禁止事项与示例对照 |
| [RECIPES.md](design/RECIPES.md) | 配方治理：四层作用域（core / org / project / session）、求值链与依赖锁 |
| [UPDATE-DESIGN.md](design/UPDATE-DESIGN.md) | 版本管理与自动更新方案：多源竞速、失败必须说人话 |
| [UI-MODULES.md](design/UI-MODULES.md) | 界面模块划分与各页职责 |

## dev · 维护与发布

| 文档 | 说明 |
| --- | --- |
| [REPO-RELEASE-CHECKLIST.md](dev/REPO-RELEASE-CHECKLIST.md) | **提交前必读**：入仓判定规则 R1–R5、忽略规则、三条机械校验、发布检查清单 |
| [PLATFORM.md](dev/PLATFORM.md) | 平台总纲：知识库运营治理（采集 / 萃炼 / 治理 / 检索 / 注入 / 反馈 SOP 与验收指标） |
| [TOOLS.md](dev/TOOLS.md) | 脚本与工具清单：每个脚本的用途与调用方式 |
| [BRAND.md](dev/BRAND.md) | 品牌规范：Logo 体系、配色、字体、各场景用哪一份资产、修改流程 |
| [CODE-SIGNING.md](dev/CODE-SIGNING.md) | 代码签名与分发：SmartScreen / Gatekeeper 绕过指引与证书路径取舍 |
| [DISTRIBUTION-PLAN.md](dev/DISTRIBUTION-PLAN.md) | 分发计划：各平台产物命名与发布流程 |
| [MONTHLY-TEMPLATE.md](dev/MONTHLY-TEMPLATE.md) | 月度回顾模板（每月 1 日执行，填完归档为 `MONTHLY-YYYY-MM.md`） |

## ui · 界面截图

| 文件 | 内容 |
| --- | --- |
| `01-view-browse.png` | 记忆浏览（主界面） |
| `02-view-triage.png` | 候选审核工作台 |
| `03-view-stats.png` | 统计诊断 |
| `04-view-backup.png` | 数据备份 |
| `05-channel-model.png` | 系统架构：本地 → 对象存储 → 百度云 |
| `06-main-view-light-dark.png` | 备份与同步主视图（明亮 / 暗色） |
| `07-wizard-light-dark.png` | 新增渠道向导（明亮 / 暗色） |
| `08-status-matrix-light-dark.png` | 渠道状态矩阵（明亮 / 暗色） |

---

返回 [项目主页](../README.md) · [English README](../README.en.md)
