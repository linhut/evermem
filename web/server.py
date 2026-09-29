#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# pmem Web 版后端 —— 零依赖（Python 内置 http.server）+ JSON API
#
#
# 启动：C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe server.py
# 打开：http://127.0.0.1:8765

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

if getattr(sys, "frozen", False):
    # PyInstaller 单文件打包：`--add-data web:web` 把前端资源解压到 <MEIPASS>/web
    WEB = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "web"
else:
    WEB = Path(__file__).resolve().parent
BASE = WEB.parent  # .memory
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import mem  # noqa: E402
import backup  # noqa: E402
try:  # 导入模块依赖 harvest.redact；缺了也要能起服务，接口里另有兜底
    import memimport  # noqa: E402
except Exception:  # noqa: BLE001
    memimport = None  # type: ignore

PORT = int(os.environ.get("PMEM_WEB_PORT", "8765"))
INDEX_FILE = WEB / "index.html"

# ---------- 数据位置配置（可自由选择，env > 配置文件 > 默认） ----------
CONFIG_FILE = BASE / "pmem_config.json"
# 数据位置配置（env > pmem_config.json > 默认）：发布可移植，勿写死机器路径；
# 本机实际位置请写入 pmem_config.json（已在 .gitignore，数据与代码分离）
_DEFAULTS = {
    "home": str(BASE),
    "chunks": os.environ.get("PMEM_CHUNKS", str(BASE / "chunks")),
    "spaces": os.environ.get("PMEM_SPACES", str(BASE)),
}

def load_pmem_config() -> dict:
    try:
        c = json.loads(CONFIG_FILE.read_text(encoding="utf-8", errors="ignore"))
        if isinstance(c, dict):
            return c
    except (OSError, json.JSONDecodeError):
        pass
    return {}

_PMEM_CFG = load_pmem_config()
CHUNKS_ROOT = Path(os.environ.get("PMEM_CHUNKS", _PMEM_CFG.get("chunks") or _DEFAULTS["chunks"]))
SPACES_ROOT = Path(os.environ.get("PMEM_SPACES", _PMEM_CFG.get("spaces") or _DEFAULTS["spaces"]))

import shutil as _shutil

def path_check(p: str) -> dict:
    """数据目录检查：存在 / 可写（权限）/ 可用空间 / 可创建。"""
    path = Path(p)
    if not str(path).strip():
        return {"error": "路径为空"}
    if path.exists():
        if not path.is_dir():
            return {"exists": True, "is_dir": False, "ok": False, "note": "不是目录"}
        writable = os.access(path, os.W_OK)
        try:
            du = _shutil.disk_usage(path)
            free_gb = round(du.free / 2**30, 1)
        except OSError:
            free_gb = None
        return {"exists": True, "is_dir": True, "writable": writable, "ok": writable,
                "free_gb": free_gb, "note": "可写" if writable else "无写权限"}
    # 不存在：检查父目录可写（能否创建）
    parent_ok = os.access(path.parent, os.W_OK) if path.parent.exists() else False
    return {"exists": False, "writable": False, "ok": parent_ok, "creatable": True,
            "note": "不存在，" + ("父目录可写可创建" if parent_ok else "父目录不可写")}

def save_pmem_config(patch: dict) -> tuple[bool, str]:
    """保存数据位置配置（跨会话一致：写 pmem_config.json，所有进程读同一文件）。"""
    cfg = load_pmem_config()
    for k in ("home", "chunks", "spaces"):
        if k in patch and patch[k] is not None:
            cfg[k] = str(patch[k]).strip()
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return True, str(CONFIG_FILE)
    except OSError as exc:
        return False, str(exc)
EXCLUDE_DIRS = {
    "$RECYCLE.BIN", "System Volume Information", "CPM_ENCRYPTED_FOLDER",
    "Game", "WeGameApps", "Wondershare", "Android", "iso", "hulu", "opgg",
    "canon", "Anki", "U盘file", "PSAutoRecover", "BaiduNetdiskDownload",
    "Package", "tmp", "tools", "master", "1111", "f", "data", "cod", "备份",
    "WeChat Files",
}
DOC_EXTS = {".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".pdf",
            ".md", ".txt", ".csv", ".html", ".py", ".json", ".yaml", ".yml"}
HOSTS = [
    ("WorkBuddy", str(Path.home() / ".workbuddy" / "skills" / "personal-memory" / "SKILL.md")),
    ("Claude Code", str(Path.home() / ".claude" / "skills" / "personal-memory" / "SKILL.md")),
    ("CodeBuddy", str(Path.home() / ".codebuddy" / "skills" / "personal-memory" / "SKILL.md")),
    ("DSH (DeepSeek Harness)", str(Path.home() / ".dsh" / "skills" / "personal-memory" / "SKILL.md")),
]
SKILL_TEMPLATE = BASE / "templates" / "personal-memory.SKILL.md"

# ---------- MCP 一键安装配置（各宿主） ----------
def _default_py() -> str:
    """Python 解释器探测：PMEM_SYS_PY > 当前解释器 > PATH，发布可移植。"""
    for cand in (os.environ.get("PMEM_SYS_PY", "").strip(),
                 sys.executable, _shutil.which("python"), _shutil.which("python3")):
        if cand:
            return str(cand)
    return "python"

PY_ABS = _default_py()
MCP_SCRIPT = str(BASE / "evermem_mcp.py")
MCP_SERVER_NAME = "evermem"

MCP_TARGETS = [
    ("workbuddy", "WorkBuddy",
     [str(Path.home() / ".workbuddy" / "mcp.json"),
      str(Path.home() / ".workbuddy" / ".mcp.json")], "json"),
    ("claude", "Claude Code",
     [str(Path.home() / ".claude.json")], "json"),
    ("dsh", "DSH (DeepSeek Harness)",
     [str(Path.home() / ".dsh" / "settings.yaml")], "yaml"),
]

def mcp_entry() -> dict:
    return {MCP_SERVER_NAME: {"command": PY_ABS, "args": [MCP_SCRIPT]}}

