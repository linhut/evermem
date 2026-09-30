#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# memimport - 外部记忆导入（其他记忆系统 / 画像导出 / Markdown / JSON → 恒忆笔记）
#
# 设计前提：
#   1) 导入的是"别人的整理"，不是本机验证过的经验 → 默认 status=staged，不进检索池，
#      人工在「记忆浏览」逐条转正后才参与召回。宁可慢一步，不可污染检索质量。
#   2) 全程只读源文件，绝不改动/删除被导入的目录。
#   3) 冲突处理：同 id 已存在 → 跳过；与现有 active 笔记高度相似 → 标疑似重复（默认仍跳过）。
#
# 用法：
#   python memimport.py preview --file 画像.md
#   python memimport.py preview --text "## 指令\n[2026-09-27] - 先用结论后给依据"
#   python memimport.py import  --dir  "<其他记忆库目录>/notes" --status staged
#   python memimport.py import  --file 导出.json --dry-run

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

# 数据目录走唯一解析入口（env > 持久化配置 > 可移植默认），
# 否则 PyInstaller 单文件包会把导入写进临时解包目录。
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths as _paths  # noqa: E402

ROOT = _paths.data_root()
NOTES = ROOT / "notes"
EVENTS = ROOT / "events"
IMPORT_LOG = "events/import.jsonl"

# 画像的五个分类 → 笔记类型。画像条目讲的都是"关于你的事实"，故统一 fact，
# 分类本身作为 tag 保留（这样 mem.py profile 下次还能把它挑回同一分类）。
PROFILE_CATEGORIES = ("指令", "身份", "职业", "项目", "偏好")
CATEGORY_TYPE = {c: "fact" for c in PROFILE_CATEGORIES}
CAT_LINE = re.compile(r"^#{1,6}\s*(" + "|".join(PROFILE_CATEGORIES) + r")\s*$")
DATE_LINE = re.compile(r"^\s*[-*]?\s*\[([^\]]{1,24})\]\s*[-–—:：]\s*(.+?)\s*$")
DATE_OK = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UNKNOWN_DATE = ("unknown", "未知", "不确定", "?", "-")

# 通用 Markdown / JSON 里的字段别名（不同工具导出五花八门，这里做一次归一）
JSON_LIST_KEYS = ("items", "notes", "memories", "records", "data", "list", "results")
TITLE_KEYS = ("title", "name", "subject", "summary", "heading", "question")
BODY_KEYS = ("body", "content", "text", "note", "value", "answer", "detail", "description")
DATE_KEYS = ("created", "date", "created_at", "timestamp", "ts", "time", "updated")
TAG_KEYS = ("tags", "labels", "categories", "keywords")
TYPE_KEYS = ("type", "kind", "category")

VALID_TYPES = ("procedure", "lesson", "fact")


# ---------------- 去敏：复用 harvest 的规则，拿不到就退化为原样 ----------------
try:  # noqa: SIM105
    from harvest import redact  # type: ignore
except Exception:  # noqa: BLE001
    def redact(text: str) -> str:  # 退化实现：只做最基本的脱敏占位
        t = str(text or "")
        t = re.sub(r"1[3-9]\d{9}", "<phone>", t)
        t = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>", t)
        return t


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", str(text or "").strip().lower())
    return s.strip("-")[:60] or "imported"


def new_id(title: str, body: str) -> str:
    """与既有笔记同构的 id：日期时间 + 内容哈希。

    注意：id 带时间，所以**不能**用完整 id 判重（同一条换个分钟导入就是新 id）。
    判重一律走 id_hash()——只取末尾的内容指纹，这样重复导入才会被识别为已存在。
    """
    stamp = time.strftime("%Y%m%d-%H%M")
    digest = hashlib.md5((str(title) + "\n" + str(body)).encode("utf-8", "ignore")).hexdigest()[:8]
    return f"{stamp}-{digest}"


def id_hash(nid: str) -> str:
    return str(nid or "").split("-")[-1][:8]


