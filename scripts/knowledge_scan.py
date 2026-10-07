# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# 恒忆 Evermem · 全量历史会话知识提取
# 扫描本机所有 agent 会话 jsonl → 结构化知识库（knowledge-base.md + kb.json）
# 类别：会话索引 / 常用命令 / 问题与解决（失败→成功）/ 活跃项目 / 未沉淀候选
#

import json
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]  # 项目根（scripts/ 的上一级）
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
import harvest  # noqa: E402

# ---------- 顶层目录（项目 / 知识空间）识别：盘符无关 ----------
# 只认「绝对路径的根」，不绑定任何具体盘符（旧实现写死 F:/，换盘或换平台即失效）：
#   · Windows 盘符（C:\ / D:/）与 UNC 共享（\\host\share）：形态明确，任意位置都认；
#   · POSIX 根（/）：仅认行首，避免把 URL 片段（/api/notes）误判成目录；
#   · 另加用户目录（Path.home()，可带一层 Documents），覆盖 macOS/Linux 与 Windows 文档区。
# 命中后取根之后的第一段作为项目名，系统目录（Users / usr / home…）不计入。
_TOP_SEG = r"([A-Za-z0-9_\u4e00-\u9fff][A-Za-z0-9_.\u4e00-\u9fff-]*)"
_WIN_ROOT_RE = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\[^\\/\s]+[\\/])" + _TOP_SEG)
_POSIX_ROOT_RE = re.compile(r"^[ \t]*/" + _TOP_SEG, re.M)
_HOME_ROOT_RE = re.compile(re.escape(str(Path.home())) + r"[\\/](?:Documents[\\/])?" + _TOP_SEG)
_TOP_IGNORE = {"Users", "Windows", "ProgramFiles", "tmp", "temp", "usr", "var", "etc",
               "opt", "bin", "lib", "sbin", "home", "root", "dev", "proc", "sys", "run",
               "srv", "mnt", "media", "Volumes", "Applications", "System", "Library"}

def top_dirs(text: str) -> list[str]:
    """提取文本中被提及的顶层目录名 —— 盘符无关。"""
    if not text:
        return []
    names = _WIN_ROOT_RE.findall(text) + _POSIX_ROOT_RE.findall(text) + _HOME_ROOT_RE.findall(text)
    return [n for n in names if n and n not in _TOP_IGNORE]

# ---------- 会话解析 ----------
def session_label(path: Path) -> str:
    return path.parent.name + "/" + path.stem[:12]

def read_raw_meta(path: Path) -> dict:
    """读 jsonl 原文：会话标题（ai-title）+ 用户消息 + 时间。"""
    title, first_user, texts = "", "", []
    ts0 = None
    for line in path.open(encoding="utf-8", errors="ignore"):
        try:
            d = json.loads(line)
        except (json.JSONDecodeError, OSError):
            continue
        t = d.get("type")
        if t == "ai-title":
            title = str(d.get("title") or d.get("meta", {}).get("title") or "")
        elif t == "message" and d.get("role") == "user":
            for c in d.get("content", []) or []:
                txt = str(c.get("text") or "")
                if txt and "<system-reminder" not in txt[:30]:
                    texts.append(txt[:400])
        if ts0 is None and d.get("timestamp"):
            ts0 = d.get("timestamp")
    first_user = next((t for t in texts if not t.lstrip().startswith("<")), "")
    first_line = ""
    for ln in first_user.splitlines():
        s = ln.strip()
        if s and not s.startswith("<") and not s.startswith(("#", "---")):
            first_line = s[:80]
            break
    return {"title": title, "first_user": first_line, "user_msgs": len(texts),
            "ts": time.strftime("%Y-%m-%d %H:%M", time.localtime(ts0 / 1000)) if ts0 else ""}

def extract_user_queries(seq: list) -> list[dict]:
    """提取用户提问/主题消息。"""
    out = []
    for item in seq:
        if item.get("type") == "user":
            text = str(item.get("message") or item.get("text") or "")
            if not text or len(text) < 4:
                continue
            out.append({"text": text[:300], "ts": item.get("timestamp", "")})
    return out

def extract_commands(seq: list) -> list[tuple[str, bool]]:
    """提取 Bash 命令（命令 + 是否失败，失败用 output 内容判定）。"""
    out = []
    for item in seq:
        if item.get("tool") != "Bash":
            continue
        cmd = harvest.extract_command(item)
        if cmd and len(cmd) > 3 and not re.match(r"^(cd|echo|pwd|export)\b", cmd):
            out.append((cmd, harvest.is_failure(item)))
    return out

