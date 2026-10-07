#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# harvest - 从会话记录自动收割试错证据与记忆候选（方案 B 的自动捕获层）
#
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
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

# 数据目录必须与 mem.py 同源（env > 持久化配置 > 可移植默认），
# 否则打包后候选会写进临时解包目录，界面与检索看不到。
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths as _paths  # noqa: E402

ROOT = _paths.data_root()
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
    # 原子写：收割常驻后台线程，直接覆盖中断会留下截断游标（下次重复收割）
    tmp = STATE_PATH.with_name(STATE_PATH.name + f".tmp-{os.getpid()}")
    try:
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, STATE_PATH)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass

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

_SIMPLE_CMD = re.compile(r"^\s*(ls|cd|pwd|echo|cat|head|tail|clear|date|whoami|git status|git log|git ls-files)\b")

# 工具名黑名单：只有单个工具名（无实质命令内容）的"成功配方"不是知识，过滤掉
_TOOL_NAME_ONLY = re.compile(
    r"^(?:Bash|PowerShell|Python|Node|Write|Read|Edit|TaskStop|TaskOutput|WebFetch|WebSearch|"
    r"AskUserQuestion|ToolSearch|present_files|show_widget|Skill|Agent|TaskCreate|TaskUpdate|"
    r"TaskGet|TaskList|DeferExecuteTool|Grep|Glob|mcp__\S+)\b[^\w]*$")

def looks_like_complex_cmd(sig: str) -> bool:
    """高价值"成功配方"信号：非常规命令且带复杂度（多命令/变量/参数化路径/管道）。"""
    if _TOOL_NAME_ONLY.match(sig.strip()):
        return False
    if any(k in sig for k in ("&&", ";", "$", "|", "python", "--")):
        return True
    return not bool(_SIMPLE_CMD.match(sig))

def build_success_candidate(sig: str, items: list[dict], session_id: str) -> tuple[str, str] | None:
    """成功配方候选（procedure）：一次成功、命令复杂、会话内认可用它完成实作。"""
    successes = [i for i in items if not i["_failed"]]
    if not successes:
        return None
    first = successes[0]
    tool = first["tool"]
    cmd = redact(extract_command(first))[:160]
    out_snip = redact(first["output"])[:300]
    last = successes[-1]
    title = f"[候选] 成功配方：{sig[:70]}"
    body = [
        f"工具：{tool}",
        f"命令签名：{sig}",
        f"首次命令：{cmd}",
        f"执行次数：{len(successes)}",
        "输出片段（末次）：",
        "```",
        out_snip or "(无输出)",
        "```",
        "",
        "说明：本次会话中该命令（或等价命令）已成功执行，可作为可复用配方候选。",
        f"来源会话：{session_id}",
        f"来源 callId：{first['callId']}",
    ]
    return title, "\n".join(body)


# ============ 任务级提炼（Task-Level Distillation）============
# 命令级收割只能产出"某命令可用"的碎片（且签名归一化后大量重复→自动归档）。
# 任务级提炼弥补语义盲区：同一会话内出现"多次失败 → 最终成功"的完整任务链时，
# 结合用户任务指令（意图）与最终方案，产出 lesson 级候选——这才是"经验自动入库"。
_MSG_REMINDER = re.compile(r"<system-reminder.*?</system-reminder>", re.S)
# 元指令特征词：这类指令不是任务目标（"总结经验/入库/回顾"等），选意图时按子串跳过
_META_HINTS = ("总结", "入库", "记住", "回忆", "回顾", "沉淀", "怎么用", "经验")
# 短反馈：整条指令即"好的/可以/谢谢"这类 → 跳过（只整体匹配，不用子串——"这样可以"是任务指令）
_SHORT_OK = {"好的", "可以", "可以了", "没问题", "行", "好", "谢谢", "感谢", "知道了", "收到", "ok"}
# 任务"最终方案"只看执行类工具，跳过 show_widget/present_files 等汇报调用
_EXEC_TOOLS = ("Bash", "PowerShell", "Python", "Write", "Edit", "Node", "Cmd", "Shell")
# 附件/引用占位（图片、文件）不是任务指令：@image#xxx / <image_local_path>... 等
_ATTACH = re.compile(r"@image#|<image_local_path>|<file_path>|<attachment", re.I)

