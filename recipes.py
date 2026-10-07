#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recipes.py — 恒忆配方管理工具（零依赖，标准库 only）。

子命令：
  scan              盘点配方：分层统计、同命名空间同名检测(P0)、疑似隐式覆盖(P1)
  resolve <scope>   求值顺序：给定当前项目 scope，输出生效配方优先级链
  lock              生成 .recipe-lock.json：锁定所有被 depends 引用的配方快照

用法示例：
  python recipes.py scan
  python recipes.py resolve project:evermem
  python recipes.py lock

规范见 docs/design/RECIPES.md。不改动 mem.py 核心；索引重建照常走 mem.py reindex。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import sys as _sys
if str(Path(__file__).resolve().parent) not in _sys.path:
    _sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths as _paths  # noqa: E402

# 数据目录与 mem.py 同源（env > 持久化配置 > 可移植默认），避免配方扫描扫错目录。
ROOT = _paths.data_root()
NOTES = ROOT / "notes"
LOCK = ROOT / ".recipe-lock.json"

LAYER_ORDER = {"session": 0, "project": 1, "org": 2, "core": 3}
LAYER_NAMES = {"session": "L3 会话层", "project": "L2 项目层", "org": "L1 组织层", "core": "L0 核心层"}

ID_RE = re.compile(r"^([a-z]+:[a-z0-9_-]+)/([a-z0-9_-]+)@(\d+\.\d+\.\d+)$")


def parse_note(path: Path) -> dict | None:
    """解析 frontmatter（宽容模式，未知字段忽略）。独立实现，不依赖 mem.py。"""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    except UnicodeDecodeError:
        # 并发写入留下的半成品文件：按"读不到"处理，调用方跳过即可。
        return None
    meta: dict = {}
    body = raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end > 0:
            head = raw[3:end]
            body = raw[end + 4:].lstrip("\n")
            for line in head.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    v = v.strip()
                    if v.startswith("[") and v.endswith("]"):
                        v = [x.strip().strip('"\'') for x in v[1:-1].split(",") if x.strip()]
                    meta[k.strip()] = v
    nid = str(meta.get("id", path.stem))
    scope = str(meta.get("scope", "")).strip()
    layer = "project"
    if scope:
        layer = scope.split(":", 1)[0]
    if layer not in LAYER_ORDER:
        layer = "project"
    def _int(v, dflt=50):
        try:
            return int(v)
        except (TypeError, ValueError):
            return dflt
    return {
        "id": nid,
        "name": nid.rsplit("/", 1)[-1].split("@", 1)[0] if "/" in nid else path.stem,
        "type": str(meta.get("type", "fact")),
        "status": str(meta.get("status", "active")),
        "title": str(meta.get("title", path.stem)),
        "scope": scope,
        "layer": layer,
        "priority": _int(meta.get("priority")),
        "depends": meta.get("depends", []) if isinstance(meta.get("depends"), list) else [],
        "overrides": meta.get("overrides", []) if isinstance(meta.get("overrides"), list) else [],
        "version": str(meta.get("version", "")),
        "env": str(meta.get("env", "")),
        "created": str(meta.get("created", "")),
        "path": str(path),
    }


def iter_recipes():
    if not NOTES.exists():
        return []
    out = []
    for p in sorted(NOTES.rglob("*.md")):
        if "/candidates/" in p.as_posix():
            continue
        n = parse_note(p)
        if n:
            out.append(n)
    return out


def _norm_title(t: str) -> str:
    return re.sub(r"[\s、，,：:（）()/\\\-_]+", "", t).lower()


def cmd_scan(args) -> int:
    notes = iter_recipes()
    if not notes:
        print("未发现任何配方笔记（notes/ 为空？）")
        return 1
    by_layer: dict[str, list] = {}
    for n in notes:
        by_layer.setdefault(n["layer"], []).append(n)

    print(f"配方盘点：共 {len(notes)} 条\n")
    for layer in ["core", "org", "project", "session"]:
        lst = by_layer.get(layer, [])
        scoped = [n for n in lst if n["scope"]]
        active = [n for n in lst if n["status"] == "active"]
        print(f"  {LAYER_NAMES[layer]:<10} {len(lst):>3} 条  |  已标 scope {len(scoped)}  |  active {len(active)}")

    problems = 0
    p0 = []
    by_key: dict[str, list] = {}
    for n in notes:
        if n["scope"] and n["name"]:
            by_key.setdefault(f"{n['scope']}/{n['name']}", []).append(n)
    for key, lst in by_key.items():
        if len(lst) > 1:
            p0.append((key, lst))

    if p0:
        print("\n[P0] 同命名空间同名冲突（自动拒装目标）：")
        for key, lst in p0:
            print(f"  {key}")
            for n in lst:
                print(f"    - {n['id']}  {n['title']}  [{n['status']}] {n['path']}")
            problems += 1

    p1 = []
    seen: dict[str, list] = {}
    for n in notes:
        if n["status"] != "active":
            continue
        seen.setdefault(_norm_title(n["title"]), []).append(n)
    for key, lst in seen.items():
        if len(lst) > 1:
            scopes = {n["scope"] for n in lst}
            overrides = {n["id"] for n in lst for _ in n["overrides"]}
            # 同 title 多条且 scope 不同 → 疑似隐式覆盖（除非某条显式 overrides 了另一条）
            if len(scopes) > 1:
                unpaired = [n for n in lst if n["id"] not in overrides]
                if unpaired:
                    p1.append((key, lst))

    if p1:
        print("\n[P1] 疑似隐式覆盖（同用途不同 scope，无 overrides 声明）：")
        for key, lst in p1:
            print(f"  标题：{key}")
            for n in lst:
                print(f"    - {n['id']}  scope={n['scope'] or '(未标)'}  [{n['status']}]")
            problems += 1

    unscoped = [n for n in notes if not n["scope"]]
    if unscoped:
        print(f"\n提示：{len(unscoped)} 条未标 scope（默认归 L2 项目层）。抽查：")
        for n in unscoped[:5]:
            print(f"    {n['id']}  {n['title']}")
    if not problems:
        print("\n未发现命名冲突与隐式覆盖，配方分层干净。")
    print(f"\n结论：P0={len(p0)}  P1={len(p1)}")
    return 1 if p0 else 0