def clean_title(raw: str, limit: int = 60) -> str:
    t = re.sub(r"\s+", " ", str(raw or "").strip())
    t = t.strip("-#*>").strip()
    return (t[:limit] + "…") if len(t) > limit else t


# ---------------- 解析器 1：画像格式（## 分类 + [日期] - 条目）----------------
def parse_profile(text: str, src: str = "") -> list[dict]:
    items: list[dict] = []
    cat = ""
    for line in str(text or "").splitlines():
        line = line.rstrip()
        m = CAT_LINE.match(line.strip())
        if m:
            cat = m.group(1)
            continue
        m = DATE_LINE.match(line)
        if not m:
            continue
        date_raw, content = m.group(1).strip(), m.group(2).strip()
        content = content.strip("`*_ ").strip()
        if not content or content.startswith("|"):  # 跳过表格分隔线与表头
            continue
        created = date_raw if DATE_OK.match(date_raw) else time.strftime("%Y-%m-%d")
        note = ("（日期未知，导入时记为今天）" if date_raw.lower() in UNKNOWN_DATE else "")
        items.append({
            "title": clean_title(content),
            "type": CATEGORY_TYPE.get(cat, "fact"),
            "tags": [c for c in (cat, "导入", "画像") if c],
            "created": created,
            "body": f"{content}\n\n分类：{cat or '未分类'}{note}\n来源：外部画像导出",
            "source": src or "外部画像导出",
        })
    return items


# ---------------- 解析器 2：Markdown（带 / 不带 frontmatter，可多篇拼接）----------------
# 注意：必须用"零宽定位 + 切片"而不是 re.split——split 会把 `---\n` 分隔符吃掉，
# 导致每篇正文开头丢失，标题被误取成 `id: xxx`。
_FM_START = re.compile(r"(?m)^---[ \t]*\r?\n(?=id:[ \t]*\S)")


def _split_markdown(text: str) -> list[str]:
    starts = [m.start() for m in _FM_START.finditer(text)]
    if not starts:
        return [text]
    if starts[0] > 0 and text[:starts[0]].strip():
        starts = [0] + starts
    chunks = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunks.append(text[s:e])
    return chunks


def _frontmatter_note(chunk: str, src: str) -> dict | None:
    meta: dict = {}
    body = chunk
    if chunk.startswith("---"):
        end = chunk.find("\n---", 3)
        if end > 0:
            head = chunk[3:end]
            body = chunk[end + 4:].lstrip("\n")
            for line in head.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    v = v.strip()
                    if v.startswith("[") and v.endswith("]"):
                        v = [x.strip().strip('"\'') for x in v[1:-1].split(",") if x.strip()]
                    meta[k.strip()] = v
    title = clean_title(meta.get("title") or "")
    if not title:
        for line in body.splitlines():  # 没有 frontmatter 标题就取首个标题行/首行
            s = line.strip()
            if s:
                title = clean_title(s.lstrip("#").strip() or s)
                break
    if not title:
        return None
    ntype = str(meta.get("type", "")).strip().lower()
    if ntype not in VALID_TYPES:
        ntype = "fact"
    tags = meta.get("tags") if isinstance(meta.get("tags"), list) else []
    tags = [str(t).strip() for t in tags if str(t).strip()]
    created = str(meta.get("created") or "")[:10]
    if not DATE_OK.match(created):
        created = time.strftime("%Y-%m-%d")
    return {
        "title": title, "type": ntype, "created": created,
        "tags": list(dict.fromkeys(tags + ["导入"])),
        "body": body.strip() or title, "source": src or "外部 Markdown",
        "orig_id": str(meta.get("id", "")).strip(),
    }


def parse_markdown(text: str, src: str = "") -> list[dict]:
    chunks = [c for c in _split_markdown(str(text or "")) if c and c.strip()]
    if not chunks:
        chunks = [str(text or "")]
    out = []
    for c in chunks:
        item = _frontmatter_note(c, src)
        if item:
            out.append(item)
    return out


# ---------------- 解析器 3：JSON ----------------
def _pick(d: dict, keys: tuple[str, ...]) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, (str, int, float)) and str(v).strip():
            return str(v).strip()
    return ""


