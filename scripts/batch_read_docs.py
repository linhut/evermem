# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# 批量读取测试赛每日运行报告（.doc，通过 editor_sdk），提取关键单元格。
import json
import subprocess
import os
import sys
from pathlib import Path

# 环境专用工具脚本：机器路径一律走环境变量/参数，勿硬编码（发布约定）
#   PMEM_EDSDK    指向 tencent-local-office-edit/edsdk.py 的完整路径
#   PMEM_DOC_DIR  数据目录（或命令行第一个参数）
EDSDK = os.environ.get("PMEM_EDSDK") or ""
BASE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ.get("PMEM_DOC_DIR", "."))
if not EDSDK or not Path(EDSDK).exists():
    raise SystemExit("缺少 edsdk.py：请设置环境变量 PMEM_EDSDK 指向 tencent-local-office-edit/edsdk.py")

def run(args):
    r = subprocess.run([sys.executable, EDSDK, *args], capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return r.stdout

def get_texts(full_path: str):
    """打开 .doc 并读表格关键单元格（日期/概要/遗留问题）。"""
    fid = None
    out = run(["call", "open_file", f"file_path={full_path}"])
    if "started" not in out:
        return None, f"open失败: {out[:120]}"
    # open_file 的 file_id 就是路径本身（后台 fresh open）
    fid = full_path
    res = run(["call", "doc_get_table_info", f"file_id={fid}", "idx=0"])
    try:
        d = json.loads(res)
    except json.JSONDecodeError:
        return fid, f"解析失败: {res[:120]}"
    try:
        cells = d["block"]["table"]["cells"]
    except (KeyError, TypeError):
        return fid, f"结构异常: {res[:150]}"
    # 收集非空、非表头文本，按行组织
    rows: dict[int, list[str]] = {}
    for c in cells:
        t = (c.get("text") or "").strip()
        if not t:
            continue
        if t in ("报告日期", "联系人", "联系方式", "业务领域", "填报人（目前）："):
            continue
        rows.setdefault(c["row"], []).append(t)
    texts = []
    for rn in sorted(rows):
        texts.append(f"[行{rn}] " + " / ".join(rows[rn]))
    return fid, "\n".join(texts)

def main():
    files = sorted(BASE.glob("项目场馆*每日运行报告*"))
    print(f"共 {len(files)} 份运行报告\n")
    for f in files:
        fid, text = get_texts(str(f))
        if fid is None:
            print(f"### {f.name}\n失败: {text}\n")
            continue
        # 提取日期
        date = "?"
        for line in text.splitlines():
            if "9月" in line and "日" in line:
                date = line.split("9月")[1].split("日")[0]
                break
        print(f"### {f.name[:20]}...（9月{date}日）")
        print(text[:1600])
        print()
        # 释放后台实例
        run(["call", "close_file", f"file_id={fid}"])

if __name__ == "__main__":
    main()
