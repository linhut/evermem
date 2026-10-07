# 恒忆 Evermem · 架构设计

> 定位：描述**已实现**的系统结构——模块职责、分层约束、目录布局、路径解析与宿主集成。
> 与 `docs/dev/PLATFORM.md` 的分工：本文讲「系统怎么搭起来的」，PLATFORM.md 讲「知识库怎么运营与治理」。

## 一、核心原则

1. **笔记是唯一权威**。索引、缓存、派生文件全部可重建，丢了不心疼。
2. **核心引擎零界面依赖**。引擎与 Web 后端只用 Python 标准库，不 import 任何 Qt；
   命令行能独立跑、单元测试不需要图形环境、将来换界面框架也不用重写引擎。
3. **代码与数据分离**。工具可分发可升级；数据目录用户私有，升级工具不动数据。
4. **本地优先**。不依赖网络、不依赖云端；联网能力（更新检查、云端备份）都是可选增强。
5. **失败不碍事**。检索失败、收割失败、备份失败都不应影响用户正常使用——但也**不得静默**，
   必须给出可读原因。

## 二、分层

| 层 | 位置 | 职责 | 第三方依赖 |
| --- | --- | --- | --- |
| 核心引擎 | `mem.py`、`harvest.py`、`memimport.py`、`recipes.py`、`backup.py`、`s3client.py`、`update.py` | 笔记读写与检索、会话收割、外部导入、配方治理、多渠道备份、更新检查 | 无 |
| 路径与配置 | `paths.py` | **代码目录 / 数据目录的唯一解析入口**，全项目不得各自按 `__file__` 推导 | 无 |
| 集成层 | `evermem_mcp.py`（MCP stdio）、`templates/*.md`（技能与提示词）、`web/server.py` 的接入设置接口 | 把引擎接进各 AI 宿主 | 无 |
| 界面层 | `web/`（零依赖 HTTP + 原生 JS）、`desktop.py`（可选桌面外壳） | 浏览、审核、导入、备份、设置、更新 | Web 无；桌面壳需 PySide6 + QtWebEngine |
| 打包分发 | `installers/`、`.github/workflows/`、`assets/`、`brand/` | 三平台构建产物与品牌资源 | PyInstaller |

**关键约束**：核心引擎与 Web 后端绝不 import Qt。桌面壳是**可拆卸外壳**——删掉 `desktop.py`，
CLI 与 Web 界面照常工作。

## 三、目录结构

仓库（仓库根 = 项目根，可分发）：

```
.
├── paths.py            代码目录 / 数据目录唯一解析入口
├── mem.py              CLI 引擎：recall / add / show / set-status / gc / hot / candidates / reindex / stats
├── harvest.py          会话收割（命令级 + 任务级），无需任何钩子
├── memimport.py        外部记忆导入（画像 / Markdown / JSON / 目录）
├── recipes.py          配方治理（四层作用域 / 求值链 / 依赖锁）
├── backup.py           多渠道备份（对象存储 / SMTP / 本地镜像 / 全量快照 / 加密归档）
├── s3client.py         零依赖 S3 兼容客户端（手写 SigV4）
├── update.py           多源更新检查（自建清单 → GitHub 直连 → 镜像竞速）
├── evermem_mcp.py      MCP 服务（标准 stdio，4 个工具）
├── desktop.py          桌面壳（内嵌 Web 服务 + QtWebEngine，可选）
├── web/                零依赖 Web 界面：server.py + index.html/index.js/i18n.js/channel.js
├── templates/          技能与提示词模板（唯一事实源，安装到宿主时复制出去）
├── scripts/            开发与运维工具（自检 / 冒烟 / 基准 / 图标 / 知识扫描 / 会话导入）
├── tests/              回归测试（标准库 unittest）
├── installers/         安装器脚本与向导图（Inno Setup 等）
├── assets/             打包用应用图标三件套（icon.ico / icon.icns / icon.png）
├── brand/              品牌源（SVG）与多尺寸 PNG；运行时经 `/brand/` 路由提供
├── docs/               文档：design（设计）/ guides（使用与运维）/ dev（维护与发布）
└── .github/            CI 工作流与社区健康文件
```

数据目录（用户私有，**永不进 Git**，只经加密通道备份）：