# ---- 标题蒸馏（L1）：把原始口语化指令压成"动宾规则"，避免标题变成一整句原话 ----
# 口语前缀：用户下指令时常带"给你一个思路/能不能/请帮我…"，这些不是任务本体
_FILLER_PREFIX = (
    "给你一个思路", "给你一个", "我有个想法", "我想请你", "我想让你", "我想", "我想要", "我希望",
    "请你", "请帮我", "请", "帮我", "麻烦你", "麻烦", "能不能", "能否", "可不可以", "是否可以",
    "咱们", "我们", "现在", "接下来", "另外", "还有", "顺便",
)
# 连接词：长句在这些位置断开取前半段，得到"动作+对象"核心
_CUT_CONNECTORS = ("然后", "接着", "再", "并且", "同时", "以及", "这样", "以便", "从而", "另外", "还有", "之后")
_TRAIL_FILLER = ("一下", "吧", "呢", "啊", "谢谢", "感谢", "哈")
# 输出里的噪声行：Bash 等工具会把回显打在第一行（"Command: cd ..."），不是错误信息
_NOISE_LINE = re.compile(r"^\s*(Command|命令|Working directory|当前目录)\s*[:：]", re.I)
_ERR_HINT = re.compile(
    r"error|错误|失败|异常|denied|refused|traceback|exception|not found|no such|cannot|can't|"
    r"无法|不能|拒绝|超时|timeout|invalid|EOF|exit code|permission|not allowed|missing", re.I)
# 最终方案：不再截成 140 字的残片（脚本路径类方案尤其危险——只剩路径等于没记）
_OK_CMD_LIMIT = 600
_SCRIPT_EXT = (".py", ".js", ".mjs", ".ps1", ".sh", ".bash", ".bat", ".cmd")
_SCRIPT_PATH = re.compile(r"([A-Za-z]:[\\/][^\s\"'|><]+|\.{0,2}[\\/][^\s\"'|><]+)(" + "|".join(
    e.replace(".", r"\.") for e in _SCRIPT_EXT) + r")\b")


def distill_intent(raw: str, limit: int = 34) -> str:
    """把原始用户指令蒸馏为可当标题的动宾短语（保语义、去口语、断长句）。"""
    t = re.sub(r"\s+", " ", str(raw or "").strip())
    if not t:
        return ""
    changed = True
    while changed:  # 反复剥离口语前缀（"请帮我能不能…"这类叠加）
        changed = False
        for f in _FILLER_PREFIX:
            if t.startswith(f) and len(t) > len(f) + 4:
                t = t[len(f):].lstrip("，,、：: ")
                changed = True
    for c in _CUT_CONNECTORS:  # 长句在连接词处断开，取任务本体
        pos = t.find(c)
        if 8 <= pos <= limit:
            t = t[:pos]
            break
    t = t.rstrip("，,、；;：: ")
    for f in _TRAIL_FILLER:
        if t.endswith(f) and len(t) > len(f) + 4:
            t = t[: -len(f)]
    if len(t) > limit:
        cut = t[:limit]
        for sep in ("。", "；", "，", "、", "：", " ", "的"):
            pos = cut.rfind(sep)
            if pos > limit * 0.5:
                cut = cut[:pos].rstrip("，；：、的 ") + "…"
                break
        else:
            cut = cut + "…"
        t = cut
    return t or str(raw)[:limit]


def best_error_line(output: str, limit: int = 140) -> str:
    """从工具输出里挑真正的错误信息行，而不是命令回显。"""
    lines = [l.strip() for l in str(output or "").splitlines() if l.strip()]
    lines = [l for l in lines if not _NOISE_LINE.match(l)]
    for l in lines:
        if _ERR_HINT.search(l):
            return l[:limit]
    return (lines[-1][:limit] if lines else "(无输出)")


def extract_command_full(call: dict) -> str:
    """取完整命令文本（不截断）；用于"最终方案"必须可照抄复现。"""
    return (extract_command(call) or "").strip()


def expand_script_body(cmd: str, call: dict | None = None, limit_lines: int = 40) -> str:
    """方案是脚本路径时，附上脚本正文前 N 行——只留路径等于没记下方案。"""
    cands = []
    m = _SCRIPT_PATH.search(cmd or "")
    if m:
        cands.append(m.group(0))
    if call:
        args = call.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if isinstance(args, dict):
            for key in ("file_path", "path", "content"):
                v = args.get(key)
                if isinstance(v, str) and v.strip():
                    cands.append(v.strip())
    for c in cands:
        try:
            p = Path(c)
        except (OSError, ValueError):
            continue
        if not p.is_file():
            continue
        try:
            if p.stat().st_size > 200_000:  # 大文件只取开头，避免候选正文爆炸
                with p.open("r", encoding="utf-8", errors="ignore") as f:
                    head = "".join(f.readline() for _ in range(limit_lines))
            else:
                head = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = head.splitlines()[:limit_lines]
        if not lines:
            continue
        return "\n".join(lines)
    return ""


