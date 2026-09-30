#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# pmem - 个人跨会话经验记忆（零依赖 MVP，方案 B）
#
#
# 不依赖任何宿主钩子或 MCP 通道：笔记是本地 Markdown，索引可随时重建。
# 用法：
#  python mem.py recall "查询词" [--limit 5] [--all]
#  python mem.py add --type procedure --title "..." --body "..." [--tags a,b]
#  python mem.py show <id>
#  python mem.py reindex
#  python mem.py stats
#  python mem.py hot --apply

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import random
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

# Windows 控制台/管道默认编码（GBK/cp1252）打印中文会 UnicodeEncodeError；
# 统一按 UTF-8(replace) 输出，保证打包后的 exe 与控制台管道都能稳定打印。
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        pass

# 数据目录与代码目录的唯一解析入口；先补 sys.path，
# 保证从任意 cwd、冻结态解包目录调用本模块都能找到它。
from pathlib import Path

import sys as _sys
if str(Path(__file__).resolve().parent) not in _sys.path:
    _sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths as _paths  # noqa: E402
paths = _paths  # 供同目录模块复用同一份解析结果（历史写法兼容）

def code_root() -> Path:
    """代码目录（模板 / 脚本 / 前端资源），冻绝态下可能是临时解包目录。"""
    return _paths.code_root()

def resolve_root() -> Path:
    """数据目录（全项目唯一入口）：环境变量 > 持久化配置 > 可移植默认目录。

    mem / server / backup / memimport / harvest / recipes 都必须走 paths.data_root()，
    否则 PyInstaller 单文件包会出现「核心检索、界面配置、导入、备份恢复」
    各指向一个目录的分裂问题。
    """
    return _paths.data_root()

HOST_MEMORY_CANDIDATES = (
    ".workbuddy/memory/MEMORY.md",
    ".claude/CLAUDE.md",
    ".codex/AGENTS.md",
)

def default_hot_target() -> Path:
    """猜一个宿主每次会话必读的文件，猜不到就退回家目录。"""
    for base in (Path.cwd(), Path.home()):
        for rel in HOST_MEMORY_CANDIDATES:
            candidate = base / rel
            if candidate.exists():
                return candidate
    return Path.home() / ".workbuddy" / "memory" / "MEMORY.md"

ROOT = resolve_root()
NOTES = ROOT / "notes"
INDEX_PATH = ROOT / "index.json"
EVENTS = ROOT / "events"

K1 = 1.5
B = 0.75
TITLE_BOOST = 2.5
PHRASE_BOOST = 2.0
TYPE_WEIGHT = {"procedure": 0.4, "lesson": 0.35, "fact": 0.2}

# 核心经验：同步进宿主每次会话必读的文件，保证确定生效
HOT_START = "<!-- MEMORY_HOT:START -->"
HOT_END = "<!-- MEMORY_HOT:END -->"
HOT_TYPE_SCORE = {"procedure": 3.0, "fact": 2.5, "lesson": 1.5}
NARROW_TAGS = {
    "命令", "工具", "环境", "排查", "插件", "架构", "沙箱", "移植", "自动收割", "会话记录",
    "workbuddy", "mcp", "hooks", "skill", "python", "git", "claude", "codex", "dsh",
}

def is_cjk(cp: int) -> bool:
    return (
        0x3000 <= cp <= 0x303F or 0x3040 <= cp <= 0x30FF or 0x3400 <= cp <= 0x9FFF
        or 0xF900 <= cp <= 0xFAFF or 0xFF00 <= cp <= 0xFFEF or 0xAC00 <= cp <= 0xD7AF
    )

def tokenize(text: str, dedupe: bool = False):
    text = (text or "").lower()
    out: list[str] = []
    buf = ""
    for ch in text:
        if is_cjk(ord(ch)):
            if buf:
                out.extend(_latin(buf))
                buf = ""
            out.append(ch)
        elif ch.isalnum() or ch == "_":
            buf += ch
        else:
            if buf:
                out.extend(_latin(buf))
                buf = ""
    if buf:
        out.extend(_latin(buf))

    grams: list[str] = []
    for tok in out:
        if is_cjk(ord(tok[0])):
            grams.append(tok)
        else:
            grams.append(tok)
    # CJK 相邻字符补 2/3-gram
    seq = [t for t in out if is_cjk(ord(t[0]))]
    for i in range(len(seq) - 1):
        grams.append(seq[i] + seq[i + 1])
    for i in range(len(seq) - 2):
        grams.append(seq[i] + seq[i + 1] + seq[i + 2])
    return sorted(set(grams)) if dedupe else grams

def _latin(raw: str) -> list[str]:
    parts = []
    parts.append(raw)
    if "_" in raw:
        parts.extend(p for p in raw.split("_") if p)
    camel = re.findall(r"[a-z0-9]+|[A-Z][a-z0-9]*", raw)
    if len(camel) > 1:
        parts.extend(c.lower() for c in camel)
    return [p for p in parts if p]

def parse_note(path: Path) -> dict | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
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
    return {
        "id": str(meta.get("id", path.stem)),
        "type": str(meta.get("type", "fact")),
        "status": str(meta.get("status", "active")),
        "title": str(meta.get("title", path.stem)),
        "tags": meta.get("tags", []) if isinstance(meta.get("tags"), list) else [],
        "env": str(meta.get("env", "")),
        "created": str(meta.get("created", "")),
        "hot": str(meta.get("hot", "")),
        "source": str(meta.get("source", "")),
        "body": body.strip(),
        "path": str(path),
    }

def iter_notes():
    if not NOTES.exists():
        return []
    out = []
    for p in sorted(NOTES.rglob("*.md")):
        # 候选/归档是无决策的暂存与证据区，不参与正式索引（--all 也不含）
        if "/candidates/" in p.as_posix():
            continue
        note = parse_note(p)
        if note:
            out.append(note)
    return out

