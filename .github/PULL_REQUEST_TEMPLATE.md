## 这个 PR 做了什么

<!-- 一到三句话说清改动与动机。关联 Issue 用 "Closes #123"。 -->

Closes #

## 改动类型

- [ ] `feat` 新功能
- [ ] `fix` 缺陷修复
- [ ] `docs` 文档
- [ ] `refactor` / `perf` 重构或性能
- [ ] `test` 测试
- [ ] `chore` / `build` / `ci` 杂项、构建与流水线

## 自查清单

- [ ] 提交标题符合双语规范：`type(scope): English summary — 中文摘要`
- [ ] 已实际跑过改动路径（不是"看起来对"）
- [ ] `python -m unittest discover -s tests` 通过
- [ ] `python scripts/frontend_smoke.py` 通过（若改动前端）
- [ ] 改动涉及界面文案时，已在 `web/i18n.js` 成对补上英文
- [ ] 已同步更新 README / CHANGELOG 与相关文档

## 纪律自查（重要）

- [ ] **没有**提交任何记忆数据（`notes/`、`events/`、`index.json`、`pmem_config.json`、`pmem_backup.json`）
- [ ] **没有**写死本机盘符或用户目录（`C:/`、`/Users/xxx` 等），路径一律走 `paths.py`
- [ ] **没有**写死任何密钥、令牌、邮箱
- [ ] 文档与示例里的单位名、人名、项目名已用占位符（`某单位`、`某负责人`、`org:gov-a`）

## 验证方式

<!-- 你用什么方式证明它真的生效了？命令、截图、输出片段都行。 -->

## 需要 reviewer 关注的点

<!-- 有取舍、有不确定、有已知限制的地方，写在这里。 -->