def load_user_intents(path: Path) -> list[str]:
    """提取会话里的用户指令：剥去宿主注入的 <system-reminder> 整块与 <user_query> 标签壳。"""
    intents = []
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return intents
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "message" or obj.get("role") != "user":
            continue
        content = obj.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "input_text":
                continue
            t = _MSG_REMINDER.sub("", str(block.get("text") or "")).strip()
            t = re.sub(r"</?user_query>", "", t).strip()
            if len(t) >= 4:
                intents.append(t)
    return intents


def task_level_distill(seq: list[dict], intents: list[str], session_id: str) -> tuple[str, str, str] | None:
    """任务级提炼：多次失败 → 最终成功的完整任务链 → lesson 候选。

    门槛（防把普通调试过程也变成经验）：
      1) 失败调用 ≥ 2（真实试错，而非一次成功）
      2) 其后存在成功调用（任务最终有产出）
      3) 会话内有明确任务指令（≥6 字，跳过"好的/感谢/总结经验"等收尾与元指令）
    返回 (任务签名, 标题, 正文)；不满足门槛返回 None。
    """
    fails = [i for i in seq if i["_failed"]]
    oks = [i for i in seq if not i["_failed"]]
    if len(fails) < 2 or not oks or not intents:
        return None
    # 意图：会话开头的第一条真实任务指令（任务先下达再执行；收尾消息在尾部，倒序会挡路）
    intent = ""
    for t in intents:
        t2 = t.strip()
        if len(t2) < 6:
            continue
        if _ATTACH.search(t2):
            continue
        if len(t2) <= 10 and t2.lower() in _SHORT_OK:  # 短反馈（好的/可以/谢谢）不是任务指令
            continue
        if any(k in t2 for k in _META_HINTS):
            continue
        intent = t2
        break
    if not intent:
        return None
    # 标题用蒸馏后的动宾短语；正文保留原始指令全文（蒸馏只影响展示，不丢信息）
    short = distill_intent(intent) or intent[:34]
    tool = fails[0]["tool"] or "执行类工具"
    pit, seen_pit = [], set()
    for f in fails:
        if len(pit) >= 3:
            break
        cmd = redact(extract_command(f))[:70] or "(无命令)"
        # 错误信息取"真错误行"，过滤 Bash 的 Command: 回显噪声；并按 (命令,错误) 去重
        err = redact(best_error_line(f.get("output", ""))) 
        key = (cmd[:40], err[:40])
        if key in seen_pit:
            continue
        seen_pit.add(key)
        pit.append(f"{cmd} → {err}")
    # 最终方案：最后一次失败之后的第一个执行类成功调用（任务"解决那一刻"，
    # 而非会话收尾的汇报/写记忆动作）；找不到则退回最后执行类成功
    failed_idx = [i for i, x in enumerate(seq) if x["_failed"]]
    after = [x for x in seq[failed_idx[-1] + 1:]
             if not x["_failed"] and x["tool"] in _EXEC_TOOLS]
    last_ok = after[0] if after else next(
        (i for i in reversed(oks) if i["tool"] in _EXEC_TOOLS), oks[-1])
    ok_cmd = redact(extract_command_full(last_ok))[:_OK_CMD_LIMIT] or "(见输出)"
    ok_snip = redact(last_ok["output"])[:180].replace("\n", " ")
    script = redact(expand_script_body(ok_cmd, last_ok)) if ok_cmd != "(见输出)" else ""
    title = f"[候选] 任务经验：{short}（失败 {len(fails)} 次后成功）"
    body = "\n".join([
        f"任务目标：{short}",
        f"原始指令：{intent}",
        f"工具：{tool} 等",
        f"失败次数：{len(fails)}",
        "踩坑片段（前 3 次失败）：",
        "```",
        *pit,
        "```",
        "",
        "最终方案：",
        "```",
        ok_cmd,
        "```",
        *([f"方案脚本正文（{last_ok.get('tool')} 写入）：", "```", script, "```", ""] if script else [""]),
        "成功输出片段：",
        "```",
        ok_snip or "(无输出)",
        "```",
        "",
        "说明：harvest 任务级提炼自动生成（staged，需验证后转 active）。",
        f"来源会话：{session_id}",
    ])
    sig = f"task:{intent[:24]}"
    return sig, title, body

