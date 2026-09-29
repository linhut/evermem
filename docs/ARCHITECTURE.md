# pmem 目标架构设计

参考项目：ReMe（本地优先、Markdown + BM25 + wikilink）、Vault-Agent-Memory（分层与 trust 字段）、dsh-memoir（生命周期与治理）、BoxMark（PySide6 分层与打包实践）、agentmemory（完整捕获链路）。

## 一、核心原则

1. **笔记是唯一权威**。索引、缓存、派生文件全部可重建，丢了不心疼。
2. **核心逻辑零界面依赖**。`core/` 不引用任何 Qt 组件，CLI 与 GUI 共用它，可单独测试。
3. **工具与数据分离**。工具代码可分发可升级；数据目录用户私有，不随工具走。升级工具不动数据。
4. **本地优先**。不依赖网络、不依赖云端，联网能力最多是可选增强。
5. **失败时不碍事**。检索失败、收割失败都不应影响用户正常工作。

## 二、分层

| 层 | 目录 | 职责 | 依赖界面 |
|---|---|---|---|
| 核心 | `core/` | 笔记读写、索引检索、收割、热层、宿主适配 | 否 |
| 命令行 | `cli.py` | 给 agent 调用 | 否 |
| 界面 | `ui/` | 给人用（PySide6） | 是 |
| 基础设施 | `platform/` | 路径解析（开发/打包双模式）、配置、日志 | 部分 |
| 打包 | `packaging/` | PyInstaller 脚本与产物 | 否 |

关键约束：**`core/` 绝不 import Qt**。这样命令行能独立跑、单元测试不需要 Qt 环境、将来换界面框架也不用重写引擎。

## 三、目录结构

工具仓库（可分发）：

```
pmem/
├── pmem/
│   ├── core/
│   │   ├── config.py        数据目录解析：PMEM_HOME > 默认 ~/.pmem
│   │   ├── notes.py         笔记读写与 frontmatter 解析
│   │   ├── index.py         索引与 BM25 检索
│   │   ├── harvest.py       会话收割（无需钩子）
│   │   ├── hot.py           热层挑选与同步
│   │   └── adapters/        各宿主适配：claude / codex / dsh / workbuddy
│   ├── cli.py
│   ├── ui/
│   │   ├── main_window.py
│   │   ├── views/           笔记、候选审核、热层、设置、统计
│   │   ├── styles/theme.py  明暗主题
│   │   └── workers.py       QThread 异步任务，避免界面卡顿
│   ├── platform/paths.py    开发态与打包态路径解析
│   └── resources/
├── tests/                   pytest + pytest-qt
├── packaging/               PyInstaller spec 与构建脚本
└── .github/workflows/       三平台矩阵构建
```

数据目录（用户私有，可进 Git）：

```
<数据目录>/
├── config.toml
├── notes/{facts,lessons,procedures,candidates}/
├── events/                  证据流水，只追加
├── index.*                  索引，本地生成，不同步
└── state.json               收割进度，不同步
```

## 四、跨平台

| 事项 | 处理 |
|---|---|
| 路径 | 一律 pathlib，禁止字符串拼接分隔符 |
| 数据目录 | `~/.pmem`（各平台家目录下），可用 `PMEM_HOME` 覆盖 |
| Python 解释器 | `sys.executable`，禁止写死绝对路径 |
| 编码 | 读写一律显式 utf-8 |
| 打包 | PyInstaller **不能交叉编译**，必须三平台各建一次 |
| macOS 分发 | 未签名会被 Gatekeeper 拦截，正式分发需开发者账号 |
| Linux 分发 | AppImage 最省事，免安装 |
| Windows 细节 | 设置 AppUserModelID，否则任务栏图标异常 |

打包态路径是真实坑：PyInstaller 打出的程序里 `__file__` 与源码态不同，需通过 `sys._MEIPASS` 区分，`platform/paths.py` 专门处理这件事。

## 五、界面设计

布局：左侧列表（含搜索与类型筛选）、右侧编辑区（标题、正文、元数据）、顶部工具栏。

原则：

1. **键盘优先**：`Ctrl/Cmd+K` 搜索、`↑↓` 切换、`Ctrl/Cmd+N` 新建、`Ctrl/Cmd+S` 保存。
2. **即时搜索**：输入即过滤，不等回车（本地检索毫秒级）。
3. **状态可见**：active / staged / suspect / superseded 用颜色标签；热层用实心标记。
4. **批量审核**：候选可多选，批量通过或丢弃；每条必须能看到证据（命令、失败输出、来源会话）。
5. **编辑区尊重 Markdown**：等宽字体、语法着色，不做富文本转换。
6. **不打断**：自动保存，删除才确认。
7. **明暗主题**：随系统或手动切换。

工程规范（PySide6）：

- 显式 import，禁止 `from PySide6.QtWidgets import *`
- 用 QLayout 布局，避免绝对定位
- 组件间用 Signal / Slot 通信
- 耗时任务（检索、收割、索引重建）走 QThread，绝不阻塞界面
- 所有子控件设 parent
- 函数带类型注解

平台适配：快捷键映射（macOS 用 Cmd）、字体栈、菜单位置。

## 六、宿主能力矩阵

| 宿主 | 钩子 | 自动捕获 | 说明 |
|---|---|---|---|
| Claude Code | 完整 | 支持 | hooks 写 settings.json，支持注入/改写/阻断三级 |
| DSH | 插件 | 支持 | 回合结束事件可用于自动归纳 |
| Codex | 无 | 不支持 | 只能写 AGENTS.md 加 MCP 配置 |
| WorkBuddy | 产品禁用 | 靠收割 | 钩子被硬编码关闭；收割落盘记录是唯一自动路径 |

## 七、分期

| 阶段 | 内容 | 依赖 |
|---|---|---|
| M1 | 跨平台改造：清硬编码、数据目录可配、宿主探测通用 | 无 |
| M2 | 最小窗口：笔记列表 + 搜索 + 编辑 | M1 |
| M3 | 候选审核 + 热层管理 | M2 |
| M4 | 设置 + 宿主注入 + 打包单平台 | M3 |
| M5 | 三平台 CI 与分发 | M4 |

## 八、风险

- **核心循环尚未验证**：界面做得再完整，若日常不使用则投入沉没。建议 M2 之后先用一段时间再继续。
- 打包体积：PySide6 打包后 80–120 MB。
- macOS 签名成本：正式分发需付费账号。
- 宿主配置格式会随版本变化，适配器需持续跟进。