def cmd_resolve(args) -> int:
    notes = iter_recipes()
    targets = [s for s in args.scope if ":" in s]
    if not targets:
        print("用法：resolve <scope>...，首个为主 scope，其后可附归属组织，如 resolve project:evermem org:yjxt", file=sys.stderr)
        return 2
    main_scope = targets[0]
    org_scopes = {s for s in targets[1:] if s.startswith("org:")}
    tlayer = main_scope.split(":", 1)[0]
    t_order = LAYER_ORDER.get(tlayer, 1)

    candidates = []
    for n in notes:
        if n["status"] != "active":
            continue
        slayer = n["layer"]
        if slayer == "session":
            continue  # 会话层不被正式引用
        if LAYER_ORDER.get(slayer, 1) < t_order:
            continue  # 引用只许向上：不得引用更下层
        if LAYER_ORDER.get(slayer, 1) == t_order:
            # 同层仅匹配主 scope（未标 scope 的默认归本项目）。
            # 原写法 slayer == t_order 是字符串与整数比较恒 False，同层其他项目配方漏进求值链。
            if n["scope"] and n["scope"] != main_scope:
                continue
        elif slayer == "org":
            # 组织层：显式归属的组织空间或通用 org:common 才对当前项目生效
            if not (n["scope"] in org_scopes or n["scope"] == "org:common"):
                continue
        dist = LAYER_ORDER[slayer] - t_order  # 同层0 / 组织1 / 核心2，就近优先
        candidates.append((n, dist))

    # 就近优先（距离小者先），同层按 priority 升序
    candidates.sort(key=lambda it: (it[1], it[0]["priority"], it[0]["id"]))

    print(f"求值顺序（主 scope {main_scope}，归属组织 {sorted(org_scopes) or '无'}，active 配方，就近优先）：\n")
    for n, dist in candidates:
        ov = f"  overrides→{','.join(n['overrides'])}" if n["overrides"] else ""
        ver = f"  v{n['version']}" if n["version"] else ""
        tier_mark = "  ← 共享层（可被项目覆盖）" if dist else ""
        print(f"  [{LAYER_NAMES[n['layer']]}] p{n['priority']:>3}  {n['id']}{ver}{ov}{tier_mark}")
        print(f"        {n['title']}")
    return 0


def cmd_lock(args) -> int:
    notes = iter_recipes()
    if getattr(args, "project", None):
        # 与文档 RECIPES.md 对齐：lock --project <name> 只锁该项目作用域
        want = f"project:{args.project}"
        notes = [n for n in notes if (n.get("scope") or "") == want
                 or (n.get("scope") or "").startswith(want + ":")]
    deps: dict[str, dict] = {}
    for n in notes:
        if n["status"] != "active":
            continue
        for d in n["depends"]:
            if d not in deps:
                target = next((x for x in notes if x["id"] == d), None)
                deps[d] = {
                    "locked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": target["status"] if target else "missing",
                    "version": target["version"] if target else "",
                    "consumers": [],
                }
            deps[d]["consumers"].append(n["id"])
    if not deps:
        print("当前无配方声明 depends，锁文件为空（可留空文件供后续追加）。")
        _atomic_write(LOCK, json.dumps({"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "deps": {}}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {LOCK}")
        return 0
    payload = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "deps": deps}
    _atomic_write(LOCK, json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已锁定 {len(deps)} 个依赖 → {LOCK}")
    for d, info in deps.items():
        flag = "[缺失]" if info["status"] == "missing" else ""
        print(f"  {d}  v{info['version'] or '?'}  {info['status']}{flag}  被 {len(info['consumers'])} 个配方引用")
    return 0


def _atomic_write(path, text: str, encoding: str = "utf-8") -> None:
    """原子写：tmp + os.replace，避免并发/中断留下截断锁文件。"""
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    try:
        tmp.write_text(text, encoding=encoding)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(prog="recipes", description="恒忆配方管理（规范见 docs/design/RECIPES.md）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan", help="盘点配方分层与冲突")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("resolve", help="求值顺序解析")
    p.add_argument("scope", nargs="+", help="主 scope 在前，可附归属组织，如 resolve project:evermem org:yjxt")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("lock", help="生成依赖锁文件 .recipe-lock.json")
    p.add_argument("--project", default=None,
                   help="只锁指定项目（scope 前缀 project:<name> 或 <name>）；不给则锁全部 active 配方")
    p.set_defaults(func=cmd_lock)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
