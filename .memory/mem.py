#!/usr/bin/env python3
# pmem - 个人跨会话经验记忆（零依赖 MVP，方案 B）
#
# Copyright (c) 2026 Jose-AI
# https://www.linhut.cn
# SPDX-License-Identifier: MIT
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
import json
import math
import os
import random
import re
import sys
import time
from pathlib import Path

def resolve_root() -> Path:
    """数据目录：PMEM_HOME 优先，否则回退到脚本所在目录。

    设了 PMEM_HOME 就能把数据放到任意位置，工具代码与数据彻底分离，
    升级或重装工具不会碰到笔记。
    """
    env = os.environ.get("PMEM_HOME", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parent


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
        note = parse_note(p)
        if note:
            out.append(note)
    return out


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
    INDEX_PATH.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
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
    latins = [t for t in qterms if not is_cjk(ord(t[0]))]
    if latins and all(len(postings.get(t, {})) == 0 for t in latins):
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
    return (s[:40] or "note").lower()


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


def select_hot(idx: dict, limit: int, auto_fill: bool = False) -> list[tuple[float, dict, bool]]:
    """挑选核心经验：只装"行动时能直接救命"的知识。

    人工在 frontmatter 标 hot: true 的优先入选；不足上限时才用算法补足，
    并标记 pinned=False 以便输出时区分。宁少勿多，热层挤占上下文就失效了。
    """
    docs = idx.get("docs", {})
    scored = []
    for d in docs.values():
        if d.get("status") != "active":
            continue
        pinned = str(d.get("hot", "")).lower() in ("true", "1", "yes")
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
    return picks[:limit]


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


def cmd_hot(args) -> int:
    idx = load_index(force=args.reindex)
    picks = select_hot(idx, args.limit, auto_fill=args.auto_fill)
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
        print(f"\n[dry-run] 共 {len(picks)} 条（其中自动补足 {auto} 条），未写入。" +
              (f"token 预算 {budget}，已用 {used}。" if budget else "") +
              " 加 --apply 写入目标文件。")
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
    target.write_text(new, encoding="utf-8")
    print(f"已同步 {len(picks)} 条核心经验 → {target}")
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
            rv = cand_score(d, idx)
            print(f"{rv['score']:3d} 分 | {VERDICT_LABEL.get(rv['verdict'], rv['verdict']):6s} | {d.get('id')} | {str(d.get('title',''))[:46]}")
            for reason in rv["reasons"]:
                print(f"          · {reason}")
        if args.llm:
            if not os.environ.get("PMEM_AI_REVIEW"):
                print("\n[LLM 精审跳过]：未配置 PMEM_AI_REVIEW（如 base_url,key,model），保持本地启发式评分。涉密环境建议保持离线。")
            else:
                print("\n[LLM 精审] 已配置，可接入外部模型复核（默认仅本地评分）。")
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
    path.write_text(text, encoding="utf-8")
    build_index()
    print(f"已写入 {path}")
    print(f"id: {nid}")
    return 0


def cmd_recall(args) -> int:
    idx = load_index(force=args.reindex)
    hits = search(idx, args.query, limit=args.limit, include_all=args.all)
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

    p = sub.add_parser("hot", help="同步热层到宿主必读文件")
    p.add_argument("--limit", type=int, default=12)
    p.add_argument("--digest", type=int, default=45, help="每条要点字数")
    p.add_argument("--tokens", type=int, default=int(os.environ.get("PMEM_HOT_TOKENS", "0")),
                   help="注入 token 预算（CJK≈1；0=不限，参考默认 900）")
    p.add_argument("--target", default=None,
                   help="宿主必读文件路径；不给则自动探测当前项目与家目录")
    p.add_argument("--auto-fill", action="store_true", help="人工标记不足时用算法补足")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--reindex", action="store_true")
    p.set_defaults(func=cmd_hot)

    p = sub.add_parser("candidates", help="候选池治理（list/check/review/archive/cap）")
    p.add_argument("action", nargs="?", choices=["list", "check", "review", "archive", "cap"], default="check")
    p.add_argument("--cap", type=int, default=None, help="容量上限（默认 50）")
    p.add_argument("--ids", nargs="*", default=None, help="review 指定候选 id（默认全部）")
    p.add_argument("--llm", action="store_true", help="review 时尝试 LLM 精审（需 PMEM_AI_REVIEW 配置）")
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
