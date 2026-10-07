# 恒忆条目状态流转关系与规则（STATUS-FLOW）

> 统一解释「候选 / 记忆 / 内容 / 存档 / 转正 / 存疑 / 归档 / 替代」这些词的关系，
> 以及每种状态的进入条件、可执行操作、下一流转去向。

## 一、先分清「状态」与「操作」与「概念」

| 词 | 性质 | 含义 |
|---|---|---|
| 内容 | 概念（属性） | 笔记正文 body，不是状态 |
| 候选 | 状态（staged）+ 位置 | 自动收割产物，位于 `notes/candidates/`，未经验证 |
| 记忆 | 状态（active）+ 位置 | 正式库 `notes/{procedures,lessons,facts}/`，正常使用 |
| 存疑 | 状态（suspect） | 被质疑、默认检索隐藏 |
| 已替代 | 状态（superseded） | 被新笔记取代、保留历史、默认检索隐藏 |
| 存档 | 位置（archive 目录） | `notes/candidates/archive/`，退出活跃的候选 |
| 转正 | 操作 | 候选 → 记忆（staged→active + 移动到正式目录） |
| 存疑 | 操作 | 任意笔记 → suspect |
| 归档 | 操作 | 候选 → 存档目录（退出活跃） |
| 替代 | 操作 | 正式笔记 → superseded（被新笔记取代） |

## 二、状态机（4 个 status × 位置）

```
自动收割 → 候选(candidates/ , staged)
              ├─【转正】→ 记忆(正式目录 , active)
              ├─【存疑】→ 存疑(suspect，默认隐藏)
              ├─【归档】→ 存档(candidates/archive/)
              └─ 超期(>60天未动) → 存档(自动)
记忆(active)
              ├─【编辑】→ 仍是 active
              ├─【进热层】→ 仍是 active（hot:true）
              ├─【存疑】→ suspect
              └─【替代】→ superseded（保留原位，默认隐藏）
存疑(suspect)
              ├─【转正】→ active
              └─【归档】→ 存档
已替代(superseded)
              └─【转正/恢复】→ active（可回滚）
存档(archive/)   → 只读证据，不再流转
```

## 三、每种状态明细

| 状态 | 进入条件 | 可执行操作 | 下一去向 |
|------|---------|-----------|---------|
| **候选 staged** | 自动收割（harvest scan）产出 | 转正 / 存疑 / 归档 / 多角色评审 | active / suspect / archive |
| **记忆 active** | 转正；人工 add；AI 提炼 | 编辑 / 进热层 / 存疑 / 替代 | suspect / superseded |
| **存疑 suspect** | 使用中发现错误；人工标存疑 | 转正 / 归档 | active / archive |
| **已替代 superseded** | 被新笔记替代（写前治理确认） | 恢复（转正） | active |
| **存档 archive** | 候选归档 / 超期自动归档 | 只读（证据保留） | — |

## 四、关键规则（铁律）

1. **自动产物只进候选**，绝不直接 active（信噪比优先）。
2. **转正 = 移动目录 + status→active**（候选从 candidates/ 移到正式 type 目录）。
3. **superseded 不删除**，留在正式目录原位，默认检索隐藏（历史可回溯）。
4. **归档 ≠ 替代**：归档是"候选退出活跃（进 archive/）"；替代是"正式笔记被新笔记取代（superseded）"。两者语义不同。
5. **多角色自动转正仅限 lesson 踩坑类**；procedure 成功配方碎片不自动转正，留人工。
6. 候选超期（>60 天未动）自动归档；候选池容量上限 50。

## 五、已修正的历史不一致

- 浏览页操作栏的「归档」按钮曾错误映射到 `status: superseded`（已替代）——语义错乱，已改名「替代」，动作不变（superseded）。
- 候选池与正式库的状态此前割裂（suspect 可同时存在于两处）——本状态机统一：候选池只承担 staged→(转正/存疑/归档) 的前置流转，正式库承担 active/suspect/superseded 的长期流转。