def parse_json(text: str, src: str = "") -> list[dict]:
    try:
        data = json.loads(str(text or ""))
    except json.JSONDecodeError:
        return []
    rows: list = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for k in JSON_LIST_KEYS:
            if isinstance(data.get(k), list):
                rows = data[k]
                break
        if not rows:  # 单条对象也收
            rows = [data]
    out = []
    for r in rows:
        if not isinstance(r, dict):
            if isinstance(r, str) and r.strip():
                out.append({"title": clean_title(r), "type": "fact", "tags": ["导入"],
                            "created": time.strftime("%Y-%m-%d"), "body": r.strip(),
                            "source": src or "外部 JSON"})
            continue
        title = clean_title(_pick(r, TITLE_KEYS))
        body = _pick(r, BODY_KEYS) or title
        if not title:
            continue
        ntype = _pick(r, TYPE_KEYS).lower()
        if ntype not in VALID_TYPES:
            ntype = "fact"
        created = _pick(r, DATE_KEYS)[:10]
        if not DATE_OK.match(created):
            created = time.strftime("%Y-%m-%d")
        raw_tags = r.get("tags")
        tags = [str(t).strip() for t in raw_tags if str(t).strip()] if isinstance(raw_tags, list) else []
        out.append({"title": title, "type": ntype, "created": created,
                    "tags": list(dict.fromkeys(tags + ["导入"])), "body": body,
                    "source": src or "外部 JSON",
                    "orig_id": str(r.get("id") or "").strip()})
    return out


# ---------------- 格式自动探测 ----------------
def detect_format(text: str) -> str:
    s = str(text or "").strip()
    if s.startswith("{") or s.startswith("["):
        try:
            json.loads(s)
            return "json"
        except json.JSONDecodeError:
            pass
    if CAT_LINE.search(s) or ("[unknown]" in s and DATE_LINE.search(s)):
        return "profile"
    if re.search(r"(?m)^\s*\[\d{4}-\d{2}-\d{2}\]\s*[-–—]", s):
        return "profile"
    return "markdown"


def parse_any(text: str, src: str = "", fmt: str = "") -> tuple[list[dict], str]:
    """解析任意来源文本：返回 (条目列表, 实际使用的格式)。

    坑：fmt 的"自动"是个哨兵值（UI 下拉默认值就是 auto），**不能**当成指定格式用，
    否则 `fmt or detect_format()` 会把它当真值，画像格式被误判成 Markdown，
    整份画像塌成一条标题为分类名的笔记。哨兵必须先归一再分派。
    """
    kind = (fmt or "").strip().lower()
    if kind in ("", "auto", "自动", "自动识别", "detect"):
        kind = detect_format(text)
    fn = {"json": parse_json, "profile": parse_profile}.get(kind, parse_markdown)
    return fn(text, src), kind


def collect_from_dir(root: Path, limit: int = 500) -> list[dict]:
    """从目录批量收集 .md/.json（只读）。目录里既有单篇笔记也有导出文件。"""
    out: list[dict] = []
    for p in sorted(root.rglob("*")):
        if len(out) >= limit or not p.is_file():
            continue
        if p.name.startswith("~$") or p.suffix.lower() not in (".md", ".markdown", ".json"):
            continue
        try:
            if p.stat().st_size > 2_000_000:
                continue
            raw = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        items, _ = parse_any(raw, src=f"目录导入 · {p.name}")
        for it in items:
            it["source"] = f"目录导入 · {p.name}"
            it.setdefault("tags", [])
            out.append(it)
    return out