def extract_projects(texts: list[str]) -> Counter:
    """统计被提及的顶层项目/知识空间目录（盘符无关，见 top_dirs）。"""
    c = Counter()
    for t in texts:
        c.update(top_dirs(t))
    return c

# ---------- DSH 会话（~/.dsh/sessions/<工作区>/<session>/session.jsonl.zstd） ----------
def scan_dsh() -> list[dict]:
    """DSH 会话：zstd 压缩事件流（user/message、assistant/message、tool/call、session/title）。"""
    import zstandard
    root = Path.home() / ".dsh" / "sessions"
    sessions = []
    if not root.exists():
        return sessions
    for f in root.glob("*/*/session.jsonl.zstd"):
        try:
            dctx = zstandard.ZstdDecompressor()
            with open(f, "rb") as fh, dctx.stream_reader(fh) as reader:
                text = reader.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        title, ts, toolc, users = "", "", 0, []
        for line in text.splitlines():
            try:
                d = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            t = d.get("type")
            dt = d.get("data", {}) or {}
            if t == "session/title":
                title = str(dt.get("title") or "")
            elif t == "user/message":
                txt = ""
                content = dt.get("content")
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            txt += str(c.get("text") or "")
                if not txt and dt.get("text"):
                    txt = str(dt.get("text"))
                if txt and not txt.lstrip().startswith(("<", "Current runtime context")):
                    users.append(txt[:300])
            elif t == "tool/call":
                toolc += 1
            if not ts and d.get("time"):
                try:
                    ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(d["time"]) / 1000))
                except (ValueError, TypeError):
                    pass
        topic = title or next((u for u in users if not u.lstrip().startswith("<")), "")[:80] or "（无主题）"
        sessions.append({
            "file": f.name, "id": f.parent.name[:12], "mtime": ts or "?",
            "lines": 1, "query_count": len(users), "user_msgs": len(users),
            "first_query": topic, "cmd_count": 0, "tools": {"dsh:" + f.parent.parent.name[:20]: toolc},
        })
    return sessions

def extract_file_projects(items: list) -> Counter:
    """从 Read/Write 的 file_path 统计工作目录活跃度。"""
    c = Counter()
    for item in items:
        if item.get("tool") not in ("Read", "Write", "Edit"):
            continue
        try:
            args = json.loads(item.get("arguments") or "{}")
            p = args.get("file_path", "")
        except (json.JSONDecodeError, TypeError):
            continue
        if not p:
            continue
        # 盘符无关：按「绝对路径根」提取顶层目录，不写死任何盘符（见 top_dirs）
        for name in top_dirs(p):
            c[name] += 1
    return c

# ---------- atomcode 会话（~/.atomcode/sessions） ----------
def scan_atomcode() -> list[dict]:
    """atomcode 会话：每行含 user/assistant 字段（真实对话文本）。"""
    root = Path.home() / ".atomcode" / "sessions"
    sessions = []
    if not root.exists():
        return sessions
    for f in sorted(root.glob("*/*.jsonl")):
        users, assts, sessions_id, iso = [], [], "", ""
        for line in f.open(encoding="utf-8", errors="replace"):
            try:
                d = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if d.get("user"):
                users.append(str(d["user"]))
            if d.get("assistant"):
                assts.append(str(d["assistant"]))
            if not sessions_id:
                sessions_id = d.get("session_id", "")[:12]
            if not iso:
                iso = str(d.get("iso", ""))[:16].replace("T", " ")
        topic = ""
        for u in users:
            s = u.strip()
            if s and not s.startswith("<"):
                topic = s[:80]
                break
        sessions.append({
            "file": f.name, "id": sessions_id, "mtime": iso or "?",
            "lines": len(users), "query_count": len(users), "user_msgs": len(users),
            "first_query": topic or "（无主题）",
            "cmd_count": 0, "tools": {"atomcode": len(assts)},
        })
    return sessions

