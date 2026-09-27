#!/usr/bin/env python3
# scan_spaces - 扫描项目/单位目录，生成知识空间地图（只读，不改动任何文件）
#
# Copyright (c) 2026 Jose-AI
# https://www.linhut.cn
# SPDX-License-Identifier: MIT
#
# 用法：
#   python scan_spaces.py F:/                    # 扫描并打印摘要
#   python scan_spaces.py F:/ --json out.json    # 另存为 JSON

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

# 明确排除：系统与软件目录、娱乐、缓存、个人杂项
EXCLUDE_DIRS = {
    "$RECYCLE.BIN", "System Volume Information", "CPM_ENCRYPTED_FOLDER",
    "Game", "WeGameApps", "Wondershare", "Wondershare UniConverter 15",
    "Android", "iso", "hulu", "opgg", "canon", "Anki", "U盘file",
    "PSAutoRecover", "BaiduNetdiskDownload", "Package", "tmp", "tools",
    "master", "1111", "f", "data", "cod", "备份", "WeChat Files",
}

# 文档类扩展名：这些才算"知识载体"
DOC_EXT = {
    ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".pdf",
    ".md", ".txt", ".csv", ".html", ".py", ".json", ".yaml", ".yml",
}

# 明显的噪音文件：Office 锁文件、缩略图
NOISE_PREFIX = ("~$", ".~")


def scan_space(root: Path) -> dict:
    files = 0
    docs = 0
    size = 0
    newest = 0.0
    oldest: float | None = None
    ext_count: dict[str, int] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            if name.startswith(NOISE_PREFIX):
                continue
            path = Path(dirpath) / name
            try:
                st = path.stat()
            except OSError:
                continue
            files += 1
            size += st.st_size
            mtime = st.st_mtime
            newest = max(newest, mtime)
            oldest = mtime if oldest is None else min(oldest, mtime)
            ext = path.suffix.lower()
            if ext in DOC_EXT:
                docs += 1
                ext_count[ext] = ext_count.get(ext, 0) + 1

    top_ext = sorted(ext_count.items(), key=lambda kv: -kv[1])[:5]
    return {
        "name": root.name,
        "path": str(root),
        "files": files,
        "docs": docs,
        "size_mb": round(size / 1048576, 1),
        "top_ext": top_ext,
        "oldest": time.strftime("%Y-%m-%d", time.localtime(oldest)) if oldest else None,
        "newest": time.strftime("%Y-%m-%d", time.localtime(newest)) if newest else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="扫描项目/单位目录，生成知识空间地图")
    ap.add_argument("root", help="要扫描的根目录，例如 F:/")
    ap.add_argument("--min-docs", type=int, default=3, help="文档数少于此值的目录不列入")
    ap.add_argument("--json", dest="json_out", help="另存为 JSON 文件")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"目录不存在：{root}", file=sys.stderr)
        return 1

    spaces = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir():
            continue
        if entry.name in EXCLUDE_DIRS:
            continue
        info = scan_space(entry)
        if info["docs"] >= args.min_docs:
            spaces.append(info)

    spaces.sort(key=lambda s: -s["docs"])

    print(f"扫描根目录：{root}")
    print(f"识别出 {len(spaces)} 个知识空间（文档数 ≥ {args.min_docs}）\n")
    print(f"{'空间':<22}{'文档':>6}{'文件':>8}{'大小MB':>10}  时间跨度")
    print("-" * 68)
    total_docs = 0
    for s in spaces:
        total_docs += s["docs"]
        span = f"{s['oldest'] or '?'} ~ {s['newest'] or '?'}"
        print(f"{s['name'][:20]:<22}{s['docs']:>6}{s['files']:>8}{s['size_mb']:>10}  {span}")
    print("-" * 68)
    print(f"{'合计':<22}{total_docs:>6}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"root": str(root), "spaces": spaces}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(f"\n已保存：{args.json_out}")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