# ---------------- 计划：去重与冲突判定 ----------------
def plan_import(items: list[dict], idx: dict, dedupe: bool = True) -> list[dict]:
    """给每条标上动作：new 可导入 / exists 已存在跳过 / dup 疑似重复。

    判定只用本地索引，不联网。去重是"提示"而非"替你决定"——默认把 dup/exists 预置为不勾选，
    用户仍可强制导入（历史记忆换个说法也值得留一份）。
    """
    docs = idx.get("docs", {})
    known_ids = {str(d.get("id")) for d in docs.values()}
    known_hashes = {id_hash(i) for i in known_ids}
    known_titles = {str(d.get("title") or "").strip() for d in docs.values()}
    titles = [(str(d.get("id")), str(d.get("title") or "")) for d in docs.values()
              if d.get("status") == "active"]
    plan = []
    for it in items:
        nid = new_id(it.get("title", ""), it.get("body", ""))
        action, reason = "new", ""
        if it.get("orig_id") and it["orig_id"] in known_ids:
            action, reason = "exists", f"库里已有同名 id（{it['orig_id']}）"
        elif id_hash(nid) in known_hashes:
            action, reason = "exists", "内容完全一致，已存在"
        elif str(it.get("title", "")).strip() in known_titles:
            action, reason = "exists", "标题完全一致，已存在"
        elif dedupe:
            hit = _similar_existing(it.get("title", ""), titles)
            if hit:
                action, reason = "dup", f"与已有笔记相似：{hit[1][:40]}"
        row = dict(it)
        row["id"] = nid
        row["action"] = action
        row["reason"] = reason
        row["selected"] = (action == "new")
        plan.append(row)
    return plan


def _similar_existing(title: str, titles: list[tuple[str, str]]) -> tuple[str, str] | None:
    """标题级粗筛：字集合 Jaccard ≥0.6 视为疑似重复（零依赖，够用即可）。"""
    a = set(re.findall(r"[\u4e00-\u9fff]|\w+", str(title or "").lower()))
    if len(a) < 4:
        return None
    best, best_score = None, 0.0
    for nid, t in titles:
        b = set(re.findall(r"[\u4e00-\u9fff]|\w+", str(t or "").lower()))
        if not b:
            continue
        score = len(a & b) / max(1, len(a | b))
        if score > best_score:
            best, best_score = (nid, t), score
    return best if best_score >= 0.6 else None


def run_import(rows: list[dict], status: str = "staged", dry_run: bool = False) -> dict:
    """写入正式笔记目录。默认 status=staged：未人工确认前不参与召回。"""
    written, skipped = [], []
    for r in rows:
        ntype = r.get("type") if r.get("type") in VALID_TYPES else "fact"
        title = clean_title(r.get("title", ""))
        if not title:
            skipped.append((r.get("id", "?"), "标题为空"))
            continue
        body = redact(str(r.get("body") or title))
        nid = r.get("id") or new_id(title, body)
        tags = [t for t in (r.get("tags") or []) if t]
        if "导入" not in tags:
            tags.append("导入")
        created = r.get("created") if DATE_OK.match(str(r.get("created", ""))) else time.strftime("%Y-%m-%d")
        text = (
            "---\n"
            f"id: {nid}\n"
            f"type: {ntype}\n"
            f"status: {status}\n"
            f"title: {title}\n"
            f"tags: [{', '.join(tags)}]\n"
            f"env: {r.get('env') or 'win32'}\n"
            f"created: {created}\n"
            f"source: {r.get('source') or '外部导入'}\n"
            "---\n\n"
            f"{body.strip()}\n"
        )
        sub = NOTES / (ntype + "s")
        target = sub / f"{slugify(title)}-{nid}.md"
        if dry_run:
            written.append({"id": nid, "title": title, "path": str(target)})
            continue
        sub.mkdir(parents=True, exist_ok=True)
        if target.exists():
            skipped.append((nid, "目标文件已存在"))
            continue
        try:
            target.write_text(text, encoding="utf-8")
        except OSError as exc:  # noqa: BLE001
            skipped.append((nid, f"写入失败：{exc}"))
            continue
        written.append({"id": nid, "title": title, "path": str(target)})
    if not dry_run:
        try:
            log = ROOT / IMPORT_LOG
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "imported": len(written), "skipped": len(skipped),
                    "status": status,
                    "titles": [w["title"] for w in written][:50],
                }, ensure_ascii=False) + "\n")
        except OSError:
            pass
    return {"written": written, "skipped": skipped, "count": len(written)}


