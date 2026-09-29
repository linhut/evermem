# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# 检索与热层的回归测试（零依赖，直接运行）
#
#
#     python tests/test_recall.py
#
# 改动 mem.py 的检索逻辑或热层挑选规则后都应跑一遍。

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mem  # noqa: E402

FAILURES = []

def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILURES.append(name)

def main() -> int:
    idx = mem.load_index(force=True)
    docs = idx.get("docs", {})

    print(f"索引：{len(docs)} 条笔记，{len(idx.get('postings', {}))} 个词项\n")

    print("[1] 相关查询必须命中，且最相关排第一")
    hits = mem.search(idx, "gongwen python interpreter", limit=3)
    check("有命中", len(hits) > 0)
    if hits:
        check("首位是解释器那条", "python" in hits[0]["title"].lower(),
              f"实际首位：{hits[0]['title']}")

    print("\n[2] 中文查询可用（2/3-gram 分词）")
    zh = mem.search(idx, "插件钩子为什么不执行", limit=3)
    check("中文有命中", len(zh) > 0)

    print("\n[2b] 不存在的内容必须无命中（防误召回回归）")
    noise = mem.search(idx, "完全不存在的关键词xyzqwerty", limit=3)
    check("噪声词无命中", len(noise) == 0, f"实际命中 {len(noise)} 条：{[h['title'][:12] for h in noise]}")

    print("\n[3] 默认只返回 active，不含 staged 候选")
    check("结果全为 active", all(h["status"] == "active" for h in hits + zh))

    print("\n[4] staged 候选可用 --all 查到")
    allhits = mem.search(idx, "命令签名 失败", limit=20, include_all=True)
    staged = [h for h in allhits if h["status"] == "staged"]
    tmp_path = None
    if staged:
        check("--all 含 staged", True)
    else:
        # 库中无 staged 时自建临时夹具验证，测完删除，保证任意数据状态下可执行
        import time as _t
        nid = _t.strftime("%Y%m%d-%H%M%S") + "-fixture"
        tmp_path = mem.NOTES / "lessons" / f"fixture-{nid}.md"
        tmp_path.write_text(
            f"---\nid: {nid}\ntype: lesson\nstatus: staged\ntitle: 临时夹具 staged 检索验证\n"
            "created: 2026-09-27\n---\n\n正文：命令签名 失败的临时夹具，验证 include_all 行为。\n",
            encoding="utf-8")
        idx = mem.build_index()
        try:
            h2 = mem.search(idx, "临时夹具 staged 检索验证", limit=5, include_all=True)
            check("--all 能查到 staged（临时夹具）", any(x["status"] == "staged" for x in h2))
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
                mem.build_index()

    print("\n[5] 热层默认只取人工标记（hot: true）")
    hot, _skipped_auto = mem.select_hot(idx, limit=12)
    check("热层非空", len(hot) > 0)
    check("热层全为人工标记", all(pinned for _, _, pinned in hot),
          f"实际：{[(d['title'], p) for _, d, p in hot][:3]}")

    print("\n[6] 索引可从笔记幂等重建")
    rebuilt = mem.build_index()
    check("重建笔记数一致", rebuilt["doc_count"] == len(docs),
          f"{rebuilt['doc_count']} vs {len(docs)}")

    print()
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项：{FAILURES}")
        return 1
    print("全部通过。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
