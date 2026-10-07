#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# 恒忆 Evermem · MCP 注入桥（DSH / WorkBuddy / Claude 通用）
#
# 参考 dsh-memoir 的工具设计（memoir_read/record/update），但数据层完全
# 复用本地恒忆（mem.py + notes/），零依赖、全本地、无云端。
#
# 协议：MCP over stdio（JSON-RPC 2.0），符合 MCP 规范，任何支持
# stdio MCP 的宿主（DeepSeek Harness / Claude / WorkBuddy…）均可接入。
#

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 数据目录走唯一解析入口（env > 持久化配置 > 可移植默认），
# 与 mem.py / server.py / backup.py 同源，避免 MCP 写入另一个目录。
import sys as _sys
if str(Path(__file__).resolve().parent) not in _sys.path:
    _sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths as _paths  # noqa: E402

BASE = _paths.data_root()
CODE_BASE = _paths.code_root()
if str(CODE_BASE) not in sys.path:
    sys.path.insert(0, str(CODE_BASE))

import mem  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "evermem"
# 与项目 VERSION 对齐（此前写死 0.1.0，宿主排障会被误导）；打包态需保证 VERSION 随资源分发
try:
    _ver = (_paths.code_root() / "VERSION").read_text(encoding="utf-8").strip()
    SERVER_VERSION = _ver or "0.1.0"
except OSError:
    SERVER_VERSION = "0.1.0"

TYPE_OPTIONS = ["procedure", "lesson", "fact"]

# 进程内索引缓存（MCP 常驻后大幅提速：按 index.json mtime 失效）
_idx_cache: dict = {"mtime": -1.0, "idx": None}

def cached_index() -> dict:
    """缓存索引：force=False 走 mem.py 的"笔记 mtime > 索引 mtime 自动重建"，
    重建后 index.json mtime 更新 → 本缓存随之失效，外部写笔记自动反映。"""
    try:
        m = mem.INDEX_PATH.stat().st_mtime
    except OSError:
        return mem.build_index()
    if _idx_cache["mtime"] != m:
        _idx_cache["idx"] = mem.load_index(force=False)
        _idx_cache["mtime"] = m
    return _idx_cache["idx"]

# ---------- 工具实现 ----------
def tool_read(query: str, limit: int = 8, include_all: bool = False) -> dict:
    """检索记忆（对标 memoir_read）。"""
    if not query or not query.strip():
        return {"error": "query 必填", "hits": []}
    idx = cached_index()
    hits = mem.search(idx, query, limit=max(1, min(limit, 30)), include_all=include_all)
    return {
        "hits": [{"id": h["id"], "score": h["score"], "title": h["title"],
                  "type": h["type"], "status": h["status"], "snippet": h["snippet"]} for h in hits],
        "query": query,
    }

def tool_record(title: str, body: str = "", note_type: str = "lesson",
                status: str = "staged", tags: str = "", supersedes: list | None = None) -> dict:
    """写入记忆（对标 memoir_record + 写前相似治理）。默认 staged，需人工转正。"""
    import time
    if not title.strip():
        return {"ok": False, "error": "title 必填"}
    if note_type not in TYPE_OPTIONS:
        return {"ok": False, "error": f"type 必须是 {TYPE_OPTIONS}"}

    # —— 写前相似治理（借鉴 dsh-memoir needs-resolution）：用标题检索疑似重复/冲突 ——
    idx = cached_index()
    cands = mem.search(idx, title, limit=5, include_all=True)
    similar = [{"id": c["id"], "title": c["title"], "score": c["score"],
                "status": c["status"]} for c in cands if c["score"] >= 18.0]

    nid = time.strftime("%Y%m%d-%H%M%S") + "-mcp"
    tag_list = [f'"{t.strip()}"' for t in tags.split(",") if t.strip()]
    tag_field = "[" + ", ".join(tag_list) + "]" if tag_list else "[自动, 待验证]"
    sup_ids = supersedes or []
    sup_field = ("[" + ", ".join(f'"{s}"' for s in sup_ids) + "]") if sup_ids else "[]"
    note = (f"---\nid: {nid}\ntype: {note_type}\nstatus: {status}\ntitle: {title}\n"
            f"tags: {tag_field}\nsupersedes: {sup_field}\ncreated: {time.strftime('%Y-%m-%d')}\n---\n\n{body.strip()}\n")
    out_dir = BASE / "notes" / "lessons" if note_type == "lesson" else BASE / "notes" / note_type
    out_dir.mkdir(parents=True, exist_ok=True)
    fp = out_dir / f"mcp-{nid}.md"
    mem.atomic_write(fp, note)  # 原子写：服务端界面会并发读同一目录

    # 替代：把被替代的旧笔记标记 superseded
    if sup_ids:
        import re as _re
        old = mem.load_index(force=True)
        for sid in sup_ids:
            d = old.get("docs", {}).get(sid)
            if d and d.get("path"):
                p = Path(d["path"])
                try:
                    raw = p.read_text(encoding="utf-8")
                    if _re.search(r"^status:\s*\S+", raw, _re.M):
                        raw = _re.sub(r"^status:\s*\S+", "status: superseded", raw, count=1, flags=_re.M)
                    else:
                        raw = raw.replace("---\n", "---\nstatus: superseded\n", 1)
                    mem.atomic_write(p, raw)
                except OSError:
                    pass
    mem.build_index()
    return {"ok": True, "id": nid, "status": status, "path": str(fp),
            "similar": similar, "needs_resolution": bool(similar),
            "hint": "存在疑似重复/冲突的候选：可改用 mem_update 更新旧记录、或带 supersedes 参数确认替代。" if similar else ""}