def load_source(args) -> tuple[str, str]:
    """按 --text / --file / --dir 取内容：返回 (文本或目录标记, 标签)。"""
    if args.text:
        return args.text, "命令行粘贴"
    if args.file:
        p = Path(args.file)
        if not p.is_file():
            print(f"文件不存在：{p}", file=sys.stderr)
            sys.exit(2)
        return p.read_text(encoding="utf-8", errors="ignore"), p.name
    if args.dir:
        return "", args.dir
    print("需要 --text / --file / --dir 之一", file=sys.stderr)
    sys.exit(2)


def main() -> int:
    ap = argparse.ArgumentParser(description="外部记忆导入（画像导出 / Markdown / JSON / 目录）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name, helptext in (("preview", "只解析并给出导入计划，不写文件"),
                           ("import", "解析并写入笔记库（默认 status=staged）")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--text", help="直接粘贴的文本（画像/笔记/JSON 均可）")
        p.add_argument("--file", help="单个 .md / .json 文件")
        p.add_argument("--dir", help="目录：批量收集其中的 .md/.json")
        p.add_argument("--fmt", choices=("auto", "profile", "markdown", "json"), default="auto",
                       help="强制指定格式（默认自动探测）")
        p.add_argument("--status", default="staged", choices=("staged", "active", "suspect"),
                       help="导入后的状态（默认 staged：不进检索池，人工确认后再转正）")
        p.add_argument("--no-dedupe", action="store_true", help="不做相似去重判定")
        p.add_argument("--include-dup", action="store_true", help="连疑似重复/已存在的也一起导入")
        if name == "import":
            p.add_argument("--dry-run", action="store_true", help="只演练，不写文件")
        p.set_defaults(dry_run=False)

    args = ap.parse_args()
    src_label = "命令行粘贴"
    if args.dir:
        items = collect_from_dir(Path(args.dir))
        fmt = "dir"
    else:
        text, src_label = load_source(args)
        items, fmt = parse_any(text, src_label, "" if args.fmt == "auto" else args.fmt)

    if not items:
        print(f"未解析出任何条目（格式判定：{fmt}）。可试 --fmt profile / markdown / json。")
        return 1

    sys.path.insert(0, str(ROOT))
    import mem  # noqa: PLC0415  （复用既有索引与检索，避免重复实现相似度）
    idx = mem.load_index(force=False)
    plan = plan_import(items, idx, dedupe=not args.no_dedupe)
    new = sum(1 for r in plan if r["action"] == "new")
    dup = sum(1 for r in plan if r["action"] == "dup")
    exist = sum(1 for r in plan if r["action"] == "exists")
    print(f"解析 {len(items)} 条（格式：{fmt}，来源：{src_label}）→ 可导入 {new} | 疑似重复 {dup} | 已存在 {exist}")
    for r in plan[:20]:
        flag = {"new": "✅", "dup": "⚠️", "exists": "⏭"}[r["action"]]
        print(f"  {flag} [{r['type']}] {r['title'][:50]}"
              + (f"  ← {r['reason']}" if r["reason"] else ""))
    if len(plan) > 20:
        print(f"  … 其余 {len(plan) - 20} 条略")

    if args.cmd == "preview":
        print("\n[preview] 未写入任何文件。确认后跑：memimport.py import <同样参数>")
        return 0

    rows = plan if args.include_dup else [r for r in plan if r["selected"]]
    if not rows:
        print("\n没有可导入的新条目（全部重复或已存在）。需要强制导入加 --include-dup。")
        return 0
    res = run_import(rows, status=args.status, dry_run=args.dry_run)
    if not args.dry_run:
        mem.build_index()
    print(f"\n{'[dry-run] 将写入' if args.dry_run else '已写入'} {res['count']} 条（status={args.status}）"
          + (f"，跳过 {len(res['skipped'])} 条" if res["skipped"] else ""))
    if args.status == "staged":
        print("提示：staged 不参与检索召回。在「记忆浏览」逐条确认后点「转正」才生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