```
<数据目录>/
├── pmem_config.json                本机配置（数据位置、块库、扫描根）
├── notes/{procedures,lessons,facts}/  正式笔记（唯一权威）
├── notes/candidates/               自动收割候选（staged）
├── events/                         证据流水，只追加
├── index.json                      派生索引，可幂等重建
├── chunks/                         文档导入的文本块库
└── updates/                        更新包暂存
```

## 四、跨平台

| 事项 | 处理 |
| --- | --- |
| 路径 | 一律 `pathlib`，禁止字符串拼接分隔符 |
| 数据目录 | `PMEM_HOME` > 数据目录 `pmem_config.json` 的 `home` > 安装版系统数据区 > 可执行文件/脚本同级目录 |
| 盘符与挂载点 | **不写死任何盘符**：Windows 动态枚举已挂载盘符，macOS/Linux 用 `/`、`/Volumes`、`/media`、`/mnt` |
| Python 解释器 | `sys.executable` 或 `PMEM_SYS_PY`，禁止写死绝对路径 |
| 外部工具 | openssl / node 一律 PATH 探测 + 环境变量可覆盖，安装位由 `%ProgramFiles%`、`%LOCALAPPDATA%` 推导 |
| 编码 | 读写一律显式 `utf-8` |
| 打包 | PyInstaller **不能交叉编译**，必须三平台各建一次（CI 矩阵） |
| macOS 分发 | 未签名会被 Gatekeeper 拦截，正式分发需开发者账号 |
| Linux 分发 | 绿色版 tar.gz / deb / AppImage，最省事 |
| Windows 细节 | 设置 AppUserModelID，否则任务栏图标异常 |

打包态路径是真实坑：PyInstaller 产物里 `__file__` 指向临时解包目录（`sys._MEIPASS`），
所以数据位置**绝不能**由 `__file__` 推导——这正是 `paths.py` 单独存在的理由。

## 五、宿主集成能力矩阵

| 宿主 | 钩子 | 自动捕获 | 恒忆使用的通道 |
| --- | --- | --- | --- |
| WorkBuddy | 产品禁用第三方插件钩子 | 靠收割 | 技能 + MCP |
| Claude Code | 完整（注入/改写/阻断三级） | 支持 | 技能 + MCP（钩子为可选增强） |
| DSH (DeepSeek Harness) | 插件事件 | 支持 | 技能（目录被监视，热刷新） |
| Codex | 无 | 不支持 | 写 `AGENTS.md` + MCP 配置 |
| Marvis（腾讯马维斯） | 未见公开钩子 | 靠收割 | 技能（`~/.marvis/skills/custom/`） |

> 恒忆**不依赖任何宿主钩子**——收割直接读会话落盘记录。钩子缺失只会少一层实时性，不影响能力成立。

## 六、界面

Web 界面为单页应用，零依赖实现（`web/server.py` 提供 HTTP API 与静态资源，前端为原生 JS）：

- `web/server.py`：路由 + API + 各业务处理器（含原子写与并发守卫）
- `web/index.js`：视图渲染与交互
- `web/i18n.js`：中英双语文案（新增文案必须成对登记，禁止硬编码）
- `web/channel.js`：备份渠道的表单/向导渲染

一级模块共 9 个：记忆浏览 / 候选审核 / 数据导入 / 核心经验 / 统计诊断 / 接入设置 / 数据与维护 /
数据备份 / 版本与更新。明亮与暗色主题为对等实现。

桌面壳 `desktop.py` 不重复实现界面，只做三件事：内嵌启动 `web/server.py`、用 QtWebEngine 承载同一页面、
提供单实例与托盘常驻。

## 七、设计取舍（已知限制）

| 取舍 | 理由 | 代价 |
| --- | --- | --- |
| 索引用 JSON 而非 SQLite | 可幂等重建、零依赖、可读可 diff | 规模上限较低，全量重建耗时随条目线性增长 |
| 不依赖宿主钩子 | 桌面端会禁用第三方插件钩子，绑钩子等于把能力交给别人的开关 | 收割依赖会话落盘，存在延迟 |
| 界面用 Web 而非原生 Qt | 一套代码跨三平台，零依赖，改样式不用重编译 | 首屏依赖本地 HTTP 服务；窗口由外壳承载 |
| 自动抽取不直接入库 | 未经评审的经验进正式库会污染检索 | 需要人工/多角色评审环节 |
| 不做自动删除 | 漏掉一条关键经验的代价远高于多存几 MB | 需要分层降级与冷存打包来控体积 |