def _already_promoted(title: str, nid: str) -> bool:
    """任务级候选是否已转正为正式笔记（按 id 或 title 判断），防"转正→重生→再转正"循环。"""
    for sub in ("lessons", "procedures", "facts"):
        for p in (NOTES / sub).glob("*.md"):
            raw = p.read_text(encoding="utf-8", errors="ignore")
            if f"id: {nid}" in raw or f"title: {title}" in raw:
                return True
    return False


def cmd_scan(args) -> int:
    files = iter_session_files(args.days)
    if not files:
        print("未找到会话记录。")
        return 0
    state = load_state()
    seen = set(state.get("processed_callids", []))
    events: list[dict] = []
    candidates: list[tuple[str, str, str, str]] = []

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
            # not fails：--min-failures 0 时 fails 为空，下面的 max() 会抛 ValueError
            if not fails or len(fails) < args.min_failures:
                # 成功配方候选：无失败但命令复杂（一次成功的价值同样值得沉淀）
                if looks_like_complex_cmd(sig):
                    rc = build_success_candidate(sig, items, session_id)
                    if rc:
                        candidates.append((sig, rc[0], rc[1], "procedure"))
                continue
            # 失败之后是否出现同签名的成功（late-success）
            # 修正：成功项的输出必须不含错误特征（曾有"成功片段实为错误栈"的误判案例）
            success = None
            last_fail_idx = max(i for i, x in enumerate(items) if x["_failed"])
            for later in items[last_fail_idx + 1:]:
                if not later["_failed"] and not looks_like_error(str(later.get("output") or "")):
                    success = later
                    break
            if not success and not args.include_pure_failure:
                continue
            title, body = build_candidate(sig, fails, success, session_id)
            candidates.append((sig, title, body, "lesson"))
        # 任务级提炼：基于整会话调用（增量窗口会切断"失败→成功"任务链），
        # 产出 lesson 候选；重复会话靠 cand 文件同名（签名哈希）去重，不重复写入
        if not args.no_task_level:
            full = [s for s in load_pairs(path)]
            for item in full:
                item["_failed"] = is_failure(item)
            tl = task_level_distill(full, load_user_intents(path), session_id)
            if tl:
                sig, title, body = tl
                candidates.append((sig, title, body, "lesson"))

    print(f"扫描会话文件 {len(files)} 个，新执行记录 {total_calls} 条")
    print(f"识别到候选模式 {len(candidates)} 组\n")
    for sig, title, body, ntype in candidates[: args.limit]:
        print(f"- [{ntype}] {title}")
        print(f"    {body.splitlines()[1] if len(body.splitlines()) > 1 else ''}")
    if args.dry_run:
        print("\n[dry-run] 未写入任何文件。")
        return 0

    n_ev = write_events(events)
    CANDIDATES.mkdir(parents=True, exist_ok=True)
    written = 0
    for sig, title, body, ntype in candidates:
        h = hashlib.sha1(sig.encode("utf-8")).hexdigest()[:8]
        nid = f"{time.strftime('%Y%m%d-%H%M')}-{h}"
        fp = CANDIDATES / f"cand-{h}.md"
        if fp.exists():
            continue
        if sig.startswith("task:") and (CANDIDATES / "archive" / fp.name).exists():
            # 任务级候选已被归档过：防"归档→下轮重生→再归档"的多副本循环
            continue
        if sig.startswith("task:") and _already_promoted(title, nid):
            # 任务级候选已转正为正式笔记：防"转正→下轮重生"的重复生成
            continue
        text = (
            "---\n"
            f"id: {nid}\n"
            f"type: {ntype}\n"
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
    p.add_argument("--no-task-level", action="store_true",
                   help="禁用任务级提炼（默认开启：多次失败→成功的任务链产出 lesson 候选）")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("signals", help="信号统计")
    p.add_argument("--days", type=int, default=3)
    p.set_defaults(func=cmd_signals)

    args = ap.parse_args()
    return args.func(args)

if __name__ == "__main__":
    sys.exit(main())