def tool_update(note_id: str, status: str | None = None, hot: bool | None = None) -> dict:
    """更新记忆生命周期（对标 memoir_update）。"""
    idx = cached_index()
    d = idx.get("docs", {}).get(note_id)
    if not d or not d.get("path"):
        return {"ok": False, "error": f"未找到 {note_id}"}
    path = Path(d["path"])
    import re
    raw = path.read_text(encoding="utf-8")
    if status and status in ("active", "staged", "suspect", "superseded"):
        if re.search(r"^status:\s*\S+", raw, re.M):
            raw = re.sub(r"^status:\s*\S+", f"status: {status}", raw, count=1, flags=re.M)
        else:
            raw = raw.replace("---\n", f"---\nstatus: {status}\n", 1)
    if hot is not None:
        if hot:
            if not re.search(r"^hot:\s*", raw, re.M):
                raw = raw.replace("---\n", "---\nhot: true\n", 1)
            else:
                raw = re.sub(r"^hot:\s*\S+", "hot: true", raw, count=1, flags=re.M)
        else:
            raw = re.sub(r"^hot:\s*(true|1|yes)\s*\n", "", raw, flags=re.M)
    mem.atomic_write(path, raw)  # 原子写：状态更新不能留下半成品被界面读到
    mem.build_index()
    return {"ok": True, "id": note_id, "status": status or d.get("status"), "hot": hot if hot is not None else bool(d.get("hot"))}
def tool_hot(limit: int = 20) -> dict:
    """返回当前热层（对标 dsh-memoir 的 Hot Memory 预览）。"""
    idx = cached_index()
    # 热层保护：自动收割转正的条目默认不进热层（未经人工确认），与 mem.py hot 同一标准
    picks, _skipped = mem.select_hot(idx, limit=max(1, min(limit, 20)), include_auto=False)
    return {"hot": [{"id": d["id"], "title": d["title"], "type": d["type"],
                     "status": d["status"], "pinned": p} for _, d, p in picks],
            "count": len(picks), "limit": min(limit, 20)}

TOOLS = {
    "mem_read": {
        "description": "检索个人经验记忆（本地 BM25，中文 2/3-gram）。任务开始或行动前调用，避免重复试错。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索词，如：融合通信 方案"},
                "limit": {"type": "number", "description": "返回条数，默认 8，最大 30"},
                "include_all": {"type": "boolean", "description": "是否包含非 active（候选/suspect）"},
            },
            "required": ["query"],
        },
        "fn": lambda a: tool_read(str(a.get("query", "")), int(a.get("limit", 8)), bool(a.get("include_all", False))),
    },
    "mem_record": {
        "description": "写入一条经验记忆（默认 staged，需人工审核转正）。写前自动检索疑似重复/冲突候选；如存在，可用 supersedes 参数确认替代旧记录。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "一句话标题"},
                "body": {"type": "string", "description": "正文 Markdown：问题→无效做法→已验证做法→适用范围"},
                "note_type": {"type": "string", "enum": TYPE_OPTIONS, "description": "类型：procedure 配方/lesson 经验/fact 事实"},
                "status": {"type": "string", "enum": ["staged", "active", "suspect"], "description": "默认 staged"},
                "tags": {"type": "string", "description": "逗号分隔标签"},
                "supersedes": {"type": "array", "items": {"type": "string"}, "description": "被本记录替代的旧记忆 id 列表（替代后旧记录标记 superseded）"},
            },
            "required": ["title"],
        },
        "fn": lambda a: tool_record(str(a.get("title", "")), str(a.get("body", "")),
                                     str(a.get("note_type", "lesson")), str(a.get("status", "staged")),
                                     str(a.get("tags", "")), a.get("supersedes")),
    },
    "mem_update": {
        "description": "更新记忆生命周期：转正/标记存疑/进热层或移出热层。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "记忆 id"},
                "status": {"type": "string", "enum": ["active", "staged", "suspect", "superseded"], "description": "目标状态"},
                "hot": {"type": "boolean", "description": "true=进热层，false=移出热层"},
            },
            "required": ["note_id"],
        },
        "fn": lambda a: tool_update(str(a.get("note_id", "")),
                                    a.get("status"), a.get("hot")),
    },
    "mem_hot": {
        "description": "查看当前热层（下一会话必读的 20 条方法论），可用于会话开始时注入参考。",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "number", "description": "条数，默认 20"}},
        },
        "fn": lambda a: tool_hot(int(a.get("limit", 20))),
    },
}

# ---------- MCP stdio 协议 ----------
def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()

def _read_line() -> str | None:
    line = sys.stdin.readline()
    return line if line else None

def main() -> int:
    while True:
        line = _read_line()
        if not line:
            break
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}

        if method == "initialize":
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }})
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "tools": [{"name": k, "description": v["description"], "inputSchema": v["inputSchema"]}
                          for k, v in TOOLS.items()]}})
        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments") or {}
            tool = TOOLS.get(name)
            if not tool:
                _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"未知工具 {name}"}})
                continue
            try:
                result = tool["fn"](args)
                _send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=1)}],
                    "isError": False}})
            except Exception as exc:  # noqa: BLE001
                _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32000, "message": str(exc)}})
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": mid, "result": {}})
        else:
            _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"未知方法 {method}"}})
    return 0

if __name__ == "__main__":
    sys.exit(main())
