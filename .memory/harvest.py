#!/usr/bin/env python3
# harvest - 从会话记录自动收割试错证据与记忆候选（方案 B 的自动捕获层）
#
# Copyright (c) 2026 Jose-AI
# https://www.linhut.cn
# SPDX-License-Identifier: MIT
#
# 不依赖任何宿主钩子：直接读取会话落盘的 jsonl，配对调用与结果，
# 识别"失败 / 重试 / 失败后成功"模式，落证据层并生成候选笔记。
#
# 用法：
#  python harvest.py scan             # 增量扫描并生成候选（写入候选区）
#  python harvest.py scan --dry-run   # 只看会挖出什么，不落盘
#  python harvest.py scan --days 7    # 只处理最近 N 天
#  python harvest.py signals          # 只打印信号统计，不生成笔记

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOTES = ROOT / "notes"
CANDIDATES = NOTES / "candidates"
EVENTS = ROOT / "events"
STATE_PATH = ROOT / "harvest_state.json"

SESSION_ROOTS = (
    Path.home() / ".workbuddy" / "projects",
    Path.home() / ".claude" / "projects",
    Path.home() / ".codex" / "sessions",
    Path.home() / ".dsh" / "sessions",
)

# 严格错误模式：只匹配真正的报错行，避免把"抓取到的正文里含 error 一词"误判为失败
STRICT_ERROR_PATTERNS = [
    r"command not found", r"no such file or directory", r"permission denied",
    r"^\s*fatal:", r"^\s*error:", r"^\s*usage error", r"traceback \(most recent call",
    r"sandbox-center", r"blocked by security", r"access is denied",
    r"is not recognized as an internal", r"command failed", r"npm err!",
    r"module not found", r"importerror", r"syntaxerror",
    r"未能(找到|加载)", r"被(拦截|拒绝)", r"权限不足",
    r"program blocked", r"cannot find", r"failed to (load|connect|start)",
]

# 只看状态的兜底：这些状态视为明确失败
FAIL_STATUSES = {"error", "failed", "failure", "denied", "blocked", "aborted", "timeout"}

REDACT_PATTERNS = [
    (r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}", r"\1<redacted>"),
    (r"(?i)(authorization[\"':\s]+)[A-Za-z0-9._\-]{8,}", r"\1<redacted>"),
    (r"(?i)(token[\"':\s]+)[A-Za-z0-9._\-]{8,}", r"\1<redacted>"),
    (r"(?i)(api[_-]?key[\"':\s]+)[A-Za-z0-9._\-]{8,}", r"\1<redacted>"),
    (r"\b[0-9a-f]{32,}\b", "<hex>"),
    (r"\b[\w.+-]+@[\w-]+\.[\w.]+\b", "<email>"),
]

UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
NUM_RE = re.compile(r"\b\d+\b")


def redact(text: str) -> str:
    if not text:
        return ""
    for pat, rep in REDACT_PATTERNS:
        text = re.sub(pat, rep, text)
    return text


def normalize_command(cmd: str) -> str:
    """生成命令签名：抹掉变量部分，只留结构。"""
    s = (cmd or "").strip()
    s = UUID_RE.sub("<uuid>", s)
    s = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "<path>", s)
    s = re.sub(r"(?<![\w])/[^\s\"']+", "<path>", s)
    s = NUM_RE.sub("<n>", s)
    # 长字符串字面量掩码，避免把整段正文塞进签名
    s = re.sub(r"\"[^\"\n]{24,}\"", '"<str>"', s)
    s = re.sub(r"'[^'\n]{24,}'", "'<str>'", s)
    s = " ".join(s.split())
    return s[:200]


def looks_like_error(text: str) -> bool:
    """严格判定：只看真正的报错行，不做宽松关键词匹配。"""
    if not text:
        return False
    head = "\n".join(text.splitlines()[:12])
    return any(re.search(p, head, re.I | re.M) for p in STRICT_ERROR_PATTERNS)


def signature_of(item: dict) -> str:
    """命令型工具用归一化命令做签名；其他工具只用工具名，避免把长 prompt 塞进签名。"""
    tool = item.get("tool") or ""
    if tool in ("Bash", "PowerShell"):
        cmd = extract_command(item)
        return f"{tool}:{normalize_command(cmd)}" if cmd else f"{tool}:<空>"
    return f"{tool}"