def _atomic_write(path, text: str, encoding: str = "utf-8") -> None:
    """原子写：tmp + os.replace，避免并发/中断留下截断文件。"""
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    try:
        tmp.write_text(text, encoding=encoding)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def build_index() -> dict:
    notes = iter_notes()
    postings: dict[str, dict[str, int]] = {}
    title_postings: dict[str, dict[str, int]] = {}
    docs: dict[str, dict] = {}
    for n in notes:
        body_tokens = tokenize(n["body"] + " " + " ".join(n["tags"]))
        title_tokens = tokenize(n["title"])
        for t in body_tokens:
            postings.setdefault(t, {}).setdefault(n["id"], 0)
            postings[t][n["id"]] += 1
        for t in title_tokens:
            title_postings.setdefault(t, {}).setdefault(n["id"], 0)
            title_postings[t][n["id"]] += 1
        docs[n["id"]] = {
            "id": n["id"], "type": n["type"], "status": n["status"], "title": n["title"],
            "tags": n["tags"], "env": n["env"], "created": n["created"], "path": n["path"],
            "hot": str(n.get("hot", "")),
            "source": str(n.get("source", "")),
            "body_len": len(body_tokens) or 1, "title_len": len(title_tokens) or 1,
            # 索引瘦身：不存正文全文，只存 smart snippet（详情按需读原文件）
            "snippet": _smart_snippet(n["body"]),
        }
    avg_body = sum(d["body_len"] for d in docs.values()) / len(docs) if docs else 1.0
    avg_title = sum(d["title_len"] for d in docs.values()) / len(docs) if docs else 1.0
    idx = {
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "doc_count": len(docs),
        "avg_body": avg_body, "avg_title": avg_title,
        "postings": postings, "title_postings": title_postings, "docs": docs,
    }
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(INDEX_PATH, json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    return idx

def load_index(force: bool = False) -> dict:
    if not force and INDEX_PATH.exists():
        try:
            # 笔记目录比索引文件新 → 说明有外部写入未 reindex，自动重建
            if NOTES.exists() and INDEX_PATH.exists():
                try:
                    newest_note = max(p.stat().st_mtime for p in NOTES.rglob("*.md"))
                    if newest_note > INDEX_PATH.stat().st_mtime + 1.0:
                        return build_index()
                except OSError:
                    pass
            return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return build_index()

def bm25_field(tf: int, df: int, total: int, doc_len: int, avg_len: float) -> float:
    idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
    denom = tf + K1 * (1 - B + B * doc_len / max(1.0, avg_len))
    return idf * (tf * (K1 + 1) / denom)

def _smart_snippet(body: str, n: int = 200) -> str:
    """关键句提取：优先取正文首个有效段落（非标题/列表行），比纯前 n 字更能代表要点。"""
    for seg in body.split("\n"):
        s = seg.strip()
        if len(s) > 8 and not s.startswith(("#", "-", "*", "```")):
            return " ".join(s.split())[:n]
    return " ".join(body.split())[:n]

# 查询 LRU 缓存（按索引 mtime 失效；借鉴 dsh-memoir 的 queryCache）
_QUERY_CACHE: dict = {}

def _search_impl(idx: dict, query: str, limit: int, include_all: bool) -> list[dict]:
    docs = idx.get("docs", {})
    if not docs:
        return []
    total = idx.get("doc_count", len(docs)) or 1
    qterms = tokenize(query, dedupe=True)
    if not qterms:
        return []
    postings = idx.get("postings", {})
    tpostings = idx.get("title_postings", {})
    avg_body = idx.get("avg_body", 1.0)
    avg_title = idx.get("avg_title", 1.0)
    q = " ".join(query.lower().split())

    scores: dict[str, float] = {}
    matched: dict[str, set] = {}
    for term in qterms:
        plist = postings.get(term, {})
        df = len(plist)
        # 语料统计停用词：仅当语料足够大时启用，否则小库会把关键词误杀
        if total >= 20 and df > total * 0.7:
            continue
        for did, tf in plist.items():
            scores[did] = scores.get(did, 0.0) + bm25_field(tf, df, total, docs[did]["body_len"], avg_body)
            matched.setdefault(did, set()).add(term)
        tlist = tpostings.get(term, {})
        for did, tf in tlist.items():
            scores[did] = scores.get(did, 0.0) + TITLE_BOOST * bm25_field(tf, len(tlist), total, docs[did]["title_len"], avg_title)
            matched.setdefault(did, set()).add(term)

    # 强信号规则：查询含拉丁/标识符词元（SQLite、xyzqwerty、gongwen…）时，
    # 若该词在语料中零命中 → 直接判定无命中。拉丁词区分度远高于中文常用字。
    # 注意必须同时检查标题索引：词仅出现在标题（正文未提及）时不得误杀（曾导致 GUI 等
    # 标题标识词搜索返回空）。大写归一在 tokenize 完成，postings 键为小写。
    latins = [t for t in qterms if not is_cjk(ord(t[0]))]
    if latins and all(len(postings.get(t, {})) == 0 and len(tpostings.get(t, {})) == 0 for t in latins):
        return []

    # 召回门槛：只统计"特异性词元"——非中文单字（≥2 字或拉丁/标识符）且
    # 出现在 ≤25% 文档中；至少命中其 34% 否则视为无命中。
    # 中文单字（不/全/存/在…）几乎每个文档都沾，不参与门槛统计，防止误召回。
    spec = [
        t for t in qterms
        if not (len(t) == 1 and is_cjk(ord(t[0])))
        and len(postings.get(t, {})) <= total * 0.25
    ]
    if spec:
        min_terms = max(1, int(len(spec) * 0.34))
    else:
        min_terms = len(qterms)  # 全是常见词：必须全命中

    results = []
    for did, score in scores.items():
        if len(matched.get(did, set())) < min_terms:
            continue
        d = docs[did]
        if not include_all and d["status"] != "active":
            continue
        hay = (d["title"] + " " + d.get("snippet", "")).lower()
        if q and q in " ".join(hay.split()):
            score += PHRASE_BOOST
        score += TYPE_WEIGHT.get(d["type"], 0.1)
        score += _recency_boost(d.get("created", ""), time.time())
        results.append({"id": did, "score": round(score, 3), "title": d["title"], "type": d["type"],
                        "status": d["status"], "tags": d["tags"], "env": d["env"], "created": d["created"],
                        "snippet": d.get("snippet", "")[:180]})
    results.sort(key=lambda r: (-r["score"], r["id"]))
    return results[:limit]

def search(idx: dict, query: str, limit: int = 5, include_all: bool = False) -> list[dict]:
    """检索（带查询 LRU 缓存，索引 mtime 变化自动失效）。"""
    try:
        m = INDEX_PATH.stat().st_mtime
    except OSError:
        m = 0.0
    key = (query, limit, include_all)
    hit = _QUERY_CACHE.get(key)
    if hit and hit[0] == m:
        return hit[1]
    results = _search_impl(idx, query, limit, include_all)
    _QUERY_CACHE[key] = (m, results)
    if len(_QUERY_CACHE) > 256:
        _QUERY_CACHE.pop(next(iter(_QUERY_CACHE)))
    return results

def slugify(text: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text).strip("-")
    return (s[:30] or "note").lower()

def _recency_boost(created: str, now_ts: float) -> float:
    """新近度小加权（≤0.6）：半年内笔记按年龄线性衰减，新的略优先。"""
    try:
        t = time.mktime(time.strptime(str(created)[:10], "%Y-%m-%d"))
    except (ValueError, TypeError):
        return 0.0
    age_d = max(0.0, (now_ts - t) / 86400.0)
    if age_d > 180:
        return 0.0
    return 0.6 * (1.0 - age_d / 180.0)

def token_estimate(text: str) -> int:
    """token 粗估（借鉴 dsh-memoir selector）：CJK≈1 token，其他≈4 字符/token。"""
    t = 0.0
    for ch in text:
        t += 1.0 if is_cjk(ord(ch)) else 0.25
    return max(1, int(t))

# ============ 热层保护（L3）============
# 自动收割转正的笔记未经人工确认，质量参差（命令碎片/半截方案）；
# 让它们自动补足进热层会稀释上下文、挤掉真正救命的经验。默认不入选，人工 pin 或 --include-auto 才放行。
AUTO_SOURCE_HINTS = ("自动收割", "自动提炼", "harvest", "auto_promote")


def is_auto_source(d: dict) -> bool:
    src = str(d.get("source") or "")
    return any(h in src for h in AUTO_SOURCE_HINTS)


def select_hot(idx: dict, limit: int, auto_fill: bool = False,
               include_auto: bool = False) -> tuple[list[tuple[float, dict, bool]], int]:
    """挑选核心经验：只装"行动时能直接救命"的知识。

    人工在 frontmatter 标 hot: true 的优先入选；不足上限时才用算法补足，
    并标记 pinned=False 以便输出时区分。宁少勿多，热层挤占上下文就失效了。
    自动收割来源默认不参与补足（热层保护），返回 (入选, 被保护排除的条数)。
    """
    docs = idx.get("docs", {})
    scored = []
    skipped_auto = 0
    for d in docs.values():
        if d.get("status") != "active":
            continue
        pinned = str(d.get("hot", "")).lower() in ("true", "1", "yes")
        if not pinned and not include_auto and is_auto_source(d):
            skipped_auto += 1
            continue
        s = 100.0 if pinned else 0.0
        s += HOT_TYPE_SCORE.get(d.get("type", "fact"), 1.0)
        tags = {str(t).lower() for t in (d.get("tags") or [])}
        if tags & NARROW_TAGS:
            s += 1.0
        if d.get("env"):
            s += 0.2
        scored.append((s, d, pinned))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    picks = [x for x in scored if x[2]]
    if auto_fill and len(picks) < limit:
        picks += [x for x in scored if not x[2]][: limit - len(picks)]
    return picks[:limit], skipped_auto

def digest_of(d: dict, n: int = 45) -> str:
    body = " ".join((d.get("snippet") or "").split())
    if len(body) <= n:
        return body
    cut = body[:n]
    # 别在路径或标识符中间截断，回退到最近的标点或空格
    for sep in ("。", "；", "，", "、", "：", " "):
        pos = cut.rfind(sep)
        if pos > n * 0.5:
            return cut[:pos].rstrip("，；：、") + "…"
    return cut + "…"

# ==================== 分层清理（L4 Retention / GC）====================
# 设计前提：记忆不是日志，"删"永远比"留"危险——漏掉一条关键经验的成本，
# 远高于多存 2MB 文本。因此清理只做三件事：分层降级、汇总压缩、冷存打包；
# 默认不删原文，只有显式 --prune 才删，且删前必有摘要与冷存包。
#
#   T0 热层视图     ：只读视图，不清理
#   T1 正式笔记     ：永不自动删除；只报告状态分布（suspect/superseded 交人工）
#   T2 候选池       ：超期（默认 60 天）移入归档区——可逆，文件保留
#   T3 归档区（冷） ：超期（180 天）/ 超量（1000 条）/ 超容（200MB）→ 先写汇总摘要保住可检索性，
#                     再打包冷存 zip，仅 --prune 才删原文
#   T4 证据流       ：超期（90 天）按月 gzip 压缩；当月文件只生成压缩快照，绝不删原文
GC_CAND_DAYS = 60
GC_ARCHIVE_DAYS = 180
GC_ARCHIVE_MAX = 1000
GC_ARCHIVE_BYTES = 200 * 1024 * 1024
GC_EVENT_DAYS = 90
# 保护标记：frontmatter 里带这些的条目永不被清理（人工认可过的重要记忆）
GC_PROTECT_KEYS = ("hot: true", "keep: true", "protect: true", "pin: true")


def gc_is_protected(text: str) -> bool:
    head = str(text or "")[:800].lower()
    return any(k in head for k in GC_PROTECT_KEYS)


def gc_file_age_days(p: Path, now: float) -> float:
    try:
        return (now - p.stat().st_mtime) / 86400.0
    except OSError:
        return 0.0


def gc_month_of(p: Path, d: dict | None) -> str:
    """归档批次归属月份：优先 frontmatter 的 created，回退文件 mtime。"""
    created = str((d or {}).get("created") or "")[:7]
    if re.fullmatch(r"\d{4}-\d{2}", created):
        return created
    try:
        return time.strftime("%Y-%m", time.localtime(p.stat().st_mtime))
    except OSError:
        return time.strftime("%Y-%m")


def gc_write_summary(items: list[tuple[Path, dict]], month: str, out_dir: Path) -> Path:
    """冷存前先写汇总摘要——压缩后仍可按标题/关键词检索，避免"清了等于忘了"。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"SUMMARY-{month}.md"
    now_s = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# 归档冷存摘要 {month}", "",
        f"- 生成时间：{now_s}",
        f"- 条目数：{len(items)}",
        "- 说明：由 `mem.py gc --apply` 在冷存打包前自动生成；原文已打包至 `_cold/`，"
        "保留本摘要即可按标题/类型/创建日期检索到条目所在冷存包。", "",
        "| id | 类型 | 标题 | 创建 |", "|---|---|---|---|",
    ]
    for p, d in items:
        title = re.sub(r"^\[候选\]\s*", "", str(d.get("title") or p.stem))
        title = title.replace("|", "/").replace("\n", " ")[:60]
        lines.append(f"| {d.get('id') or p.stem} | {d.get('type') or '?'} | {title} | {d.get('created') or '?'} |")
    # 任务级条目含"任务目标/踩坑/最终方案"，价值远高于命令碎片 → 摘要里保留要点
    task_items = [(p, d) for p, d in items
                  if str(d.get("title") or "").startswith(TASK_TITLE_PREFIX)]
    if task_items:
        lines += ["", f"## 任务级条目要点（{len(task_items)} 条）", ""]
        for p, d in task_items[:50]:
            body = str(d.get("body") or "")
            goal = _between(body, "任务目标：", "")
            plan = _between(body, "最终方案：", "")
            plan = re.sub(r"\s+", " ", plan)[:200]
            lines.append(f"- **{re.sub(r'^\[候选\] 任务经验：', '', str(d.get('title') or ''))}**")
            if goal:
                lines.append(f"  - 目标：{goal[:120]}")
            if plan:
                lines.append(f"  - 方案：{plan}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def _between(text: str, start: str, end: str) -> str:
    """取 `start` 之后的内容；若其后是 ``` 代码块，取代码块正文（跳过围栏本身）。"""
    i = text.find(start)
    if i < 0:
        return ""
    rest = text[i + len(start):].lstrip("\n")
    if rest.startswith("```"):
        rest = rest[3:].lstrip("\n")
        j = rest.find("```")
        return (rest[:j] if j > 0 else rest).strip()
    if end:
        j = rest.find(end)
        if j > 0:
            return rest[:j].strip()
    j = rest.find("\n")
    return (rest[:j] if j > 0 else rest).strip()


def gc_pack(items: list[tuple[Path, dict]], zip_path: Path) -> int:
    """打包冷存（zip deflate，stdlib 零依赖）。"""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p, _ in items:
            try:
                z.write(p, p.name)
                n += 1
            except OSError:
                continue
    return n


def gc_gzip(src: Path, dst: Path) -> int:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as fi, gzip.open(dst, "wb") as fo:
        shutil.copyfileobj(fi, fo)
    try:
        return dst.stat().st_size
    except OSError:
        return 0


def gc_t3_batch(arch_rows: list, keep_n: int, trig_size: bool, now: float) -> list:
    """T3 冷存批次选择：保留最新 keep_n 条可热查，返回应冷存的最老一批。

    独立成函数便于单测（曾因切片方向写反：冷存了最新一批，--prune 会删错对象）。
    """
    ordered = sorted(arch_rows, key=lambda r: -gc_file_age_days(r[0], now))  # 最老在前
    batch = ordered[: max(0, len(ordered) - keep_n)]
    if trig_size and not batch:
        batch = ordered[: max(1, len(ordered) // 4)]
    return batch


def cmd_gc(args) -> int:
    """分层清理体检：默认 dry-run 只报告，--apply 才动文件，--prune 才删原文。"""
    now = time.time()
    apply = bool(args.apply)
    prune = bool(args.prune) and apply
    cand_dir = NOTES / "candidates"
    archive_dir = cand_dir / "archive"
    cold_dir = archive_dir / "_cold"
    sum_dir = archive_dir / "_summaries"

    print("=" * 62)
    print("恒忆分层清理体检（Retention / GC）"
          + ("【dry-run，未改动任何文件】" if not apply else ("【执行模式" + (" + 删除原文】" if prune else "（只压缩不删）】"))))
    print("=" * 62)

    # ---- T1 正式笔记：永不自动清理，只报告 ----
    idx = load_index(force=bool(args.reindex))
    docs = idx.get("docs", {})
    stat: dict[str, int] = {}
    for d in docs.values():
        stat[d.get("status", "?")] = stat.get(d.get("status", "?"), 0) + 1
    print(f"\n[T1 正式笔记] {len(docs)} 条  分布：" +
          "  ".join(f"{k}={v}" for k, v in sorted(stat.items())))
    print("   策略：永不自动删除。suspect/superseded 只提示人工复核（状态可逆）。")
    stale = [d for d in docs.values() if d.get("status") in ("suspect", "superseded", "archived")]
    if stale:
        print(f"   待人工复核：{len(stale)} 条（mem.py set-status 可改回 active）")

    # ---- T2 候选池：超期滚动进归档区 ----
    cand_files = sorted(cand_dir.glob("cand-*.md")) if cand_dir.exists() else []
    cand_rows = []
    for p in cand_files:
        d = parse_note(p) or {}
        cand_rows.append((p, d, cand_age_days(str(d.get("created", "")), now)))
    over = [r for r in cand_rows if r[2] >= args.cand_days]
    print(f"\n[T2 候选池] {len(cand_rows)} 条（上限 {DEFAULT_CAND_CAP}）"
          f"　≥{args.cand_days} 天未处理：{len(over)} 条")
    if over and apply:
        archive_dir.mkdir(parents=True, exist_ok=True)
        moved = 0
        for p, d, age in over:
            try:
                p.rename(archive_dir / p.name)
                moved += 1
            except OSError:
                continue
        print(f"   已滚动归档 {moved} 条 → candidates/archive/（文件保留，未删除）")
        cand_rows = [r for r in cand_rows if r[2] < args.cand_days]
    elif over:
        print(f"   dry-run：将滚动归档 {len(over)} 条（加 --apply 执行）")

    # ---- T3 归档区（冷存）：超期/超量/超容触发 ----
    arch_files = sorted(archive_dir.glob("*.md")) if archive_dir.exists() else []
    arch_bytes = sum(p.stat().st_size for p in arch_files) if arch_files else 0
    arch_rows = []
    protected = []
    for p in arch_files:
        try:
            raw = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        d = parse_note(p) or {}
        if gc_is_protected(raw):
            protected.append(p)
            continue
        arch_rows.append((p, d))
    oldest = max((gc_file_age_days(p, now) for p, _ in arch_rows), default=0.0)
    trig_age = [r for r in arch_rows if gc_file_age_days(r[0], now) >= args.archive_days]
    trig_cnt = len(arch_rows) >= args.archive_max
    trig_size = arch_bytes >= args.archive_bytes
    print(f"\n[T3 归档区] {len(arch_files)} 条 / {arch_bytes / 1024 / 1024:.1f}MB"
          f"　最老 {oldest:.0f} 天　受保护 {len(protected)} 条")
    print(f"   触发条件：≥{args.archive_days} 天({len(trig_age)} 条) "
          f"| 条数 ≥{args.archive_max}({len(arch_rows)}) "
          f"| 容量 ≥{args.archive_bytes / 1024 / 1024:.0f}MB({arch_bytes / 1024 / 1024:.1f}MB)")
    batch: list[tuple[Path, dict]] = []
    if trig_cnt or trig_size:
        # 数量/容量触发：按"最老优先"取超出部分，而不是一刀切清光
        keep_n = len(arch_rows)
        if trig_cnt:
            keep_n = min(keep_n, int(args.archive_max * 0.8))
        ordered = sorted(arch_rows, key=lambda r: -gc_file_age_days(r[0], now))  # 最老在前
        # 保留最新 keep_n 条可热查，冷存超出部分（最老的一批）。
        # 原实现取 ordered[keep_n:]（尾部=最新）与注释/打印相反，--prune 会删掉最新归档，已修复。
        batch = gc_t3_batch(arch_rows, keep_n, trig_size, now)
        print(f"   命中：条数或容量超限 → 冷存 {len(batch)} 条（保留最新 {len(arch_rows) - len(batch)} 条可热查）")
    elif trig_age:
        batch = trig_age
        print(f"   命中：超期 ≥{args.archive_days} 天 → 冷存 {len(batch)} 条")
    else:
        print("   未触发：归档区仍在阈值内，无需冷存。")
    if batch:
        by_month: dict[str, list[tuple[Path, dict]]] = {}
        for p, d in batch:
            by_month.setdefault(gc_month_of(p, d), []).append((p, d))
        for month, items in sorted(by_month.items()):
            zp = cold_dir / f"cold-{month}.zip"
            print(f"   · {month}：{len(items)} 条 → 摘要 _summaries/SUMMARY-{month}.md + 冷存 {zp.name}")
            if apply:
                sp = gc_write_summary(items, month, sum_dir)
                n = gc_pack(items, zp)
                print(f"     已写摘要 {sp.name}；已打包 {n} 条 "
                      f"({zp.stat().st_size / 1024:.0f}KB)" if zp.exists() else "")
                if prune:
                    for p, _ in items:
                        try:
                            p.unlink()
                        except OSError:
                            continue
                    print(f"     --prune：已删除原文 {len(items)} 条（冷存包与摘要仍在）")
                else:
                    print("     未删原文（加 --prune 才删；默认只压缩不删，风险可控）")

    # ---- T4 证据流：超期压缩 ----
    ev_files = sorted(EVENTS.glob("*.jsonl")) if EVENTS.exists() else []
    ev_bytes = sum(p.stat().st_size for p in ev_files) if ev_files else 0
    print(f"\n[T4 证据流] {len(ev_files)} 个文件 / {ev_bytes / 1024 / 1024:.1f}MB（append-only 原始证据）")
    for p in ev_files:
        age = gc_file_age_days(p, now)
        if age < args.event_days:
            print(f"   · {p.name}：{age:.0f} 天（未超期，保留原文）")
            continue
        dst = EVENTS / "archive" / f"{p.stem}.jsonl.gz"
        if apply:
            size = gc_gzip(p, dst)
            print(f"   · {p.name}：{age:.0f} 天 → 已压缩 {dst.name}（{size / 1024:.0f}KB）"
                  + ("，原文已删除" if prune else "，原文保留（加 --prune 才删）"))
            if prune:
                try:
                    p.unlink()
                except OSError:
                    pass
        else:
            print(f"   · {p.name}：{age:.0f} 天 → dry-run 将压缩为 {dst.name}")

    print("\n" + "-" * 62)
    print("保障：① 受保护条目（hot/keep/protect/pin）永不清理；"
          "② 冷存前必写摘要，压缩不等于失忆；"
          "③ 默认只压缩不删，--prune 才删原文；"
          "④ 正式笔记永不自动删，只降级状态。")
    if not apply:
        print("\n[dry-run] 未改动任何文件。确认无误后加 --apply（需要连带删原文再加 --prune）。")
    return 0


# ==================== 使用画像导出（L5）====================
# 场景：换一个 AI 工具/新开会话时，需要一份"我是谁、我怎么要求你"的简短画像随身带。
# 原则：本地生成、只挑已有依据的条目、保留原表述；没依据的维度明确说"无覆盖"，
#       绝不用模型印象补齐——宁可少一条，不可编一条。
PROFILE_CATEGORIES = ("指令", "身份", "职业", "项目", "偏好")
# 命中权重：标签是人工打的，可信度最高；标题次之；正文片段噪声太大不参与，
# 否则"我/工作/要求"这类泛词会把所有笔记都算成命中，画像失去区分度。
PROFILE_HINTS = {
    "指令": ("纪律", "规范", "准则", "禁令", "规则", "流程", "必读", "工作纪律", "checklist", "清单"),
    "身份": ("身份", "单位", "部门", "处室", "任职", "本人"),
    # 注：不用"角色/岗位"这类泛词——"多角色评审""岗位技能"会被误判进身份维度。
    "职业": ("职业", "职责", "业务", "公文", "应急", "信息化", "科信", "写作"),
    "项目": ("项目", "工程", "系统", "平台", "赛事", "运动会", "指挥中心", "恒忆", "gongwen"),
    "偏好": ("偏好", "习惯", "风格", "模板", "格式", "输出", "preference"),
}
PROFILE_TAG_WEIGHT = 3
PROFILE_TITLE_WEIGHT = 1


def profile_pick(idx: dict, limit: int) -> dict[str, list[tuple[str, str]]]:
    """按分类启发式从本地笔记里挑画像条目：返回 {分类: [(日期, 条目)]}。

    只看 active 笔记；每类取分最高的若干条。命中依据是标签/标题关键词，属"候选"，
    输出时会标注需人工确认——画像要带得出去，就不能有编造成分。
    """
    out: dict[str, list[tuple[str, str]]] = {k: [] for k in PROFILE_CATEGORIES}
    scored: dict[str, list[tuple[int, str, str]]] = {k: [] for k in PROFILE_CATEGORIES}
    for d in idx.get("docs", {}).values():
        if d.get("status") != "active":
            continue
        tags = " ".join(str(t) for t in (d.get("tags") or []))
        title_raw = re.sub(r"^\[候选\]\s*", "", str(d.get("title") or "")).strip()
        date = str(d.get("created") or "")[:10] or "[unknown]"
        for cat, hints in PROFILE_HINTS.items():
            hit = (sum(1 for h in hints if h in tags) * PROFILE_TAG_WEIGHT
                   + sum(1 for h in hints if h in title_raw) * PROFILE_TITLE_WEIGHT)
            if hit:
                scored[cat].append((hit, date, title_raw[:70]))
    for cat in PROFILE_CATEGORIES:
        scored[cat].sort(key=lambda x: (-x[0], x[1]))
        out[cat] = [(dt, tl) for _, dt, tl in scored[cat][:limit]]
    return out


def cmd_profile(args) -> int:
    idx = load_index(force=args.reindex)
    picks = profile_pick(idx, args.limit)
    lines = ["# 使用画像（恒忆本地草稿）", "",
             f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"- 数据来源：本地恒忆笔记 {len(idx.get('docs', {}))} 条（全部本地，未联网）",
             "- 用法：整段复制到新工具/新会话开头，或交给 LLM 按同样格式续写",
             ""]
    body: list[str] = []
    empty = []
    for cat in PROFILE_CATEGORIES:
        items = picks.get(cat) or []
        if not items:
            empty.append(cat)
            continue
        body.append(f"## {cat}")
        for dt, tl in items:
            body.append(f"[{dt}] - {tl}")
        body.append("")
    block = "\n".join(body).rstrip()
    lines += ["```markdown", block, "```", ""]
    lines.append("## 覆盖率说明（务必先读）")
    lines.append("")
    if empty:
        lines.append(f"- 本地无依据、未生成的维度：{'、'.join(empty)}。"
                     "这些维度请你自己补（尤其是「指令」与「偏好」——工具只能看到你写进笔记的部分）。")
    else:
        lines.append("- 五个维度均有本地条目支撑，但仍建议人工过一遍：")
    lines.append("- 上表条目是按标签/关键词从笔记里挑的**候选**，请删掉不准确的、补上你真正在意的。")
    lines.append("- 画像的价值在于「原话保留」：条目尽量用你自己的说法，别让模型改写。")
    lines.append("- 想让下一份画像更准：把常用要求写成 fact 笔记（`mem.py add`），画像会自动带出来。")
    text = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已写入 {args.out}（{len(text)} 字符，{sum(len(v) for v in picks.values())} 条候选）")
        return 0
    print(text)
    return 0


def cmd_hot(args) -> int:
    idx = load_index(force=args.reindex)
    picks, skipped_auto = select_hot(idx, args.limit, auto_fill=args.auto_fill,
                                     include_auto=getattr(args, "include_auto", False))
    if not picks:
        print("没有 active 笔记可同步。")
        return 0
    lines = [HOT_START, "## 核心经验（自动生成，勿手改；改笔记后重跑 mem.py hot --apply）", ""]
    auto = 0
    budget = args.tokens if args.tokens and args.tokens > 0 else 0
    used = 0
    if budget:
        # 预算策略：人工精选 pinned 全部保留；非 pinned 按序装入直到预算满（硬顶）
        pinned_lines, other_lines = [], []
        for s, d, pinned in picks:
            if not pinned:
                auto += 1
            line = f"- ({d['type']}) {d['title']}：{digest_of(d, args.digest)}"
            (pinned_lines if pinned else other_lines).append(line)
        lines += pinned_lines
        used = sum(token_estimate(l) for l in pinned_lines)
        for line in other_lines:
            est = token_estimate(line)
            if used + est > budget:
                break
            lines.append(line)
            used += est
    else:
        for s, d, pinned in picks:
            if not pinned:
                auto += 1
            lines.append(f"- ({d['type']}) {d['title']}：{digest_of(d, args.digest)}")
    lines += ["", HOT_END]
    block = "\n".join(lines)

    if not args.apply:
        print(block)
        print(f"\n[dry-run] 共 {len(picks)} 条（其中自动补足 {auto} 条），未写入。"
              + (f" 热层保护排除自动收割 {skipped_auto} 条。" if skipped_auto else "")
              + (f"token 预算 {budget}，已用 {used}。" if budget else "")
              + " 加 --apply 写入目标文件。")
        return 0

    target = Path(args.target) if args.target else default_hot_target()
    if not target.exists():
        print(f"目标文件不存在：{target}", file=sys.stderr)
        return 1
    text = target.read_text(encoding="utf-8")
    if HOT_START in text and HOT_END in text:
        pre, _, rest = text.partition(HOT_START)
        _, _, post = rest.partition(HOT_END)
        new = pre + block + post
    else:
        new = text.rstrip() + "\n\n" + block + "\n"
    _atomic_write(target, new)
    print(f"已同步 {len(picks)} 条核心经验 → {target}"
          + (f"（热层保护排除自动收割 {skipped_auto} 条，人工 pin 或 --include-auto 可放行）"
             if skipped_auto else ""))
    return 0

DEFAULT_CAND_CAP = 50

def cand_age_days(created: str, now: float) -> int:
    try:
        t = time.mktime(time.strptime(str(created)[:10], "%Y-%m-%d"))
        return max(0, int((now - t) // 86400))
    except Exception:
        return 0

VERDICT_LABEL = {"promote": "推荐转正", "keep": "保留观察", "archive": "建议归档", "archive_dup": "重复归档"}

def cand_score(d: dict, idx: dict) -> dict:
    """本地启发式候选评分（AI 审核第一层，零依赖）：返回 0-100 分与建议。

    依据：与 active 笔记的相似度（与写前治理同源）、标题质量、正文信息完整度、
    类型信号（教训类含失败细节）、命令上下文完整性。分数仅供参考，人工终审为准。
    """
    reasons: list[str] = []
    score = 50.0
    title = str(d.get("title", ""))
    body = str(d.get("body", ""))
    ntype = str(d.get("type", "fact"))
    sim, sim_id = 0.0, ""
    if title:
        try:
            hits = search(idx, title[:60], limit=3, include_all=True)
            for h in hits:
                if h["id"] == d.get("id") or h["status"] != "active":
                    continue
                if h["score"] > sim:
                    sim, sim_id = h["score"], h["id"]
        except Exception:
            pass
    if sim >= 25:
        score -= 30
        reasons.append(f"疑似重复 active 笔记（{sim_id}，相似 {sim:.0f}）")
    elif sim >= 18:
        score -= 15
        reasons.append(f"与 active 笔记相似（{sim_id}，相似 {sim:.0f}），建议核实")
    has_ph = bool(re.search(r"<[a-z]+>|<str>|<path>|<n>|<N>", title))
    if has_ph and len(body) < 120:
        score -= 15
        reasons.append("标题含占位符且正文简短，信息量不足")
    elif len(title) < 10:
        score -= 8
        reasons.append("标题过短")
    if not body.strip():
        score -= 15
        reasons.append("正文为空")
    elif len(body) < 80:
        score -= 8
        reasons.append("正文过短")
    if "失败后成功" in title or "失败后成功" in body:
        score += 12
        reasons.append("含失败→成功完整路径，价值较高")
    elif "反复失败" in title or "反复失败" in body:
        score -= 8
        reasons.append("重复失败的碎片记录，未收敛为可复用配方")
    elif ntype == "lesson" and ("失败" in body or "Error" in body):
        score += 5
        reasons.append("教训类含失败细节")
    m = re.search(r"失败次数[:：]\s*(\d+)", body)
    if m and int(m.group(1)) >= 1:
        score += 3
    if "命令签名" in body and len(re.sub(r"<[^>]+>", "", body)) > 200:
        score += 10
        reasons.append("含完整命令上下文")
    elif len(re.sub(r"<[^>]+>", "", body)) > 400:
        score += 5
        reasons.append("正文信息量充足")
    if sim >= 25:
        verdict = "archive_dup"
    elif score >= 70:
        verdict = "promote"
    elif score >= 45:
        verdict = "keep"
    else:
        verdict = "archive"
    return {"score": round(score), "verdict": verdict, "verdict_label": VERDICT_LABEL[verdict],
            "reasons": reasons, "sim_id": sim_id, "sim": round(sim, 1)}

# ============ 多角色评判（参考 UZI-Skill 多角色评审团：独立打分→引用规则→加权共识→critical 否决） ============
AUTO_REVIEW_LOG = "events/auto-review.jsonl"
RECALL_LOG = "events/recall-log.jsonl"
AUTO_PROMOTE_TOTAL = 78      # 自动转正总分阈值（强共识）
AUTO_PROMOTE_PASS = 4        # 至少通过的独立角色数
ROLES = [
    ("quality", "质量官", 0.20), ("tech", "技术官", 0.20), ("compliance", "合规官", 0.15),
    ("value", "价值官", 0.20), ("novelty", "新颖官", 0.15), ("ops", "实操官", 0.10),
]
_SENSITIVE_HINTS = ("涉密", "密级", "公安内网", "身份证", "手机号", "密码:", "token=", "apikey", "sk-")
_DANGER_CMDS = ("rm -rf", "del /s", "format ", "DROP TABLE", "--force")

def _role_verdict(score: float) -> str:
    return "pass" if score >= 70 else ("veto" if score < 45 else "doubt")

def role_quality(d: dict) -> dict:
    """质量官：结构完整、标题有效、正文信息量。"""
    rules, score = [], 50.0
    title, body = str(d.get("title", "")), str(d.get("body", ""))
    if all(k in d for k in ("id", "type", "status", "title")):
        score += 15; rules.append("frontmatter 四要素齐全")
    if len(title) >= 12 and not re.search(r"^\[候选\]\s*\S+：[<\"<]", title[:20]):
        score += 10; rules.append("标题可读")
    if len(body) >= 120:
        score += 15; rules.append("正文 ≥120 字")
    elif len(body) < 60:
        score -= 20; rules.append("正文过短(<60)")
    if "命令签名" in body and len(re.sub(r"<[^>]+>", "", body)) > 200:
        score += 10; rules.append("含完整命令上下文")
    plain = re.sub(r"<[^>]+>", "", body).strip()
    if not plain:
        return {"score": 0, "verdict": "veto", "rules": ["正文为空 → 质量否决"]}
    if len(plain) < 12:
        return {"score": 0, "verdict": "veto", "rules": [f"有效正文过短({len(plain)}字) → 质量否决"]}
    return {"score": round(score), "verdict": _role_verdict(score), "rules": rules[:3]}

def role_tech(d: dict) -> dict:
    """技术官：做法真实可执行、无危险操作、有有效输出。"""
    rules, score = [], 50.0
    body = str(d.get("body", ""))
    if "命令签名" in body and "首次命令" in body:
        score += 20; rules.append("命令签名+首次命令齐备")
    if "失败输出片段" in body and len(re.sub(r"<[^>]+>", "", body)) > 150:
        score += 15; rules.append("含失败输出片段可诊断")
    if "随后成功命令" in body:
        score += 15; rules.append("含失败→成功完整路径")
    if "Error" in body or "错误" in body or "FAIL" in body:
        score += 5; rules.append("含错误信号")
    for dc in _DANGER_CMDS:
        if dc in body:
            score -= 40; rules.append(f"含危险命令({dc}) → 高怀疑")
    return {"score": round(score), "verdict": _role_verdict(score), "rules": _order_rules(rules)}

def _order_rules(rules: list[str]) -> list[str]:
    """规则排序：致否/危险规则排前。

    rules[:3] 截断与"否决原因取 rules[0]"都会只看前几条；若把加分项排在最前，
    真正的否决理由（危险命令、敏感、重复）就被藏住了——人看到的会是误导性原因。
    """
    bad = ("危险", "敏感", "否决", "重复", "过短", "为空", "无信息", "占位符占比过高")
    return sorted(rules, key=lambda s: 0 if any(k in s for k in bad) else 1)[:3]


def _veto_reason(r: dict) -> str:
    rules = r.get("rules") or []
    bad = ("危险", "敏感", "否决", "重复", "过短", "为空", "无信息", "占位符占比过高")
    for ru in rules:
        if any(k in ru for k in bad):
            return ru
    return rules[0] if rules else "(无明细)"


def role_compliance(d: dict) -> dict:
    """合规官：去敏检查，严重未去敏/敏感信息 → 一票否决。"""
    rules, score = [], 60.0
    body = str(d.get("body", "")) + " " + str(d.get("title", ""))
    ph = len(re.findall(r"<[^>]+>", body))
    plain = len(re.sub(r"<[^>]+>", "", body))
    ratio = ph / max(1, ph + plain)
    if ratio > 0.5:
        score -= 30; rules.append(f"占位符占比过高({ratio:.0%})")
    else:
        score += 20; rules.append(f"去敏充分（占位符 {ratio:.0%}）")
    hit = [k for k in _SENSITIVE_HINTS if k.lower() in body.lower()]
    if hit:
        return {"score": 0, "verdict": "veto", "rules": [f"检出敏感特征({hit[0]}) → 合规否决"]}
    if ph and plain < 80:
        return {"score": 15, "verdict": "doubt", "rules": ["几乎全是占位符，信息不可用"]}
    return {"score": round(score), "verdict": _role_verdict(score), "rules": rules[:3]}

def role_value(d: dict) -> dict:
    """价值官：未来可复用、通用而非一次性。"""
    rules, score = [], 50.0
    title = str(d.get("title", ""))
    body = str(d.get("body", ""))
    if "成功配方" in title:
        score += 15; rules.append("配方类（成功配方）")
    elif "反复失败" in title:
        score -= 15; rules.append("反复失败的碎片，未收敛")
    elif "失败后成功" in title:
        score += 10; rules.append("失败→成功路径")
    if re.search(r"\b(python|node|git|pip|npm|curl|ssh|scp|mem\.py|harvest|backup)\b", body):
        score += 10; rules.append("含通用工具命令，可迁移复用")
    if re.search(r"临时|Temp|temp|AppData/Local", body):
        score -= 10; rules.append("涉及临时目录，可能为一次性操作")
    return {"score": round(score), "verdict": _role_verdict(score), "rules": rules[:3]}

def role_novelty(d: dict, idx: dict) -> dict:
    """新颖官：与现有 active 笔记的相似度（重复不转正）。用命令签名做指纹，避免同类标题误伤。

    任务级经验候选（harvest 任务级提炼产出，title 以"[候选] 任务经验"开头）特殊处理：
    它们代表"某个任务怎么做成功"的过程经验，收割端已按任务签名去重；与现有笔记
    "主题相近"≠"内容重复"（政务任务标题命中政务知识笔记是常态），因此只轻微降分提示，
    不触发重复否决——避免任务经验被误归档（曾实测 24/24 条全部被 novelty 误杀）。
    """
    rules, score = [], 70.0
    title = str(d.get("title", ""))
    body = str(d.get("body", ""))
    is_task = title.startswith("[候选] 任务经验")
    q = title
    m = re.search(r"命令签名[:：]\s*(.+)", body)
    if m and len(m.group(1).strip()) >= 8:
        q = m.group(1).strip()[:80]
    sim, sim_id = 0.0, ""
    if q:
        try:
            for h in search(idx, q, limit=3, include_all=True):
                if h["id"] == d.get("id") or h["status"] != "active":
                    continue
                if h["score"] > sim:
                    sim, sim_id = h["score"], h["id"]
        except Exception:
            pass
    if sim >= 25:
        if is_task:
            score -= 15
            rules.append(f"与现有笔记主题相近({sim:.0f}，{sim_id})，任务经验不判重复")
        else:
            score -= 50; rules.append(f"与 active 笔记高度相似({sim:.0f}:{sim_id}) → 重复候选")
    elif sim >= 18:
        score -= 20; rules.append(f"与现有笔记相近({sim:.0f}，{sim_id})")
    else:
        score += 15; rules.append("无显著重复，具新颖性")
    return {"score": round(score), "verdict": _role_verdict(score), "rules": rules[:3], "sim_id": sim_id}

def role_ops(d: dict) -> dict:
    """实操官：失败信号有效、收敛完整。"""
    rules, score = [], 50.0
    title, body = str(d.get("title", "")), str(d.get("body", ""))
    m = re.search(r"失败次数[:：]\s*(\d+)", body)
    if m and int(m.group(1)) >= 1:
        score += 10; rules.append("记录失败次数")
    if "随后成功命令" in body:
        score += 20; rules.append("失败后收敛为成功路径（完整）")
    elif "反复失败" in title:
        score -= 15; rules.append("反复失败未收敛")
    if "来源 callId" in body:
        score += 10; rules.append("可回溯证据（callId）")
    return {"score": round(score), "verdict": _role_verdict(score), "rules": rules[:3]}

def multi_role_review(d: dict, idx: dict) -> dict:
    """六角色评审：独立打分（引用规则）→ 加权共识 → critical 否决 → 分档判定。"""
    _weights = {k: w for k, _, w in ROLES}
    roles = [
        ("quality", "质量官", role_quality(d)),
        ("tech", "技术官", role_tech(d)),
        ("compliance", "合规官", role_compliance(d)),
        ("value", "价值官", role_value(d)),
        ("novelty", "新颖官", role_novelty(d, idx)),
        ("ops", "实操官", role_ops(d)),
    ]
    total = round(sum(r["score"] * _weights[k] for k, _, r in roles) / sum(_weights.values()), 1)
    passes = sum(1 for _, _, r in roles if r["verdict"] == "pass")
    veto = [(name, _veto_reason(r)) for name, _, r in roles if r["verdict"] == "veto"]
    if veto:
        verdict, label = "reject", f"否决：{veto[0][0]}｜{veto[0][1][:30]}"
    elif total >= AUTO_PROMOTE_TOTAL and passes >= AUTO_PROMOTE_PASS:
        verdict, label = "promote", "自动转正（强共识）"
    elif total >= 50:
        verdict, label = "keep", "保留观察"
    else:
        verdict, label = "archive", "建议归档"
    return {"total": total, "passes": passes, "verdict": verdict, "label": label,
            "veto": veto, "roles": roles, "sim_id": roles[4][2].get("sim_id", "")}

def review_bucket(rv: dict) -> str:
    """把一次多角色评审结果映射为处置动作（唯一事实源，CLI 与 Web 共用）。

    promote        → 强共识且无否决 → 可自动转正（procedure 另行要求技术官背书）
    keep           → 保留观察（原地留队列）
    reject-archive → 低质/重复/无信息量 → 自动归档（文件移入 archive/，保留可找回）
    veto-keep      → 涉密/危险否决 → 留人工终审，绝不自动归档隐藏风险

    否决分级依据：risk 类否决（合规官涉密、技术官危险命令）藏起来反而有风险，
    必须留人工；其余否决（质量官空/过短、新颖官重复）无保留价值，按自动归档处理。
    """
    if rv.get("veto"):
        risky = any(k == "compliance" and r["verdict"] == "veto" for k, _, r in rv.get("roles", []))
        risky = risky or any(k == "tech" and r["verdict"] == "veto" for k, _, r in rv.get("roles", []))
        return "veto-keep" if risky else "reject-archive"
    verdict = rv.get("verdict")
    if verdict == "promote":
        return "promote"
    if verdict == "keep":
        return "keep"
    return "reject-archive"  # archive（评分建议归档）

# ============ 转正统一裁决（L2）：唯一事实源，CLI 与 Web 共用 ============
# 任务级候选除评审分外，还要求正文结构完整——结构残缺的经验宁可留人工，也不自动转正进库。
TASK_TITLE_PREFIX = "[候选] 任务经验"
TASK_REQUIRED_SECTIONS = ("任务目标", "踩坑片段", "最终方案")


def task_candidate_gate(d: dict) -> tuple[bool, str]:
    """任务级候选的结构闸门：不满足返回 (False, 原因)。非任务级候选直接放行。"""
    title = str(d.get("title") or "")
    if not title.startswith(TASK_TITLE_PREFIX):
        return True, ""
    body = str(d.get("body") or "")
    for sec in TASK_REQUIRED_SECTIONS:
        if sec not in body:
            return False, f"正文缺「{sec}」段"
    if "(见输出)" in body:
        return False, "最终方案为空（(见输出)）"
    if "→ (无输出)" in body:
        return False, "踩坑无真实错误信息"
    if len(title) > 46 or "…" in title or title.startswith(TASK_TITLE_PREFIX + "：@"):
        return False, "标题未蒸馏/被截断（原始长句）"
    return True, ""


def promotion_decision(d: dict, rv: dict) -> tuple[str, str]:
    """候选转正裁决：返回 (bucket, reason)。

    bucket: promote 自动转正 / keep 留人工 / veto-keep 涉密或危险留人工 / reject-archive 低质重复归档。
    review_bucket 负责"评分与风险分级"，本函数负责"结构与资质"——两者叠加才是完整裁决。
    """
    bucket = review_bucket(rv)
    if bucket != "promote":
        return bucket, ""
    ntype = d.get("type")
    if ntype == "procedure" and not any(
            k == "tech" and r["verdict"] == "pass" for k, _, r in rv.get("roles", [])):
        # 收割的 procedure 多为"成功配方"工具碎片；无技术官背书的一律不自动转正，留人工终审
        return "keep", "procedure 缺技术官背书"
    ok, why = task_candidate_gate(d)
    if not ok:
        return "keep", why
    return "promote", ""


def promote_candidate(path: Path, review: dict | None = None) -> dict:
    """把候选自动转正为正式笔记：清洗元数据 → 移动入正式目录 → 重建索引 → 审计日志。"""
    d = parse_note(path) or {}
    ntype = d.get("type") if d.get("type") in ("procedure", "lesson", "fact") else "lesson"
    title = re.sub(r"^\[候选\]\s*", "", d.get("title", "")).strip()
    title = re.sub(r"^(成功配方|失败后成功|反复失败)[：:]\s*", "", title).strip()[:80]
    tags = [t for t in d.get("tags", []) if t not in ("自动收割", "待验证")] or [ntype]
    now = time.strftime("%Y-%m-%d")
    text = (
        "---\n"
        f"id: {d.get('id')}\n"
        f"type: {ntype}\n"
        "status: active\n"
        f"title: {title}\n"
        f"tags: [{', '.join(tags)}]\n"
        f"env: {d.get('env') or 'win32'}\n"
        f"created: {d.get('created') or now}\n"
        f"source: 自动收割（多角色评审转正）\n"
        "---\n\n"
        f"{d.get('body','').strip()}\n"
    )
    target_dir = NOTES / (ntype + "s")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{slugify(title)}-{d.get('id')}.md"
    try:
        _atomic_write(path, text)
        if target.exists():  # 同名冲突：加时间戳后缀，不覆盖、不中断整批转正
            target = target_dir / f"{slugify(title)}-{d.get('id')}-{int(time.time())}.md"
        path.rename(target)
    except OSError as exc:
        return {"ok": False, "error": f"转正写入失败：{exc}"}
    # 审计日志：可解释的多角色转正记录（复用评审结果，避免转正后重评）
    if review is None:
        review = multi_role_review(d, load_index())
    try:
        log_path = ROOT / AUTO_REVIEW_LOG
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "id": d.get("id"),
                                "title": title, "action": "auto_promote",
                                "total": review.get("total"), "passes": review.get("passes"),
                                "roles": {n: r["score"] for _, n, r in review.get("roles", [])}},
                               ensure_ascii=False) + "\n")
    except OSError as exc:  # noqa: BLE001
        print(f"[warn] 审计日志写入失败：{exc}", file=sys.stderr)
    build_index()
    return {"ok": True, "id": d.get("id"), "title": title, "path": str(target)}

def cmd_candidates(args) -> int:
    """候选池治理：list / check / archive / cap。防止自动收割候选无限膨胀。"""
    cand_dir = NOTES / "candidates"
    if not cand_dir.exists():
        print("候选目录不存在（notes/candidates）。")
        return 0
    files = sorted(cand_dir.glob("cand-*.md"))
    now = time.time()
    rows = []
    for p in files:
        d = parse_note(p) or {}
        rows.append((p, d, cand_age_days(str(d.get("created", "")), now)))
    action = args.action or "check"
    if action == "list":
        for p, d, age in rows:
            print(f"{p.stem} | {str(d.get('type','?')):9s} | {str(d.get('created','?')):10s} | {age:4d} 天 | {str(d.get('title',''))[:40]}")
        print(f"\n共 {len(rows)} 条候选")
        return 0
    cap = args.cap or DEFAULT_CAND_CAP
    if action == "check":
        over30 = [r for r in rows if r[2] >= 30]
        over60 = [r for r in rows if r[2] >= 60]
        print(f"候选总数 {len(rows)}（上限 {cap}）")
        print(f">=30 天未审核 {len(over30)} 条（待清理观察）")
        print(f">=60 天未归档 {len(over60)} 条（建议归档）")
        if len(rows) >= cap:
            print("⚠️ 已达容量上限，请尽快审核转正或归档！")
        for p, d, age in over60:
            print(f"  · {p.stem} | {age} 天 | {str(d.get('title',''))[:40]}")
        return 0
    if action == "archive":
        archive_dir = cand_dir / "archive"
        archive_dir.mkdir(exist_ok=True)
        moved = [r for r in rows if r[2] >= 60]
        for p, d, age in moved:
            p.rename(archive_dir / p.name)
        print(f"已归档 {len(moved)} 条超期（>=60 天）候选 → candidates/archive/（文件保留，未删除）")
        for p, d, age in moved:
            print("  ·", p.stem)
        return 0
    if action == "cap":
        print(f"候选 {len(rows)} / 上限 {cap}")
        if len(rows) >= cap:
            print("⚠️ 已达上限，请审核（转正/归档）候选。")
        return 0
    if action == "review":
        idx = load_index(force=args.reindex)
        targets = [r for r in rows if (not args.ids) or r[1].get("id") in args.ids]
        for p, d, age in targets:
            rv = multi_role_review(d, idx)
            role_line = " ".join(f"{n[1]}{r['score']:.0f}{'✓' if r['verdict']=='pass' else '●' if r['verdict']=='doubt' else '✗'}"
                                 for _, n, r in rv["roles"])
            print(f"{rv['total']:5.1f} 分[{rv['passes']}/6通过] {rv['label']:12s} | {str(d.get('title',''))[:42]}")
            print(f"          {role_line}")
            for _, n, r in rv["roles"]:
                if r["rules"]:
                    print(f"          {n[0]}·{r['rules'][0]}")
            if rv["veto"]:
                print(f"          ⛔ 否决：{rv['veto'][0][0]} | {rv['veto'][0][1]}")
        return 0
    if action == "auto":
        # 多角色评审 + 高分自动转正（强共识且无否决）；否决按性质分级处置（review_bucket 唯一事实源）
        idx = load_index(force=args.reindex)
        targets = [r for r in rows if (not args.ids) or r[1].get("id") in args.ids]
        promoted, kept, rejected, veto_kept, failed = [], [], [], [], []
        held = []  # 因结构/资质不足被挡下的（留人工，不归档）
        for p, d, age in targets:
            rv = multi_role_review(d, idx)
            bucket, why = promotion_decision(d, rv)
            if bucket == "promote":
                res = promote_candidate(p, rv)
                (promoted if res.get("ok") else failed).append(d.get("id"))
            elif bucket == "keep":
                kept.append(d.get("id"))
                if why:
                    held.append((d.get("id"), why))
            elif bucket == "veto-keep":
                # 涉密/危险否决 → 留人工处置，绝不自动归档——藏起来反而有风险
                veto_kept.append(d.get("id"))
            else:
                # reject-archive：低质（空/过短）、重复（与 active 笔记高度相似）、评分建议归档
                rejected.append(d.get("id"))
        # 自动归档仅针对 reject-archive 者；涉密/危险否决留队列人工处理。--no-purge 可跳过全部。
        if not args.no_purge and rejected:
            archive_dir = cand_dir / "archive"
            archive_dir.mkdir(exist_ok=True)
            for p, d, age in targets:
                if d.get("id") in rejected and p.exists():
                    target = archive_dir / p.name
                    if target.exists():  # 归档区已有同名（旧批次），加时间戳后缀防冲突
                        target = archive_dir / f"{p.stem}-{int(time.time())}.md"
                    p.rename(target)
        print(f"多角色评审 {len(targets)} 条 → 自动转正 {len(promoted)} | 保留观察 {len(kept)} | "
              f"低质/重复归档 {len(rejected)} | 涉密/危险留人工 {len(veto_kept)}"
              + (f" | 转正失败 {len(failed)}" if failed else "")
              + (f" | 已自动归档 {len(rejected)}" if rejected and not args.no_purge else "")
              + (f" | --no-purge 未归档" if rejected and args.no_purge else "")
              + (f" | 涉密/危险否决 {len(veto_kept)} 条留人工（勿自动归档）" if veto_kept else ""))
        for pid in promoted:
            print(f"  ✅ 转正 {pid}")
        for pid, why in held:
            print(f"  ⏸ 留人工 {pid}（{why}）")
        return 0
    return 0

def cmd_add(args) -> int:
    NOTES.mkdir(parents=True, exist_ok=True)
    sub = NOTES / (args.type + "s")
    sub.mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y%m%d-%H%M%S")
    nid = f"{now}-{random.randint(100, 999)}"
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    body = args.body
    if not body and args.file:
        body = Path(args.file).read_text(encoding="utf-8")
    if not body and not sys.stdin.isatty():
        body = sys.stdin.read()
    if not body:
        print("错误：需要 --body / --file / 管道输入", file=sys.stderr)
        return 2
    text = (
        "---\n"
        f"id: {nid}\n"
        f"type: {args.type}\n"
        f"status: {args.status}\n"
        f"title: {args.title}\n"
        f"tags: [{', '.join(tags)}]\n"
        f"env: {args.env}\n"
        f"created: {time.strftime('%Y-%m-%d')}\n"
        "---\n\n"
        f"{body.strip()}\n"
    )
    path = sub / f"{slugify(args.title)}-{nid}.md"
    _atomic_write(path, text)
    build_index()
    print(f"已写入 {path}")
    print(f"id: {nid}")
    return 0

def log_recall(query: str, hits: list) -> None:
    """记录检索命中（救火榜数据源）：谁被查、命中哪些、多少分。"""
    try:
        p = ROOT / RECALL_LOG
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "query": str(query)[:120], "n": len(hits),
                "hits": [{"id": h["id"], "score": round(h["score"], 1)} for h in hits[:10]],
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass

def cmd_recall(args) -> int:
    idx = load_index(force=args.reindex)
    hits = search(idx, args.query, limit=args.limit, include_all=args.all)
    log_recall(args.query, hits)
    if not hits:
        print("无命中。")
        return 0
    print(f"命中 {len(hits)} 条（查询：{args.query}）\n")
    for h in hits:
        flag = "" if h["status"] == "active" else f" [{h['status']}]"
        print(f"- [{h['score']}] ({h['type']}{flag}) {h['title']}  id={h['id']}")
        print(f"    {h['snippet']}")
    return 0

def cmd_show(args) -> int:
    idx = load_index()
    d = idx.get("docs", {}).get(args.id)
    if not d:
        print(f"未找到 {args.id}")
        return 1
    print(Path(d["path"]).read_text(encoding="utf-8"))
    return 0


def cmd_set_status(args) -> int:
    """改笔记状态：gc 体检提示里引用了 set-status 但从未实现，用户照做会 invalid choice。"""
    idx = load_index()
    d = idx.get("docs", {}).get(args.id)
    if not d or not d.get("path"):
        print(f"未找到笔记：{args.id}", file=sys.stderr)
        return 1
    path = Path(d["path"])
    raw = path.read_text(encoding="utf-8", errors="replace")
    if re.search(r"^status:\s*\S+", raw, re.M):
        raw = re.sub(r"^status:\s*\S+", f"status: {args.status}", raw, count=1, flags=re.M)
    else:
        raw = raw.replace("---\n", f"---\nstatus: {args.status}\n", 1)
    # 原子落盘（与其余写点一致），避免中断留截断文件
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(raw, encoding="utf-8")
    os.replace(tmp, path)
    build_index()  # 状态变更必须立即反映到检索池
    print(f"已更新 {args.id} → status: {args.status}")
    return 0

def cmd_reindex(_args) -> int:
    idx = build_index()
    print(f"重建完成：{idx['doc_count']} 条笔记，{len(idx['postings'])} 个词项")
    return 0

def cmd_stats(_args) -> int:
    idx = load_index()
    docs = idx.get("docs", {})
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for d in docs.values():
        by_type[d["type"]] = by_type.get(d["type"], 0) + 1
        by_status[d["status"]] = by_status.get(d["status"], 0) + 1
    print(f"笔记 {len(docs)} 条 | 词项 {len(idx.get('postings', {}))} | 索引时间 {idx.get('built_at')}")
    print(f"类型：{by_type}")
    print(f"状态：{by_status}")
    return 0

def warn_if_empty() -> None:
    """数据目录指向空库时给出可见告警，避免"安静失败"。"""
    if not NOTES.exists():
        print(
            f"[pmem] 警告：数据目录 {ROOT} 下没有 notes/，recall 将全部无命中。"
            "请检查 PMEM_HOME 是否指向正确的数据目录。",
            file=sys.stderr,
        )

def main() -> int:
    warn_if_empty()
    ap = argparse.ArgumentParser(prog="mem", description="个人跨会话经验记忆")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("recall", help="检索记忆")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--all", action="store_true", help="包含非 active")
    p.add_argument("--reindex", action="store_true")
    p.set_defaults(func=cmd_recall)

    p = sub.add_parser("add", help="新增记忆")
    p.add_argument("--type", choices=["procedure", "lesson", "fact"], default="lesson")
    p.add_argument("--title", required=True)
    p.add_argument("--body")
    p.add_argument("--file")
    p.add_argument("--tags", default="")
    p.add_argument("--env", default="win32")
    p.add_argument("--status", default="active")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("show", help="查看全文")
    p.add_argument("id")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("set-status", help="改笔记状态（gc 提示里引用的命令，此前不存在导致照做报错）")
    p.add_argument("id")
    p.add_argument("status", choices=["active", "staged", "suspect", "superseded"])
    p.add_argument("--reindex", action="store_true")
    p.set_defaults(func=cmd_set_status)

    p = sub.add_parser("profile", help="导出使用画像草稿（本地生成，供新工具/新会话随身携带）")
    p.add_argument("--limit", type=int, default=5, help="每个分类最多取几条")
    p.add_argument("--out", default=None, help="写入文件；不给则打印到标准输出")
    p.add_argument("--reindex", action="store_true")
    p.set_defaults(func=cmd_profile)

    p = sub.add_parser("gc", help="分层清理体检（默认 dry-run；--apply 才动文件，--prune 才删原文）")
    p.add_argument("--apply", action="store_true", help="真正执行（默认只体检不改动）")
    p.add_argument("--prune", action="store_true",
                   help="连同已冷存/已压缩的原文一起删除（默认只压缩不删，零风险）")
    p.add_argument("--cand-days", type=int, default=GC_CAND_DAYS, help="T2 候选池超期天数")
    p.add_argument("--archive-days", type=int, default=GC_ARCHIVE_DAYS, help="T3 归档区超期天数")
    p.add_argument("--archive-max", type=int, default=GC_ARCHIVE_MAX, help="T3 归档区条数上限")
    p.add_argument("--archive-bytes", type=int, default=GC_ARCHIVE_BYTES, help="T3 归档区容量上限（字节）")
    p.add_argument("--event-days", type=int, default=GC_EVENT_DAYS, help="T4 证据流超期天数")
    p.add_argument("--reindex", action="store_true", help="体检前重建索引")
    p.set_defaults(func=cmd_gc)

    p = sub.add_parser("hot", help="同步热层到宿主必读文件")
    p.add_argument("--limit", type=int, default=12)
    p.add_argument("--digest", type=int, default=45, help="每条要点字数")
    p.add_argument("--tokens", type=int, default=int(os.environ.get("PMEM_HOT_TOKENS", "0")),
                   help="注入 token 预算（CJK≈1；0=不限，参考默认 900）")
    p.add_argument("--target", default=None,
                   help="宿主必读文件路径；不给则自动探测当前项目与家目录")
    p.add_argument("--auto-fill", action="store_true", help="人工标记不足时用算法补足")
    p.add_argument("--include-auto", action="store_true",
                   help="热层保护默认排除自动收割条目（未人工确认）；加此开关才允许其补足进热层")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--reindex", action="store_true")
    p.set_defaults(func=cmd_hot)

    p = sub.add_parser("candidates", help="候选池治理（list/check/review/archive/cap）")
    p.add_argument("action", nargs="?", choices=["list", "check", "review", "auto", "archive", "cap"], default="check")
    p.add_argument("--cap", type=int, default=None, help="容量上限（默认 50）")
    p.add_argument("--ids", nargs="*", default=None, help="review 指定候选 id（默认全部）")
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--purge", action="store_true",
                     help="auto 时把评审否决的候选直接归档（默认行为，保留兼容）")
    grp.add_argument("--no-purge", action="store_true", help="auto 时不归档评审否决的候选")
    p.add_argument("--reindex", action="store_true")
    p.set_defaults(func=cmd_candidates)

    p = sub.add_parser("reindex", help="重建索引")
    p.set_defaults(func=cmd_reindex)

    p = sub.add_parser("stats", help="统计")
    p.set_defaults(func=cmd_stats)

    args = ap.parse_args()
    return args.func(args)

if __name__ == "__main__":
    sys.exit(main())