def mcp_installed(file_path: str, fmt: str) -> bool:
    p = Path(file_path)
    if not p.exists():
        return False
    try:
        if fmt == "json":
            d = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
            return isinstance(d.get("mcpServers"), dict) and MCP_SERVER_NAME in d["mcpServers"]
        raw = p.read_text(encoding="utf-8", errors="ignore")
        return "serverName: " + MCP_SERVER_NAME in raw or "evermem_mcp" in raw
    except (OSError, json.JSONDecodeError):
        return False

def mcp_install_json(file_path: str) -> tuple[bool, str]:
    p = Path(file_path)
    try:
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
        else:
            d = {}
        if not isinstance(d, dict):
            d = {}
        servers = d.get("mcpServers")
        if not isinstance(servers, dict):
            servers = {}
        servers[MCP_SERVER_NAME] = mcp_entry()[MCP_SERVER_NAME]
        d["mcpServers"] = servers
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        return True, str(p)
    except (OSError, json.JSONDecodeError) as exc:
        return False, str(exc)

def mcp_install_yaml(file_path: str) -> tuple[bool, str]:
    p = Path(file_path)
    try:
        raw = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
        if "serverName: " + MCP_SERVER_NAME in raw:
            return True, "已存在，无需改动"
        block = (
            "\n# 恒忆 Evermem MCP（mcp-support 插件命名空间；需已安装 @deepseek-ai/dsh-mcp-client）\n"
            "mcp-support:\n"
            "  servers:\n"
            f"    - transport: stdio\n      serverName: {MCP_SERVER_NAME}\n"
            f"      command: {PY_ABS}\n"
            f"      args:\n        - {MCP_SCRIPT}\n"
        )
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(raw.rstrip() + "\n" + block, encoding="utf-8")
        return True, str(p)
    except OSError as exc:
        return False, str(exc)

# ---------- 异步任务系统（extract/harvest 不阻塞 UI，含失败重试） ----------
import threading as _threading
import uuid as _uuid

_TASKS: dict[str, dict] = {}

def _run_task(task_id: str, fn, retries: int = 1) -> None:
    import subprocess as _sp

    def _worker():
        last_err = ""
        for attempt in range(retries + 1):
            try:
                r = _sp.run(fn, capture_output=True, text=True, encoding="utf-8",
                            errors="ignore", timeout=1800)
                out = (r.stdout or "") + (r.stderr or "")
                if r.returncode == 0:
                    _TASKS[task_id] = {"state": "done", "output": out[-1500:]}
                    return
                last_err = out[-800:]
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
        _TASKS[task_id] = {"state": "error", "output": last_err}

    _TASKS[task_id] = {"state": "running", "output": ""}
    _threading.Thread(target=_worker, daemon=True).start()

TYPE_LABEL = {"fact": "事实", "lesson": "经验", "procedure": "配方"}

def provenance_of(source: str, tags: list, note_id: str) -> str:
    """判定记忆来源通道（界面显示来源图标）。"""
    s = source or ""
    t = "".join(tags or [])
    if "F:/" in s or "F:\\" in s or s.startswith("F:"):
        return "doc"        # 文档提炼（F 盘语料）
    if ".dsh" in s:
        return "dsh"        # DSH 会话
    if ".atomcode" in s:
        return "atomcode"   # atomcode 会话
    if "自动收割" in t:
        return "harvest"    # 会话收割候选
    if "mcp-" in note_id or "mcp" in t:
        return "mcp"        # MCP 桥写入（agent）
    if "manual" in note_id or "web-" in note_id:
        return "manual"     # 手动/界面新建
    return "ai"             # AI 提炼（其余）

def read_note_body(path: str) -> str:
    """从笔记文件读正文（索引已瘦身不存全文）。"""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""
    _, _, rest = raw.partition("---\n")
    if "\n---\n" in rest:
        return rest.split("\n---\n", 1)[1].strip()
    return rest.strip()

def note_public(d: dict) -> dict:
    """笔记 → 前端可用结构。"""
    return {
        "id": d.get("id", ""),
        "type": d.get("type", ""),
        "type_label": TYPE_LABEL.get(d.get("type"), d.get("type", "")),
        "status": d.get("status", ""),
        "title": d.get("title", ""),
        "tags": d.get("tags") or [],
        "env": d.get("env", ""),
        "created": d.get("created", ""),
        "hot": str(d.get("hot", "")).lower() in ("true", "1", "yes"),
        "source": d.get("source", ""),
        "path": d.get("path", ""),
        "body": d.get("body", ""),
        "body_len": d.get("body_len", 0),
        "origin": provenance_of(d.get("source", ""), d.get("tags") or [], d.get("id", "")),
    }

def list_notes() -> list[dict]:
    idx = cached_index()
    return [note_public(d) for d in idx.get("docs", {}).values()]

# ---------- 缓存（性能：避免每次请求读盘解析 1.24MB 索引） ----------
_idx_cache: dict = {"mtime": -1.0, "idx": None}
_spaces_cache: dict = {"ts": 0.0, "data": None}
_blocks_cache: dict[str, tuple[float, list]] = {}

def cached_index() -> dict:
    # 关键：必须用 force=False（mem.load_index 自动检测笔记变化才重建）。
    # 若用 force=True，build_index 每次写盘 → index.json mtime 每次变 → 缓存永不命中，
    # 每个请求都全量重建（0.2-0.4s），这就是"浏览记忆条目慢"的根源。
    try:
        m = mem.INDEX_PATH.stat().st_mtime
    except OSError:
        return mem.load_index(force=False)
    if _idx_cache["mtime"] != m:
        _idx_cache["idx"] = mem.load_index(force=False)
        _idx_cache["mtime"] = m
    return _idx_cache["idx"]

