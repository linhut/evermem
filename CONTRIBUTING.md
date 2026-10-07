# 贡献指南 · Contributing

感谢愿意为恒忆（Evermem）出一份力。本文说明提交约定与质量门槛；中英文均可，中文优先。

> 项目定位：个人跨会话经验记忆系统，**零第三方依赖 · 全本地 · 无云端**。
> 提交前请先读 [docs/dev/REPO-RELEASE-CHECKLIST.md](docs/dev/REPO-RELEASE-CHECKLIST.md)（入仓判定规则与发布清单）。

---

## 一、最受欢迎的四类贡献

| 类型 | 说明 |
| --- | --- |
| **问题报告** | 装了跑不起来、界面报错、数据不一致——请附上复现步骤与错误原文 |
| **平台适配** | 在 macOS / Linux 上的实测反馈（本项目主要在 Windows 上开发，跨平台问题最需要真实环境验证） |
| **宿主接入** | 新的 AI 宿主（工具）如何接入恒忆技能 / MCP 的可行路径 |
| **文档纠错** | 文档与代码不一致、步骤缺失、路径过期——这类问题优先级很高 |

## 二、开发环境

```bash
git clone https://github.com/linhut/evermem.git
cd evermem

python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements-build.txt           # 仅打包需要；运行本体零依赖

python web/server.py                            # Web 界面，默认 http://127.0.0.1:8765
python mem.py --help                            # 命令行引擎
```

**零依赖是硬约束**：核心引擎与 Web 后端只能用 Python 标准库。
新增第三方依赖的 PR 会被要求改为标准库实现，或移入仅打包期使用的 `requirements-build.txt`。

## 三、提交规范（中英双语）

标题格式：`type(scope): English summary — 中文摘要`

```
feat(web): add keyboard shortcuts — 界面新增键盘快捷键
fix(harvest): skip empty session files — 收割跳过空会话文件
docs(readme): clarify data root resolution — README 澄清数据目录解析顺序
chore(repo): renormalize line endings — 统一换行符
```

`type` 取值：`feat` / `fix` / `docs` / `refactor` / `perf` / `test` / `chore` / `build` / `ci` / `release`。

重要变更请在正文分中、英各写一段说明；修复类提交请写清**现象 → 真因 → 修法**。

## 四、质量门槛（提交前必须全部通过）

```bash
python -m py_compile mem.py harvest.py backup.py paths.py web/server.py
node --check web/index.js && node --check web/channel.js && node --check web/i18n.js
python scripts/frontend_smoke.py               # 前端静态契约冒烟
python -m unittest discover -s tests           # 回归测试
python scripts/check_all.py                    # 完整自检（会启本地服务，沙箱环境需放宽网络限制）
```

> `check_all.py` 会绑定本地端口做 API 自检；若在受限沙箱里运行，需要允许本地端口绑定，否则属于**环境导致的假失败**。

## 五、纪律（重要）

1. **绝不提交任何记忆数据**。`notes/`、`events/`、`index.json`、`pmem_config.json`、`pmem_backup.json` 一律不入库（`.gitignore` 已覆盖，仍需自查）。
2. **绝不写死本机路径**。盘符（`C:/`、`D:/`）、用户目录、解释器绝对路径都不许出现在代码或文档里；路径一律走 `paths.py`。
3. **绝不写死密钥**。凭证全部走配置项或环境变量。
4. **去敏**：文档示例里的单位、人名、项目名一律用占位符（`某单位`、`某负责人`、`org:gov-a`）。
5. **新功能要同步文档**：README 与 CHANGELOG 必须一起更新。
6. **界面文案要双语**：新增中文字符串必须在 `web/i18n.js` 成对登记英文，禁止硬编码。

## 六、提交前自查

```bash
git status                 # 只含预期变更
git ls-files               # 无个人数据、无凭证、无构建产物、无临时目录
git grep -nE "[A-Za-z]:[\\/]" -- . | grep -v https   # 应无本机盘符
```

## 七、行为准则

参与本项目即表示同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 八、许可

贡献的代码将以 [MIT License](LICENSE) 发布。提交 PR 即表示你同意这一授权。
