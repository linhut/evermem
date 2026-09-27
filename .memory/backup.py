#!/usr/bin/env python3
# pmem backup - 恒忆数据备份/同步（零依赖）
#
# Copyright (c) 2026 Jose-AI
# https://www.linhut.cn
# SPDX-License-Identifier: MIT
#
# 职责：把恒忆的【数据/知识】（notes/events/索引等）增量同步到"自定义云端位置"。
# 代码与数据分离：代码走 GitHub 仓库，数据绝不进版本库，只经本脚本备份。
#
# 目标位置配置（任选其一，云端优先）：
#   1) 环境变量 PMEM_BACKUP_TARGET="<本机可写的云端目录>"（网盘同步夹/WebDAV 挂载/NAS 挂载等）
#   2) 配置文件 pmem_backup.json：{"target": "<本机可写的云端目录>"}
# 用法：
#   python backup.py status              # 数据规模 + 目标状态 + 上次备份
#   python backup.py --dry-run           # 预览将同步/跳过的文件
#   python backup.py                     # 执行增量同步（按 mtime+size 跳过未变）
#   python backup.py --restore "<路径>"  # 从目标目录恢复到本地（覆盖同名，谨慎）

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / "pmem_backup.json"
MANIFEST = ".pmem-backup-last.json"

# 数据清单：云备份只含数据/知识，不含代码
DATA_PATHS = [
    "notes", "events", "index.json", "harvest_state.json",
    "corpus_spaces.json", "kb.json", "knowledge-base.md", "pmem_config.json",
]


def load_target() -> tuple[str, str]:
    cfg = {}
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    t = (cfg.get("target") or os.environ.get("PMEM_BACKUP_TARGET") or "").strip()
    return t, (cfg.get("note") or "")


def data_items() -> list[Path]:
    out = []
    for name in DATA_PATHS:
        p = BASE / name
        if p.exists():
            out.append(p)
    return out


def collect(src: Path, rel: str, items: list[dict]) -> None:
    if src.is_file():
        st = src.stat()
        items.append({"rel": rel, "mtime": st.st_mtime, "size": st.st_size})
    else:
        for f in sorted(src.rglob("*")):
            if f.is_file() and not f.name.startswith(".pmem-backup"):
                st = f.stat()
                items.append({"rel": str(Path(rel) / f.relative_to(src)), "mtime": st.st_mtime, "size": st.st_size})


def total_size(items: list[dict]) -> int:
    return sum(i["size"] for i in items)


def main() -> int:
    target, note = load_target()
    items: list[dict] = []
    for src in data_items():
        collect(src, src.name, items)
    total = total_size(items)

    if not target:
        print("⚠️  未配置备份目标。请任选一种：")
        print("   1) 设置环境变量 PMEM_BACKUP_TARGET=<云端目录>（网盘同步夹/WebDAV/NAS 本地挂载）")
        print(f"   2) 编辑 {CONFIG_FILE.name}：{{\"target\": \"<云端目录>\"}}")
        print("提示：先在本机登录/挂载你的云盘（如坚果云、OneDrive、NAS），把挂载路径填进来。")
        return 1

    dst = Path(target)
    if not dst.exists():
        if "status" in sys.argv or "--dry-run" in sys.argv:
            print(f"目标目录尚未创建：{target}（首次执行备份时会自动创建）")
            return 0 if "--dry-run" in sys.argv else 1
        dst.mkdir(parents=True, exist_ok=True)
    if not dst.is_dir() or not os.access(dst.parent, os.W_OK):
        print(f"⚠️  目标不可写：{target}（请确认云盘已挂载/已登录）")
        return 1

    last = {}
    mf = BASE / MANIFEST
    try:
        last = json.loads(mf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    lst = last.get("items", [])
    last_map = {i["rel"]: i for i in lst}

    if "--dry-run" in sys.argv:
        print(f"备份目标：{target}")
        if note:
            print(f"备注：{note}")
        print(f"数据规模：{len(items)} 个文件，{total/1024/1024:.2f} MB；上次备份：{last.get('at','-')}")
        todo, skip = 0, 0
        for i in items:
            old = last_map.get(i["rel"])
            if old and old["mtime"] == i["mtime"] and old["size"] == i["size"]:
                skip += 1
            else:
                todo += 1
                print(f"  → {i['rel']}")
        print(f"\n将同步 {todo} 个，跳过未变 {skip} 个。")
        return 0

    if "status" in sys.argv:
        mounted = os.access(dst, os.W_OK)
        print(f"目标：{target}（可写：{'是' if mounted else '否'}）")
        if note:
            print(f"备注：{note}")
        print(f"数据：{len(items)} 个文件 / {total/1024/1024:.2f} MB")
        print(f"上次备份：{last.get('at', '-')}（{mf.name}）")
        return 0

    # 执行增量同步
    t0 = time.time()
    todo = 0
    copied = 0
    for i in items:
        rel = i["rel"]
        old = last_map.get(rel)
        if old and old["mtime"] == i["mtime"] and old["size"] == i["size"]:
            continue
        src_p = BASE / rel
        dst_p = dst / rel
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_p, dst_p)
        todo += 1
        copied += i["size"]
    mf.write_text(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "items": items},
                             ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 同步完成：{todo} 个文件，{copied/1024/1024:.2f} MB → {target}")
    print(f"清单已写入 {mf.name}（本地记录，便于下次增量；清单本身请不要上传）")
    if "--restore" in sys.argv:
        pass  # 恢复功能独立入口，见下方
    return 0


def restore() -> int:
    target, _ = load_target()
    if not target or not Path(target).is_dir():
        print("未配置有效备份目标，无法恢复。")
        return 1
    src = Path(target)
    for name in DATA_PATHS:
        p = src / name
        if p.exists():
            d = BASE / name
            if p.is_dir():
                d.mkdir(parents=True, exist_ok=True)
                for f in p.rglob("*"):
                    if f.is_file():
                        rel = f.relative_to(p)
                        out = d / rel
                        out.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, out)
            else:
                shutil.copy2(p, d)
            print(f"  恢复 {name}")
    print("恢复完成（覆盖同名文件）。建议随后 mem.py reindex。")
    return 0


if __name__ == "__main__":
    if "--restore" in sys.argv:
        sys.exit(restore())
    sys.exit(main())