# ---------- 主流程 ----------
def main():
    files = harvest.iter_session_files(None)
    sessions = []
    all_commands: Counter = Counter()
    failed_commands: Counter = Counter()
    topic_counter: Counter = Counter()
    projects: Counter = Counter()
    session_list = []

    for path in files:
        meta = read_raw_meta(path)
        pairs = harvest.load_pairs(path)
        cmds = extract_commands(pairs)
        file_proj = extract_file_projects(pairs)
        projects.update(file_proj)
        # 会话主题：ai-title 优先，否则首条用户消息
        topic = meta["title"] or meta["first_user"] or "（无主题）"
        # 工具分布
        tools = Counter(s.get("tool", "?") for s in pairs)
        for c, failed in cmds:
            all_commands[c] += 1
            if failed:
                failed_commands[c] += 1
        session_list.append({
            "file": path.name,
            "id": path.stem[:12],
            "mtime": meta["ts"],
            "lines": len(pairs),
            "first_query": topic,
            "query_count": meta["user_msgs"],
            "cmd_count": len(cmds),
            "tools": dict(tools.most_common(4)),
        })

    # 常用命令去重排序
    common_cmds = [{"cmd": k, "count": v, "failed": failed_commands.get(k, 0)}
                   for k, v in all_commands.most_common(40) if v >= 2]
    # 失败命令（问题与解决线索）
    issue_cmds = [{"cmd": k, "count": v} for k, v in failed_commands.most_common(15) if v >= 1]

    kb = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scope": {"sessions": len(session_list), "files": len(files), "lines_total": sum(s["lines"] for s in session_list)},
        "sessions": session_list,
        "common_commands": common_cmds,
        "repeated_failures": issue_cmds,
        "active_projects": [{"name": k, "mentions": v} for k, v in projects.most_common(15)],
        "notes": "本机记忆库另有 40 条人工/AI 提炼的经验笔记（notes/），本清单为会话层结构化索引，二者互补。",
    }
    # 补充 atomcode（其他 agent 的真实会话）
    atom = scan_atomcode()
    if atom:
        kb["scope"]["atomcode_sessions"] = len(atom)
        session_list.extend(atom)
        kb["sessions"] = session_list
    # 补充 DSH（zstd 压缩会话）
    dsh = scan_dsh()
    if dsh:
        kb["scope"]["dsh_sessions"] = len(dsh)
        session_list.extend(dsh)
        kb["sessions"] = session_list
    (BASE / "kb.json").write_text(json.dumps(kb, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[kb] 生成完成：{len(session_list)} 会话（WorkBuddy {len(session_list)-len(atom)-len(dsh)} + atomcode {len(atom)} + DSH {len(dsh)}）→ kb.json")

    # ---------- Markdown 知识库 ----------
    lines = []
    lines.append("# 恒忆 Evermem · 历史会话知识库\n")
    lines.append(f"> 生成：{kb['generated']} ｜ 范围：{kb['scope']['sessions']} 个会话 · {kb['scope']['files']} 文件 · {kb['scope']['lines_total']} 行 ｜ 跨度 40 天\n")
    lines.append("> 知识类型：会话索引（主题/时间/上下文）· 常用命令 · 问题与解决（重复失败）· 活跃项目 · 记忆库笔记（另有 40 条）\n")

    lines.append("\n## 一、会话索引（来源：各 jsonl）\n")
    lines.append("| 时间 | 会话ID | 行数 | 提问数 | 主题（首条用户消息） | 主要工具 |")
    lines.append("|---|---|---|---|---|---|")
    for s in sorted(session_list, key=lambda x: x["mtime"], reverse=True)[:20]:
        tools = "、".join(f"{k}{v}" for k, v in s["tools"].items())
        lines.append(f"| {s['mtime']} | `{s['id']}` | {s['lines']} | {s['query_count']} | {s['first_query'][:34]} | {tools} |")

    lines.append("\n## 二、常用命令（全历史，去重，≥2 次）\n")
    lines.append("| 命令 | 次数 | 曾失败 |")
    lines.append("|---|---|---|")
    for c in common_cmds[:25]:
        flag = "⚠" if c["failed"] else ""
        lines.append(f"| `{c['cmd'][:70]}` | {c['count']} | {flag} |")

    lines.append("\n## 三、重复失败（问题与解决线索，待沉淀/已沉淀）\n")
    lines.append("| 失败命令 | 次数 |")
    lines.append("|---|---|")
    for c in issue_cmds[:12]:
        lines.append(f"| `{c['cmd'][:70]}` | {c['count']} |")

    lines.append("\n## 四、活跃项目（本地路径提及频次）\n")
    lines.append("| 项目 | 提及 |")
    lines.append("|---|---|")
    for p in kb["active_projects"][:12]:
        lines.append(f"| {p['name']} | {p['mentions']} |")

    lines.append("\n## 五、后续可用方式\n")
    lines.append("- 检索：`mem.py recall <关键词>`（命中 40 条经验笔记 + 热层 20 条）\n- 会话回看：按上表会话 ID 打开对应 jsonl\n- 沉淀：本清单由 `knowledge_scan.py` 再生（全量扫描）；失败模式可 `harvest.py scan` → 候选审核\n- 去重：常用命令已按频次合并；与记忆库笔记不重复（本清单是会话层索引，笔记是提炼结论）\n")
    (BASE / "knowledge-base.md").write_text("\n".join(lines), encoding="utf-8")
    print("[kb] 知识库文档 → knowledge-base.md")

if __name__ == "__main__":
    main()