def cached_spaces() -> list[dict]:
    import time as _t
    if _spaces_cache["data"] is not None and _t.time() - _spaces_cache["ts"] < 300:
        return _spaces_cache["data"]
    spaces = []
    if SPACES_ROOT.exists():
        for entry in sorted(SPACES_ROOT.iterdir(), key=lambda x: x.name.lower()):
            if not entry.is_dir() or entry.name in EXCLUDE_DIRS:
                continue
            n = sum(1 for f in entry.rglob("*")
                    if f.is_file() and f.suffix.lower() in DOC_EXTS and not f.name.startswith("~$"))
            if n >= 3:
                spaces.append({"name": entry.name, "path": str(entry), "docs": n})
    _spaces_cache["data"] = spaces
    _spaces_cache["ts"] = _t.time()
    return spaces

def cached_blocks(space: str) -> list[dict]:
    d = CHUNKS_ROOT / space
    if not d.exists():
        return []
    try:
        dm = d.stat().st_mtime
    except OSError:
        return []
    if _blocks_cache.get(space, (0, []))[0] == dm:
        return _blocks_cache[space][1]
    blocks = []
    for f in sorted(d.glob("*.txt")):
        blocks.append({"name": f.stem[:48], "path": str(f), "size": f.stat().st_size})
    _blocks_cache[space] = (dm, blocks)
    return blocks

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # 静默访问日志
        pass

    # ---------- 工具 ----------
    def _json(self, obj: dict, code: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self):
        try:
            raw = INDEX_FILE.read_bytes()
        except OSError:
            self.send_error(500, "index.html 缺失")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def handle(self):
        # 客户端中途断开（浏览器刷新/取消请求）时优雅吞掉，不刷 traceback（原会打印 ConnectionReset/Aborted 大栈）
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def _bytes(self, raw: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        # 前端改动频繁，禁用缓存避免浏览器加载旧 JS 导致读到旧版-contract（曾白页一次）
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _static(self, name: str, ctype: str):
        try:
            raw = (WEB / name).read_bytes()
        except OSError:
            self.send_error(404)
            return
        self._bytes(raw, ctype)

    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n <= 0:
                return {}
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return {}

    # ---------- GET ----------
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        if p in ("/", "/index.html"):
            self._html()
            return
        # 前端静态资源：按扩展名统一放行，并限制在 WEB 目录内。
        # 此前逐个文件白名单导致"新增一个前端模块就要改一次服务端"，这里一次性收敛。
        static_ext = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                      ".html": "text/html; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml",
                      ".ico": "image/x-icon", ".woff2": "font/woff2"}
        suffix = Path(p).suffix.lower()
        if suffix in static_ext:
            try:
                rel = Path(p.lstrip("/").replace("\\", "/"))
                full = (WEB / rel).resolve()
                if str(full).startswith(str(WEB.resolve())) and full.is_file():
                    self._bytes(full.read_bytes(), static_ext[suffix])
                    return
            except OSError:
                pass
            self.send_error(404)
            return
        if p == "/api/health":
            self._json({"ok": True, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "notes": len(list_notes())})
            return
        if p == "/api/notes":
            full = parse_qs(u.query).get("full", ["0"])[0] == "1"
            notes = list_notes()
            notes.sort(key=lambda n: n.get("id", ""), reverse=True)  # 按 id（含日期时间）倒序，最新在前
            if not full:
                # 列表瘦身：去掉 body 与 path（详情走 /api/note），响应大幅减小
                for n in notes:
                    n.pop("body", None)
                    n.pop("path", None)
                    n.pop("source", None)
            self._json({"notes": notes})
            return
        if p == "/api/search":
            q = parse_qs(u.query).get("q", [""])[0].strip()
            include_all = parse_qs(u.query).get("all", ["0"])[0] == "1"
            if not q:
                self._json({"hits": []})
                return
            idx = cached_index()
            hits = mem.search(idx, q, limit=50, include_all=include_all)
            mem.log_recall(q, hits)
            note_map = idx.get("docs", {})
            self._json({"hits": [{"id": h["id"], "score": h["score"], "title": h["title"],
                                  "type": h["type"], "type_label": TYPE_LABEL.get(h["type"], h["type"]),
                                  "status": h["status"], "snippet": h["snippet"],
                                  "origin": provenance_of(note_map.get(h["id"], {}).get("source", ""),
                                                          note_map.get(h["id"], {}).get("tags") or [],
                                                          h["id"])} for h in hits]})
            return
        if p == "/api/hot":
            idx = cached_index()
            hot, _skipped_auto = mem.select_hot(idx, limit=20, include_auto=False)
            items = []
            for _, d, pinned in hot:
                n = note_public(d)
                n["body"] = read_note_body(n.get("path", "")) or n.get("body", "")
                items.append(n)
            self._json({"hot": items, "count": len(items)})
            return
        if p == "/api/stats":
            notes = list_notes()
            by_type: dict[str, int] = {}
            by_status: dict[str, int] = {}
            hot = 0
            for n in notes:
                by_type[n["type"]] = by_type.get(n["type"], 0) + 1
                by_status[n["status"]] = by_status.get(n["status"], 0) + 1
                if n["hot"]:
                    hot += 1
            self._json({"total": len(notes), "by_type": by_type, "by_status": by_status, "hot": hot,
                        "built_at": cached_index().get("built_at", "")})
            return
        if p == "/api/gc":
            # 分层清理体检（只读）：报告各层容量与超期情况，不改任何文件。
            # 真正的清理走命令行 `mem.py gc --apply`（默认只压缩不删，需 --prune 才删原文）——
            # 破坏性操作不放 Web 一键按钮，避免误点丢数据。
            now = time.time()
            cand_dir = mem.NOTES / "candidates"
            archive_dir = cand_dir / "archive"
            idx = mem.load_index(force=False)
            cand_files = sorted(cand_dir.glob("cand-*.md")) if cand_dir.exists() else []
            cand_over = 0
            for f in cand_files:
                d = mem.parse_note(f) or {}
                if mem.cand_age_days(str(d.get("created", "")), now) >= mem.GC_CAND_DAYS:
                    cand_over += 1
            arch_files = sorted(archive_dir.glob("*.md")) if archive_dir.exists() else []
            arch_bytes = sum(x.stat().st_size for x in arch_files) if arch_files else 0
            protected = 0
            oldest = 0.0
            for x in arch_files:
                try:
                    raw = x.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if mem.gc_is_protected(raw):
                    protected += 1
                    continue
                oldest = max(oldest, mem.gc_file_age_days(x, now))
            ev_files = sorted(mem.EVENTS.glob("*.jsonl")) if mem.EVENTS.exists() else []
            ev_bytes = sum(x.stat().st_size for x in ev_files) if ev_files else 0
            hit = []
            if cand_over:
                hit.append(f"候选池 {cand_over} 条超期（≥{mem.GC_CAND_DAYS} 天）")
            if len(arch_files) >= mem.GC_ARCHIVE_MAX:
                hit.append(f"归档区 {len(arch_files)} 条已达上限 {mem.GC_ARCHIVE_MAX}")
            if arch_bytes >= mem.GC_ARCHIVE_BYTES:
                hit.append(f"归档区 {arch_bytes / 1048576:.0f}MB 已达容量上限")
            if oldest >= mem.GC_ARCHIVE_DAYS:
                hit.append(f"归档区最老 {oldest:.0f} 天已达超期线 {mem.GC_ARCHIVE_DAYS} 天")
            advice = ("触发：" + "；".join(hit) + "。建议执行 python mem.py gc --apply。"
                      if hit else "各层均在阈值内，暂无需清理（继续正常使用即可）。")
            self._json({
                "notes": len(idx.get("docs", {})),
                "candidates": len(cand_files), "cand_cap": mem.DEFAULT_CAND_CAP,
                "cand_days": mem.GC_CAND_DAYS, "cand_over": cand_over,
                "archive": len(arch_files), "archive_mb": round(arch_bytes / 1048576, 2),
                "archive_oldest_days": int(oldest), "protected": protected,
                "archive_days": mem.GC_ARCHIVE_DAYS, "archive_max": mem.GC_ARCHIVE_MAX,
                "event_files": len(ev_files), "event_mb": round(ev_bytes / 1048576, 2),
                "event_days": mem.GC_EVENT_DAYS,
                "level": "warn" if hit else "ok", "advice": advice,
            })
            return
        if p == "/api/candidates":
            cand_dir = mem.NOTES / "candidates"
            items = []
            idx = cached_index()
            if cand_dir.exists():
                now = time.time()
                for f in sorted(cand_dir.glob("cand-*.md")):
                    d = mem.parse_note(f) or {}
                    age = mem.cand_age_days(str(d.get("created", "")), now)
                    rv = mem.multi_role_review(d, idx)
                    items.append({"id": d.get("id", f.stem), "type": d.get("type", "fact"),
                                  "status": d.get("status", "suspect"), "title": d.get("title", f.stem),
                                  "created": d.get("created", ""), "age": age,
                                  "type_label": TYPE_LABEL.get(d.get("type", "fact"), d.get("type", "fact")),
                                  "ai_total": rv["total"], "ai_label": rv["label"],
                                  "ai_passes": rv["passes"], "ai_verdict": rv["verdict"],
                                  "roles": [{"k": k, "n": n, "score": r["score"], "v": r["verdict"]}
                                            for k, n, r in rv["roles"]]})
            self._json({"items": items, "total": len(items), "cap": mem.DEFAULT_CAND_CAP,
                        "over30": sum(1 for i in items if i["age"] >= 30),
                        "over60": sum(1 for i in items if i["age"] >= 60)})
            return
        if p == "/api/backup":
            self._json(backup.sync_status())
            return
        if p == "/api/backup/targets":
            self._json({"targets": backup.discover_targets()})
            return
        if p == "/api/backup/providers":
            self._json({"providers": backup.PROVIDERS, "scopes": list(backup.SCOPE_GROUPS.keys())})
            return
        if p == "/api/backup/log":
            lines = []
            try:
                lines = (backup.BASE / backup.LOG_FILE).read_text(encoding="utf-8", errors="ignore").splitlines()[-50:]
            except OSError:
                pass
            self._json({"lines": lines})
            return
        if p == "/api/candidates/body":
            did = parse_qs(u.query).get("id", [""])[0]
            cand_dir = mem.NOTES / "candidates"
            hit = None
            if cand_dir.exists():
                for f in cand_dir.glob("cand-*.md"):
                    d = mem.parse_note(f) or {}
                    if d.get("id") == did:
                        hit = f
                        break
            if not hit:
                self._json({"error": "not found"}, 404)
                return
            d = mem.parse_note(hit) or {}
            self._json({"id": did, "title": d.get("title", ""), "body": d.get("body", ""),
                        "type": d.get("type", "fact")})
            return
        if p == "/api/note":
            did = parse_qs(u.query).get("id", [""])[0]
            idx = cached_index()
            d = idx.get("docs", {}).get(did)
            if not d:
                self._json({"error": "not found"}, 404)
                return
            n = note_public(d)
            n["body"] = read_note_body(n.get("path", "")) or n.get("body", "")
            self._json({"note": n})
            return
        if p == "/api/spaces":
            self._json({"spaces": cached_spaces()})
            return
        if p == "/api/blocks":
            name = parse_qs(u.query).get("space", [""])[0]
            self._json({"blocks": cached_blocks(name), "space": name})
            return
        if p == "/api/scan":
            """扫描任意路径：文档构成统计 + 块库进度（供导入页展示）。"""
            path = parse_qs(u.query).get("path", [""])[0]
            root = Path(path)
            if not root.exists() or not root.is_dir():
                self._json({"error": "路径不存在"}, 404)
                return
            by_ext: dict[str, int] = {}
            total = 0
            size = 0
            for f in root.rglob("*"):
                if f.is_file() and f.suffix.lower() in DOC_EXTS and not f.name.startswith("~$"):
                    ext = f.suffix.lower()
                    by_ext[ext] = by_ext.get(ext, 0) + 1
                    total += 1
                    try:
                        size += f.stat().st_size
                    except OSError:
                        pass
            name = root.name
            blocks = len(cached_blocks(name))
            self._json({"path": str(root), "name": name, "total": total,
                        "size_mb": round(size / 1048576, 1),
                        "by_ext": dict(sorted(by_ext.items(), key=lambda kv: -kv[1])),
                        "blocks_now": blocks})
            return
        if p == "/api/block":
            path = parse_qs(u.query).get("path", [""])[0]
            try:
                text = Path(path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                self._json({"error": "read failed"}, 404)
                return
            self._json({"path": path, "text": text[:5000]})
            return
        if p == "/api/hosts":
            hosts = []
            for name, dest in HOSTS:
                installed = Path(dest).exists()
                ts = time.strftime("%m-%d %H:%M", time.localtime(Path(dest).stat().st_mtime)) if installed else None
                hosts.append({"name": name, "path": dest, "installed": installed, "updated": ts})
            self._json({"hosts": hosts, "template": SKILL_TEMPLATE.exists()})
            return
        if p == "/api/task/status":
            tid = parse_qs(u.query).get("task", [""])[0]
            st = _TASKS.get(tid)
            if not st:
                self._json({"error": "task 不存在"}, 404)
                return
            self._json(st)
            return
        if p == "/api/mcpsetup":
            out = []
            for key, label, files, fmt in MCP_TARGETS:
                states = [(f, mcp_installed(f, fmt)) for f in files]
                out.append({"key": key, "label": label, "files": [{"path": f, "installed": s} for f, s in states],
                            "any_installed": any(s for _, s in states),
                            "entry": mcp_entry(), "fmt": fmt})
            self._json({"targets": out, "script": MCP_SCRIPT, "python": PY_ABS})
            return
        if p == "/api/config":
            """数据位置配置：当前值 + 权限/空间检查（供 UI 显示与修改）。"""
            cur = {"home": str(BASE), "chunks": str(CHUNKS_ROOT), "spaces": str(SPACES_ROOT),
                   "config_file": str(CONFIG_FILE)}
            self._json({"current": cur,
                        "checks": {k: path_check(str(Path(v))) for k, v in cur.items()},
                        "note": "配置优先级：环境变量 > pmem_config.json > 默认；修改后重启 server/launcher 生效。跨会话一致：所有进程读同一配置文件。"})
            return
        if p == "/api/profile/prompt":
            # 「其他记忆导入」页的「导出记忆提示词」卡片数据源：直接读模板里的 COPY 区间。
            # 提示词只有一份事实源（templates/usage-profile.prompt.md），前端不硬编码。
            tpl = mem.ROOT / "templates" / "usage-profile.prompt.md"
            text = ""
            try:
                raw = tpl.read_text(encoding="utf-8")
                if "<!-- COPY:BEGIN -->" in raw and "<!-- COPY:END -->" in raw:
                    _, rest = raw.split("<!-- COPY:BEGIN -->", 1)
                    text, _ = rest.split("<!-- COPY:END -->", 1)
            except OSError:
                text = ""
            self._json({"ok": bool(text), "text": text.strip(), "path": str(tpl)})
            return
        self.send_error(404)

    # ---------- POST ----------
    def do_POST(self):
        u = urlparse(self.path)
        p = u.path
        if p == "/api/memimport/preview":
            # 外部记忆导入第一步：只解析并给出计划（new/dup/exists），不写任何文件。
            try:
                import memimport  # noqa: PLC0415
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"导入模块不可用：{exc}"}, 500)
                return
            b = self._body() or {}
            src_label = "界面粘贴"
            try:
                if b.get("dir"):
                    items = memimport.collect_from_dir(Path(b["dir"]))
                    fmt = "dir"
                elif b.get("path"):
                    fp = Path(b["path"])
                    if not fp.is_file():
                        self._json({"ok": False, "error": f"文件不存在：{fp}"}, 400)
                        return
                    src_label = fp.name
                    items, fmt = memimport.parse_any(
                        fp.read_text(encoding="utf-8", errors="ignore"), src_label, b.get("fmt") or "")
                else:
                    items, fmt = memimport.parse_any(b.get("text") or "", src_label, b.get("fmt") or "")
            except OSError as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"读取失败：{exc}"}, 400)
                return
            idx = mem.load_index(force=False)
            plan = memimport.plan_import(items, idx, dedupe=not b.get("no_dedupe"))
            stats = {
                "total": len(plan),
                "new": sum(1 for r in plan if r["action"] == "new"),
                "dup": sum(1 for r in plan if r["action"] == "dup"),
                "exists": sum(1 for r in plan if r["action"] == "exists"),
            }
            self._json({"ok": True, "format": fmt, "source": src_label, "stats": stats, "items": plan})
            return
        if p == "/api/memimport/run":
            # 第二步：写入正式笔记目录。默认 status=staged——导入的是别人的整理，
            # 未经人工确认不进检索池，避免污染召回质量。
            try:
                import memimport  # noqa: PLC0415
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"导入模块不可用：{exc}"}, 500)
                return
            b = self._body() or {}
            rows = b.get("items") or []
            if not rows:
                self._json({"ok": False, "error": "没有选中任何条目"}, 400)
                return
            status = b.get("status") or "staged"
            if status not in ("staged", "active", "suspect"):
                status = "staged"
            res = memimport.run_import(rows, status=status, dry_run=bool(b.get("dry_run")))
            if not b.get("dry_run"):
                mem.build_index()
            self._json({"ok": True, "count": res["count"], "written": res["written"][:50],
                        "skipped": res["skipped"][:20], "status": status})
            return
        if p == "/api/backup/test":
            b = self._body()
            self._json(backup.test_connection((b or {}).get("type", ""), b or {}))
            return
        if p == "/api/backup/check":
            b = self._body()
            ch_name = (b or {}).get("channel") or ""
            cfg = backup.load_cfg()
            ch = next((c for c in cfg["channels"] if not ch_name or c["name"] == ch_name), None)
            if not ch:
                self._json({"ok": False, "error": "未找到渠道"}, 400)
                return
            self._json(backup.check_channel(ch))
            return
        if p == "/api/backup/save":
            b = self._body()
            auto = bool(b.get("auto", False))
            alert = (b.get("alert_email") or "").strip()
            # 「留空保留旧值 / 涉密字段混淆」的领域规则统一在 backup.from_request，
            # HTTP 层不再各写一套 —— 此前向导与行编辑器两处实现不一致导致 S3 连接参数被清空。
            old_by_name = {oc.get("name"): oc for oc in (backup.load_cfg().get("channels") or [])}
            channels = []
            for c in b.get("channels") or []:
                if not isinstance(c, dict) or c.get("type") not in backup.CHANNEL_TYPES:
                    continue
                channels.append(backup.from_request(c, old_by_name.get(c.get("name"), {})))
            backup.save_cfg({"auto": auto, "alert_email": alert, "channels": channels})
            resp = backup.sync_status()
            # mail 渠道安全提示：SMTP 密码建议走环境变量 PMEM_SMTP_PASS，不落配置明文；涉密快照慎用邮箱
            if any(c.get("type") == "mail" and c.get("smtp", {}).get("pass") for c in channels):
                resp["hint"] = "mail 渠道已记录 SMTP 密码——建议改用环境变量 PMEM_SMTP_PASS（配置只留 host/user）；涉密数据经邮箱需自行合规评估。"
            self._json(resp)
            return
        if p == "/api/backup/run":
            b = self._body()
            ch_name = (b or {}).get("channel") or ""
            cfg = backup.load_cfg()
            if not cfg["channels"]:
                self._json({"ok": False, "error": "未配置备份渠道"}, 400)
                return
            targets = [c for c in cfg["channels"] if (not ch_name or c["name"] == ch_name) and (ch_name or c["enabled"])]
            if ch_name and not targets:
                self._json({"ok": False, "error": f"未找到渠道：{ch_name}"}, 400)
                return
            results = [backup.run_channel(c) for c in targets]
            self._json({"ok": all(r["ok"] for r in results), "results": results})
            return
        if p == "/api/backup/restore":
            b = self._body()
            ch_name = (b or {}).get("channel") or ""
            cfg = backup.load_cfg()
            if not cfg["channels"]:
                self._json({"ok": False, "error": "未配置备份渠道"}, 400)
                return
            if ch_name:
                ch = next((c for c in cfg["channels"] if c["name"] == ch_name), None)
            else:
                ch = cfg["channels"][0] if len(cfg["channels"]) == 1 else None
            if not ch:
                self._json({"ok": False, "error": "需指定要恢复的渠道"}, 400)
                return
            self._json(backup.restore_channel(ch))
            return
        if p == "/api/candidates/autoreview":
            # 多角色评审全部候选，强共识且无否决者自动转正；否决按性质分级处置（mem.review_bucket 唯一事实源）：
            #   低质/重复 → 自动归档（文件移入 archive/，保留可找回）
            #   涉密/危险 → 留人工终审，绝不自动归档隐藏风险
            cand_dir = mem.NOTES / "candidates"
            idx = mem.load_index(force=False)
            promoted, kept, rejected, veto_kept, failed = [], [], [], [], []
            held = []  # 结构/资质不足被挡下留人工的（附原因，前端可展示）
            if cand_dir.exists():
                for f in sorted(cand_dir.glob("cand-*.md")):
                    d = mem.parse_note(f) or {}
                    rv = mem.multi_role_review(d, idx)
                    bucket, why = mem.promotion_decision(d, rv)
                    if bucket == "promote":
                        try:
                            res = mem.promote_candidate(f, rv)
                        except Exception as exc:  # noqa: BLE001
                            failed.append(str(d.get("id")))
                            continue
                        (promoted if res.get("ok") else failed).append(d.get("id"))
                    elif bucket == "keep":
                        kept.append(d.get("id"))
                        if why:
                            held.append({"id": d.get("id"), "reason": why})
                    elif bucket == "veto-keep":
                        # 涉密/危险否决 → 留人工处置，绝不自动归档
                        veto_kept.append(d.get("id"))
                    else:
                        # reject-archive：低质（空/过短）、重复（与 active 笔记高度相似）、评分建议归档
                        rejected.append(d.get("id"))
            # 自动归档仅针对 reject-archive 者；涉密/危险否决留队列人工处理，防风险被藏起
            archived = []
            if rejected and cand_dir.exists():
                archive_dir = cand_dir / "archive"
                archive_dir.mkdir(parents=True, exist_ok=True)
                for f in sorted(cand_dir.glob("cand-*.md")):
                    d = mem.parse_note(f) or {}
                    if str(d.get("id")) in rejected:
                        target = archive_dir / f.name
                        if target.exists():
                            target = archive_dir / f"{f.stem}-{int(time.time())}.md"
                        f.rename(target)
                        archived.append(f.stem)
            if promoted or archived:
                mem.build_index()
            self._json({"reviewed": len(promoted) + len(kept) + len(rejected) + len(veto_kept) + len(failed),
                        "promoted": promoted, "kept": kept, "rejected": rejected,
                        "veto_kept": veto_kept, "failed": failed, "archived": archived, "held": held})
            return
        if p == "/api/candidates/archive":
            cand_dir = mem.NOTES / "candidates"
            archive_dir = cand_dir / "archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            body = self._body()
            ids = set(body.get("ids") or []) if isinstance(body, dict) else set()
            moved = []
            if cand_dir.exists():
                now = time.time()
                for f in sorted(cand_dir.glob("cand-*.md")):
                    d = mem.parse_note(f) or {}
                    if ids:
                        if str(d.get("id")) in ids:
                            f.rename(archive_dir / f.name)
                            moved.append(f.stem)
                    elif mem.cand_age_days(str(d.get("created", "")), now) >= 60:
                        f.rename(archive_dir / f.name)
                        moved.append(f.stem)
            mem.build_index()
            self._json({"ok": True, "moved": moved})
            return
        if p == "/api/candidates/status":
            # 候选的转正 / 存疑必须改候选文件本身：候选不在主索引 docs 里，
            # 走 /api/note/<id>/status 只会 404（旧的单条按钮点了个寂寞，还照样提示「已处理」）。
            # 支持一次传多个 id，批量与单条共用这一条路由。
            cand_dir = mem.NOTES / "candidates"
            b = self._body() or {}
            ids = [str(x) for x in (b.get("ids") or [])]
            status = str(b.get("status") or "").strip()
            if status not in ("active", "staged", "suspect", "superseded"):
                self._json({"error": "bad status"}, 400)
                return
            if not ids:
                self._json({"error": "ids 必填"}, 400)
                return
            import re as _re
            want = set(ids)
            updated, failed = [], []
            if cand_dir.exists():
                for f in sorted(cand_dir.glob("cand-*.md")):
                    d = mem.parse_note(f) or {}
                    nid = str(d.get("id"))
                    if nid not in want:
                        continue
                    try:
                        raw = f.read_text(encoding="utf-8")
                        if _re.search(r"^status:\s*\S+", raw, _re.M):
                            raw = _re.sub(r"^status:\s*\S+", f"status: {status}", raw, count=1, flags=_re.M)
                        else:
                            raw = raw.replace("---\n", f"---\nstatus: {status}\n", 1)
                        f.write_text(raw, encoding="utf-8")
                        updated.append(nid)
                    except OSError:
                        failed.append(nid)
            failed += [i for i in ids if i not in set(updated)]
            if updated:
                mem.build_index()
            self._json({"ok": not failed, "updated": updated, "failed": failed, "status": status})
            return
        if p == "/api/note":
            b = self._body()
            title = (b.get("title") or "").strip()
            if not title:
                self._json({"error": "title 必填"}, 400)
                return
            body = (b.get("body") or "").strip()
            ntype = b.get("type", "lesson") if b.get("type") in ("procedure", "lesson", "fact") else "lesson"
            status = b.get("status") if b.get("status") in ("active", "staged", "suspect", "superseded") else "staged"
            tags_raw = (b.get("tags") or "").strip()
            tags = [t.strip() for t in tags_raw.replace("，", ",").split(",") if t.strip()] or ["手动", "待整理"]
            nid = time.strftime("%Y%m%d-%H%M%S") + "-web"
            note = (f"---\nid: {nid}\ntype: {ntype}\nstatus: {status}\ntitle: {title}\n"
                    f"tags: [{', '.join(tags)}]\ncreated: {time.strftime('%Y-%m-%d')}\n---\n\n{body}\n")
            (BASE / "notes" / "lessons" / f"web-{nid}.md").write_text(note, encoding="utf-8")
            mem.build_index()
            self._json({"ok": True, "id": nid, "status": status})
            return
        if p.startswith("/api/note/"):
            parts = p.split("/")
            if len(parts) < 5:
                self._json({"error": "bad path"}, 400)
                return
            did, action = parts[3], parts[4]
            idx = cached_index()
            d = idx.get("docs", {}).get(did)
            if not d or not d.get("path"):
                self._json({"error": "not found"}, 404)
                return
            path = Path(d["path"])
            if action == "status":
                status = (self._body() or {}).get("status", "")
                if status not in ("active", "staged", "suspect", "superseded"):
                    self._json({"error": "bad status"}, 400)
                    return
                import re as _re
                raw = path.read_text(encoding="utf-8")
                if _re.search(r"^status:\s*\S+", raw, _re.M):
                    raw = _re.sub(r"^status:\s*\S+", f"status: {status}", raw, count=1, flags=_re.M)
                else:
                    raw = raw.replace("---\n", f"---\nstatus: {status}\n", 1)
                path.write_text(raw, encoding="utf-8")
                mem.build_index()
                self._json({"ok": True, "status": status})
                return
            if action == "unhot":
                import re as _re
                raw = path.read_text(encoding="utf-8")
                new = _re.sub(r"^hot:\s*(true|1|yes)\s*\n", "", raw, flags=_re.M)
                if new != raw:
                    path.write_text(new, encoding="utf-8")
                    mem.build_index()
                self._json({"ok": True})
                return
            if action == "edit":
                b = self._body()
                import re as _re
                raw = path.read_text(encoding="utf-8")
                head, _, rest = raw.partition("---\n")
                meta: dict[str, str] = {}
                for line in rest.split("\n---\n", 1)[0].splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
                if b.get("type"):
                    meta["type"] = b["type"]
                if b.get("status"):
                    meta["status"] = b["status"]
                if b.get("title"):
                    meta["title"] = b["title"].strip().replace("\n", " ")
                if "tags" in b:
                    meta["tags"] = "[" + ", ".join(f'"{t.strip()}"' for t in str(b["tags"]).split(",") if t.strip()) + "]"
                body_new = b.get("body") if "body" in b else d.get("body", "")
                text = "---\n" + "\n".join(f"{k}: {v}" for k, v in meta.items()) + "\n---\n\n" + body_new.strip() + "\n"
                path.write_text(text, encoding="utf-8")
                mem.build_index()
                self._json({"ok": True})
                return
            if action == "hot":
                import re as _re
                raw = path.read_text(encoding="utf-8")
                if not _re.search(r"^hot:\s*", raw, _re.M):
                    raw = raw.replace("---\n", "---\nhot: true\n", 1)
                else:
                    raw = _re.sub(r"^hot:\s*\S+", "hot: true", raw, count=1, flags=_re.M)
                path.write_text(raw, encoding="utf-8")
                mem.build_index()
                self._json({"ok": True})
                return
            self._json({"error": "unknown action"}, 400)
            return
        if p == "/api/extract":
            b = self._body()
            path = (b.get("path") or "").strip()
            if not path or not Path(path).exists():
                self._json({"error": "路径不存在"}, 400)
                return
            CHUNKS_ROOT.mkdir(parents=True, exist_ok=True)
            tid = _uuid.uuid4().hex[:10]
            CHUNKS_ROOT.mkdir(parents=True, exist_ok=True)
            _run_task(tid, [SYS_PY, str(BASE / "scripts" / "ingest.py"), "extract", path, "--out-dir", str(CHUNKS_ROOT)])
            self._json({"ok": True, "task_id": tid, "note": "后台提取中，轮询 /api/task/status"})
            return
        if p == "/api/harvest":
            tid = _uuid.uuid4().hex[:10]
            _run_task(tid, [sys.executable, str(BASE / "harvest.py"), "scan", "--days", "3"])
            self._json({"ok": True, "task_id": tid, "note": "后台收割中，轮询 /api/task/status"})
            return
        # /api/task/status 只在 do_GET 定义：任务进度是只读查询，POST 版是历史复制残留
        # （前端 index.js 轮询用 GET，全仓无 POST 调用方），保留两份只会让两份实现各自漂移。
        if p == "/api/hotsync":
            import subprocess as _sp
            target = str(BASE.parent / ".workbuddy" / "memory" / "MEMORY.md")
            cmd = [sys.executable, str(BASE / "mem.py"), "hot", "--limit", "20", "--apply", "--target", target]
            try:
                r = _sp.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=120)
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 500)
                return
            self._json({"ok": True, "output": ((r.stdout or "") + (r.stderr or ""))[-800:]})
            return
        if p == "/api/installhost":
            b = self._body()
            name = (b.get("host") or "").strip()
            dest = next((d for n, d in HOSTS if n == name), None)
            if not dest or not SKILL_TEMPLATE.exists():
                self._json({"error": "host 或模板不存在"}, 400)
                return
            dpath = Path(dest)
            try:
                dpath.parent.mkdir(parents=True, exist_ok=True)
                dpath.write_text(SKILL_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError as exc:
                self._json({"error": str(exc)}, 500)
                return
            self._json({"ok": True, "host": name, "path": dest})
            return
        if p == "/api/mcpinstall":
            b = self._body()
            key = (b.get("host") or "").strip()
            target = next((x for x in MCP_TARGETS if x[0] == key), None)
            if not target:
                self._json({"error": "未知宿主"}, 400)
                return
            _, label, files, fmt = target
            results = []
            for f in files:
                ok, msg = (mcp_install_json(f) if fmt == "json" else mcp_install_yaml(f))
                results.append({"path": f, "ok": ok, "msg": msg})
            self._json({"ok": True, "host": label, "results": results,
                        "note": "WorkBuddy/DSH 需重启宿主或新会话生效；WorkBuddy 还需在连接器管理页对新增 MCP 点 Trust。"})
            return
        if p == "/api/config/save":
            b = self._body()
            ok, msg = save_pmem_config(b)
            if not ok:
                self._json({"error": msg}, 500)
                return
            self._json({"ok": True, "file": msg,
                        "note": "已保存。重启 server/launcher 后生效（新路径的块库/空间将在重启后使用）。"})
            return
        self.send_error(404)

def main() -> int:
    from http.server import ThreadingHTTPServer
    Handler.protocol_version = "HTTP/1.1"  # keep-alive：省握手开销
    print(f"pmem Web 版启动：http://127.0.0.1:{PORT} （Ctrl+C 退出）")

    # 后台自动备份线程（按 pmem_backup.json 的 auto + interval_hours 到期执行）
    def _auto_loop():
        while True:
            try:
                backup.auto_sync_if_due()
            except Exception as exc:  # noqa: BLE001
                print(f"[auto-backup] 失败：{exc}", file=sys.stderr)
            time.sleep(backup.AUTO_CHECK_SECONDS)

    _threading.Thread(target=_auto_loop, daemon=True, name="pmem-auto-backup").start()

    # 自动收割线程：定时 harvest scan（会话证据 → 候选池，自动积累待审核）
    # 默认开启，环境变量 PMEM_NO_AUTO_HARVEST=1 可禁用
    if not os.environ.get("PMEM_NO_AUTO_HARVEST"):
        harvest_secs = int(os.environ.get("PMEM_AUTO_HARVEST_SECONDS", "3600"))

        def _harvest_loop():
            while True:
                try:
                    subprocess.run(
                        [sys.executable, str(BASE / "harvest.py"), "scan", "--days", "1"],
                        capture_output=True, text=True, timeout=300, cwd=str(BASE))
                    # 扫描后自动评审：多角色转正（仅 lesson）+ 否决项归档，防止候选池随收割爆满
                    subprocess.run(
                        [sys.executable, str(BASE / "mem.py"), "candidates", "auto", "--purge"],
                        capture_output=True, text=True, timeout=300, cwd=str(BASE))
                except Exception as exc:  # noqa: BLE001
                    print(f"[auto-harvest] 失败：{exc}", file=sys.stderr)
                time.sleep(harvest_secs)

        _threading.Thread(target=_harvest_loop, daemon=True, name="pmem-auto-harvest").start()

    # 引擎变更检测：mem.py 等改动后提示重启（进程是启动时代码快照）
    _engine_mtimes = {name: (BASE / name).stat().st_mtime
                      for name in ("mem.py", "backup.py", "harvest.py", "server.py") if (BASE / name).exists()}

    def _engine_watch():
        while True:
            try:
                for name, m in _engine_mtimes.items():
                    p = BASE / name
                    if p.exists() and p.stat().st_mtime > m:
                        print(f"[引擎变更] {name} 已在启动后被修改——当前进程仍是旧代码快照，"
                              f"请重启 server 使改动生效", file=sys.stderr)
                        _engine_mtimes[name] = p.stat().st_mtime  # 只提示一次
            except OSError:
                pass
            time.sleep(60)

    _threading.Thread(target=_engine_watch, daemon=True, name="pmem-engine-watch").start()

    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