def is_failure(item: dict) -> bool:
    """优先用执行状态判定；命令型工具再补查输出里的严格报错行。"""
    status = str(item.get("status") or "").lower()
    if status in FAIL_STATUSES:
        return True
    if item.get("tool") in ("Bash", "PowerShell"):
        return looks_like_error(item.get("output") or "")
    return False


def iter_session_files(days: int | None):
    """扫所有已安装宿主的会话落盘目录，不存在就跳过。"""
    cutoff = time.time() - days * 86400 if days else 0
    out = []
    for root in SESSION_ROOTS:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*.jsonl")):
            try:
                if p.stat().st_mtime >= cutoff:
                    out.append(p)
            except OSError:
                continue
    return out


def flatten_output(value) -> str:
    """不同宿主的输出结构不同，统一拍平成文本。"""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("text") or json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(item.get("text") or json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return "" if value is None else str(value)


def load_pairs(path: Path):
    """配对工具调用与结果，兼容两种落盘格式。

    扁平式：顶层 function_call / function_call_result（WorkBuddy）
    嵌套式：message.content 里的 tool_use / tool_result（Claude Code）
    其余格式解析不出调用对就返回空，不影响其他文件。
    """
    calls: dict[str, dict] = {}
    results: dict[str, dict] = {}
    order: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = obj.get("type")
        if t == "function_call":
            cid = obj.get("callId") or obj.get("id")
            if cid and cid not in calls:
                calls[cid] = {
                    "name": obj.get("name") or "",
                    "arguments": obj.get("arguments") or {},
                    "timestamp": obj.get("timestamp") or 0,
                    "cwd": obj.get("cwd") or "",
                }
                order.append(cid)
        elif t == "function_call_result":
            cid = obj.get("callId")
            if cid:
                results[cid] = {
                    "status": obj.get("status") or "unknown",
                    "output": flatten_output(obj.get("output")),
                }
        else:
            content = (obj.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_use":
                    cid = block.get("id")
                    if cid and cid not in calls:
                        calls[cid] = {
                            "name": block.get("name") or "",
                            "arguments": block.get("input") or {},
                            "timestamp": obj.get("timestamp") or 0,
                            "cwd": obj.get("cwd") or "",
                        }
                        order.append(cid)
                elif btype == "tool_result":
                    cid = block.get("tool_use_id")
                    if cid:
                        results[cid] = {
                            "status": "error" if block.get("is_error") else "completed",
                            "output": flatten_output(block.get("content")),
                        }
    seq = []
    for cid in order:
        call = calls[cid]
        res = results.get(cid, {})
        seq.append({
            "callId": cid,
            "tool": call.get("name") or "",
            "arguments": call.get("arguments") or {},
            "status": res.get("status") or "unknown",
            "output": res.get("output") or "",
            "timestamp": call.get("timestamp") or 0,
            "cwd": call.get("cwd") or "",
        })
    return seq


def extract_command(call: dict) -> str:
    args = call.get("arguments") or {}
    # 会话记录里 arguments 可能是 JSON 字符串，需要先解析
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return args.strip()
    if isinstance(args, dict):
        for key in ("command", "cmd", "script", "pattern", "query", "file_path", "path"):
            v = args.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    elif isinstance(args, str):
        return args.strip()
    return ""


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"processed_callids": [], "last_run": None}


def save_state(state: dict) -> None:
    state["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def write_events(events: list[dict]) -> int:
    EVENTS.mkdir(parents=True, exist_ok=True)
    if not events:
        return 0
    path = EVENTS / f"{time.strftime('%Y-%m')}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return len(events)


def build_candidate(sig: str, failures: list[dict], success: dict | None, session_id: str) -> tuple[str, str]:
    """生成候选笔记的标题与正文（status 为 staged，需人工或复用验证后转 active）。"""
    tool = failures[0]["tool"]
    first_cmd = redact(extract_command(failures[0]))[:120]
    err_snip = redact(failures[0]["output"])[:400]
    ok_snip = redact(success["output"])[:300] if success else ""
    title = f"[候选] {tool} 失败后成功：{sig[:70]}" if success else f"[候选] {tool} 反复失败：{sig[:70]}"
    body = [
        f"工具：{tool}",
        f"命令签名：{sig}",
        f"首次命令：{first_cmd}",
        "",
        f"失败次数：{len(failures)}",
        "失败输出片段：",
        "```",
        err_snip or "(无输出)",
        "```",
    ]
    if success:
        body += ["", "随后成功命令：", "```", redact(extract_command(success))[:200], "```",
                 "", "成功输出片段：", "```", ok_snip or "(无输出)", "```"]
    body += ["", f"来源会话：{session_id}", f"来源 callId：{failures[0]['callId']}"]
    return title, "\n".join(body)


def cmd_scan(args) -> int:
    files = iter_session_files(args.days)
    if not files:
        print("未找到会话记录。")
        return 0
    state = load_state()
    seen = set(state.get("processed_callids", []))
    events: list[dict] = []
    candidates: list[tuple[str, str, str]] = []

    total_calls = 0
    for path in files:
        session_id = path.stem
        seq = [s for s in load_pairs(path) if s["callId"] not in seen]
        total_calls += len(seq)
        groups: dict[str, list[dict]] = defaultdict(list)
        for item in seq:
            failed = is_failure(item)
            item["_failed"] = failed
            sig = signature_of(item)
            groups[sig].append(item)
            events.append({
                "ts": item["timestamp"], "session": session_id, "tool": item["tool"],
                "callId": item["callId"], "status": item["status"],
                "sig": sig, "failed": failed,
                "cmd": redact(extract_command(item))[:300], "output": redact(item["output"])[:300],
            })
        for sig, items in groups.items():
            fails = [i for i in items if i["_failed"]]
            if len(fails) < args.min_failures:
                continue
            # 失败之后是否出现同签名的成功（late-success）
            success = None
            last_fail_idx = max(i for i, x in enumerate(items) if x["_failed"])
            for later in items[last_fail_idx + 1:]:
                if not later["_failed"]:
                    success = later
                    break
            if not success and not args.include_pure_failure:
                continue
            title, body = build_candidate(sig, fails, success, session_id)
            candidates.append((sig, title, body))

    print(f"扫描会话文件 {len(files)} 个，新执行记录 {total_calls} 条")
    print(f"识别到候选模式 {len(candidates)} 组\n")
    for sig, title, body in candidates[: args.limit]:
        print(f"- {title}")
        print(f"    {body.splitlines()[1] if len(body.splitlines()) > 1 else ''}")
    if args.dry_run:
        print("\n[dry-run] 未写入任何文件。")
        return 0

    n_ev = write_events(events)
    CANDIDATES.mkdir(parents=True, exist_ok=True)
    written = 0
    for sig, title, body in candidates:
        h = hashlib.sha1(sig.encode("utf-8")).hexdigest()[:8]
        nid = f"{time.strftime('%Y%m%d-%H%M')}-{h}"
        fp = CANDIDATES / f"cand-{h}.md"
        if fp.exists():
            continue
        text = (
            "---\n"
            f"id: {nid}\n"
            "type: lesson\n"
            "status: staged\n"
            f"title: {title}\n"
            "tags: [自动收割, 待验证]\n"
            "env: win32\n"
            f"created: {time.strftime('%Y-%m-%d')}\n"
            "---\n\n"
            f"{body}\n"
        )
        fp.write_text(text, encoding="utf-8")
        written += 1

    state["processed_callids"] = list(seen | {e["callId"] for e in events})[-5000:]
    save_state(state)
    print(f"\n证据写入 {n_ev} 条 → events/")
    print(f"候选笔记写入 {written} 条 → notes/candidates/（status=staged，需验证后转 active）")
    print("下一步：运行 mem.py reindex，然后人工审阅 candidates 目录。")
    return 0


def cmd_signals(args) -> int:
    files = iter_session_files(args.days)
    total = 0
    failed = 0
    by_tool: dict[str, int] = defaultdict(int)
    for path in files:
        for item in load_pairs(path):
            total += 1
            if item["status"] != "completed" or looks_like_error(item["output"]):
                failed += 1
                by_tool[item["tool"]] += 1
    print(f"执行记录 {total} 条，其中失败/报错 {failed} 条")
    print("失败按工具分布：", dict(sorted(by_tool.items(), key=lambda kv: -kv[1])[:10]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="harvest", description="会话试错自动收割")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan", help="扫描并生成候选")
    p.add_argument("--days", type=int, default=3)
    p.add_argument("--min-failures", type=int, default=2)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--include-pure-failure", action="store_true", help="包含没有后续成功的纯失败")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("signals", help="信号统计")
    p.add_argument("--days", type=int, default=3)
    p.set_defaults(func=cmd_signals)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
