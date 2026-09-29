# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# 恒忆 Evermem 检索基准回归（验证假设 A2：BM25 在语料增长后质量可用）
# 用法：python bench_search.py                # 跑并输出摘要
#       python bench_search.py --save         # 保存基线 JSON（docs/bench-search-baseline-<date>.json）
# 200 条语料时复跑，与基线对比 top1 分数与预期命中率，判断检索是否退化。

import json
import sys
import time
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]  # 项目根（scripts/ 上一级），勿写死机器路径
RESULT_DIR = BASE / "docs"

# 标准查询集：(查询词, 预期命中标题关键词) —— 覆盖各领域/类型
QUERIES = [
    ("工作提示函 督办 整改", "工作提示函"),
    ("会议通知 写作 复盘", "会议"),
    ("复函 答复 平级单位", "复函"),
    ("系统上云 部署 方案", "上云"),
    ("机房 设备搬迁 方案 编制", "机房"),
    ("可行性研究报告 编制 模板", "可研"),
    ("统一认证 接入 政务", "统一认证"),
    ("弱电 需求 指挥中心", "弱电"),
    ("监理 规划 细则 文档", "监理"),
    ("应急通信 装备 配置 乡村", "应急通信"),
    ("无线电台 备案 频率", "无线电台"),
    ("MCP 安装 宿主 配置", "MCP"),
    ("会话 收割 记忆 候选", "收割"),
    ("钩子 禁用 桌面端", "钩子"),
    ("密码 应用方案 密评", "密码"),
    ("政府采购 单一来源 文件", "采购"),
    ("责任状 任务 承诺", "责任状"),
    ("机房整合 核查 纳管", "机房整合"),
    ("设备台账 字段 整理", "台账"),
    ("导则 建设规范 编制", "导则"),
]

def main() -> int:
    import mem  # noqa: E402

    idx = mem.load_index(force=True)
    total = len(idx.get("docs", {}))
    hits_stats = []
    for q, expect in QUERIES:
        t0 = time.perf_counter()
        hits = mem.search(idx, q, limit=5)
        ms = (time.perf_counter() - t0) * 1000
        top = hits[0] if hits else None
        hit_expected = any(expect in h["title"] for h in hits)
        hits_stats.append({
            "query": q, "expect": expect,
            "top_id": top["id"] if top else None,
            "top_score": round(top["score"], 1) if top else 0.0,
            "top_title": top["title"][:40] if top else "(无命中)",
            "hit_expected": hit_expected,
            "n": len(hits), "ms": round(ms, 0),
        })

    n_q = len(hits_stats)
    n_hit = sum(1 for r in hits_stats if r["hit_expected"])
    n_empty = sum(1 for r in hits_stats if r["n"] == 0)
    avg_top = sum(r["top_score"] for r in hits_stats) / n_q

    print(f"检索基准（{date.today()}，语料 {total} 条，查询 {n_q} 组）")
    print("-" * 78)
    for r in hits_stats:
        flag = "✓" if r["hit_expected"] else "✗"
        print(f"{flag} top1 {r['top_score']:7.1f} | {r['query']:<22} | 预期[{r['expect']}] 命中{r['n']}条 | {r['top_title']}")
    print("-" * 78)
    print(f"预期命中率 {n_hit}/{n_q} ({n_hit / n_q * 100:.0f}%) | 无命中 {n_empty} | 平均 top1 分数 {avg_top:.1f}")

    if "--save" in sys.argv:
        RESULT_DIR.mkdir(exist_ok=True)
        out = RESULT_DIR / f"bench-search-baseline-{date.today():%Y%m%d}.json"
        out.write_text(json.dumps({
            "date": str(date.today()), "total_notes": total, "queries": n_q,
            "hit_rate": n_hit / n_q, "empty": n_empty, "avg_top_score": round(avg_top, 1),
            "details": hits_stats,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"基线已保存 → {out}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
