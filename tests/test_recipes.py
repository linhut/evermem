# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# 配方管理（recipes.py）回归测试（零依赖，直接运行）
#
#     python tests/test_recipes.py
#
# 改动 recipes.py 的解析 / 分层 / 求值 / 锁逻辑后都应跑一遍。

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recipes  # noqa: E402

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILURES.append(name)


def main() -> int:
    print("一、frontmatter 解析（宽容 + 分层推断）")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f1 = tmp / "n1.md"
        f1.write_text(
            "---\nid: core:gongwen/qc@1.0.0\ntype: procedure\nstatus: active\n"
            "title: 质检\nscope: core:gongwen\npriority: 50\ndepends: [core:base@~1.0]\nversion: 1.0.0\n"
            "---\n\n正文\n", encoding="utf-8")
        n = recipes.parse_note(f1)
        check("解析 core 配方", n is not None and n["layer"] == "core" and n["version"] == "1.0.0"
              and n["depends"] == ["core:base@~1.0"], f"n={n}")

        f2 = tmp / "n2.md"
        f2.write_text("---\nid: 20260101-0000-001\ntype: lesson\nstatus: active\ntitle: 无 scope\n---\n\n正文\n",
                      encoding="utf-8")
        n2 = recipes.parse_note(f2)
        check("无 scope 默认项目层", n2 is not None and n2["layer"] == "project" and n2["scope"] == "",
              f"n2={n2}")

        f3 = tmp / "n3.md"
        f3.write_text("普通文本无 frontmatter\n", encoding="utf-8")
        n3 = recipes.parse_note(f3)
        check("无 frontmatter 也能解析（宽容）", n3 is not None and n3["status"] == "active", f"n3={n3}")

    print("二、scan（对当前真实库，只读）")
    notes = recipes.iter_recipes()
    check("iter_recipes 非空", len(notes) > 0, "notes 为空？")
    by_key: dict = {}
    p0 = 0
    for n in notes:
        if n["scope"] and n["name"]:
            by_key.setdefault(f"{n['scope']}/{n['name']}", []).append(n)
    for lst in by_key.values():
        if len(lst) > 1:
            p0 += 1
    check("无同命名空间同名冲突（P0=0）", p0 == 0, f"P0={p0}")

    print("三、resolve（就近优先 + 归属组织门控）")
    class A:
        pass
    a = A()
    a.scope = ["project:evermem", "org:yjxt"]
    _captured = []
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = recipes.cmd_resolve(a)
    out = buf.getvalue()
    check("resolve 正常退出", rc == 0)
    check("归属 org:yjxt 时组织配方生效", "org:yjxt" in out or "应急通信装备" in out, out[:200])
    check("core 配方进入求值链", "core:gongwen" in out or "质量检查清单" in out, out[:200])
    check("就近优先标注共享层", "共享层" in out, out[:200])

    a2 = A()
    a2.scope = ["project:games"]
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = recipes.cmd_resolve(a2)
    out2 = buf2.getvalue()
    check("未归属组织时 org:yjxt 不生效", "org:yjxt" not in out2 and "应急通信装备" not in out2, out2[:200])
    check("无归属仍含 core 基线", "core:gongwen" in out2 or "质量检查清单" in out2, out2[:200])

    print("四、lock（生成/空依赖两态）")
    class B:
        pass
    b = B()
    buf3 = io.StringIO()
    with contextlib.redirect_stdout(buf3):
        rc3 = recipes.cmd_lock(b)
    check("lock 正常退出", rc3 == 0)
    lock_path = recipes.ROOT / ".recipe-lock.json"
    check("锁文件已生成", lock_path.exists(), str(lock_path))
    import json
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    check("锁文件结构合法", "deps" in data and "generated_at" in data, str(data)[:120])

    print()
    if FAILURES:
        print(f"共 {len(FAILURES)} 项失败：{FAILURES}")
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
