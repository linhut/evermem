#!/usr/bin/env python3
# pmem Web 版后端 —— 零依赖（Python 内置 http.server）+ JSON API
#
# Copyright (c) 2026 Jose-AI
# https://www.linhut.cn
# SPDX-License-Identifier: MIT
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

WEB = Path(__file__).resolve().parent
BASE = WEB.parent  # .memory
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import mem  # noqa: E402
import backup  # noqa: E402

PORT = int(os.environ.get("PMEM_WEB_PORT", "8765"))
INDEX_FILE = WEB / "index.html"

# ---------- 数据位置配置（可自由选择，env > 配置文件 > 默认） ----------
CONFIG_FILE = BASE / "pmem_config.json"
_DEFAULTS = {"home": str(BASE), "chunks": "F:/知识库数据/chunks", "spaces": "F:/"}


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
PY_ABS = os.environ.get("PMEM_SYS_PY", r"C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe")
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

    def _static(self, name: str, ctype: str):
        fp = WEB / name
        try:
            raw = fp.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        # 前端改动频繁，禁用缓存避免浏览器加载旧 JS 导致白页（Ctrl+F5 后永久生效）
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

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
        if p == "/index.js":
            self._static("index.js", "text/javascript; charset=utf-8")
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
            hot = mem.select_hot(idx, limit=20)
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
        if p == "/api/backup/log":
            lines = []
            try:
                lines = (backup.BASE / backup.LOG_FILE).read_text(encoding="utf-8", errors="ignore").splitlines()[-50:]
            except OSError:
                pass
            self._json({"lines": lines})
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
        self.send_error(404)

    # ---------- POST ----------
    def do_POST(self):
        u = urlparse(self.path)
        p = u.path
        if p == "/api/backup/save":
            b = self._body()
            auto = bool(b.get("auto", False))
            alert = (b.get("alert_email") or "").strip()
            channels = []
            for c in b.get("channels") or []:
                if not isinstance(c, dict) or c.get("type") not in backup.CHANNEL_TYPES:
                    continue
                scope = [s for s in (c.get("scope") or backup.ALL_SCOPES) if s in backup.SCOPE_GROUPS]
                try:
                    freq = max(1, int(c.get("frequency_hours", 24)))
                except (TypeError, ValueError):
                    freq = 24
                channels.append({
                    "type": c["type"], "name": str(c.get("name") or f"{c['type']}"),
                    "enabled": bool(c.get("enabled", True)),
                    "target": str(c.get("target") or "").strip(),
                    "scope": scope, "frequency_hours": freq,
                    "note": str(c.get("note") or ""),
                    "retention": int(c.get("retention", 7) or 7),
                    "ssh_port": int(c.get("ssh_port", 22) or 22),
                    "smtp": c.get("smtp") if isinstance(c.get("smtp"), dict) else {},
                })
            backup.save_cfg({"auto": auto, "alert_email": alert, "channels": channels})
            self._json(backup.sync_status())
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
            # 多角色评审全部候选，强共识且无否决者自动转正
            cand_dir = mem.NOTES / "candidates"
            idx = mem.load_index(force=False)
            promoted, kept, rejected = [], [], []
            if cand_dir.exists():
                for f in sorted(cand_dir.glob("cand-*.md")):
                    d = mem.parse_note(f) or {}
                    rv = mem.multi_role_review(d, idx)
                    if rv["verdict"] == "promote":
                        res = mem.promote_candidate(f, rv)
                        (promoted if res.get("ok") else rejected).append(d.get("id"))
                    elif rv["verdict"] == "keep":
                        kept.append(d.get("id"))
                    else:
                        rejected.append(d.get("id"))
            self._json({"reviewed": len(promoted) + len(kept) + len(rejected),
                        "promoted": promoted, "kept": kept, "rejected": rejected})
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
        if p == "/api/note":
            b = self._body()
            title = (b.get("title") or "").strip()
            if not title:
                self._json({"error": "title 必填"}, 400)
                return
            body = (b.get("body") or "").strip()
            ntype = b.get("type", "lesson")
            nid = time.strftime("%Y%m%d-%H%M%S") + "-web"
            note = (f"---\nid: {nid}\ntype: {ntype}\nstatus: staged\ntitle: {title}\n"
                    f"tags: [手动, 待整理]\ncreated: {time.strftime('%Y-%m-%d')}\n---\n\n{body}\n")
            (BASE / "notes" / "lessons" / f"web-{nid}.md").write_text(note, encoding="utf-8")
            mem.build_index()
            self._json({"ok": True, "id": nid, "status": "staged"})
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
            _run_task(tid, [SYS_PY, str(BASE / "ingest.py"), "extract", path, "--out-dir", str(CHUNKS_ROOT)])
            self._json({"ok": True, "task_id": tid, "note": "后台提取中，轮询 /api/task/status"})
            return
        if p == "/api/harvest":
            tid = _uuid.uuid4().hex[:10]
            _run_task(tid, [sys.executable, str(BASE / "harvest.py"), "scan", "--days", "3"])
            self._json({"ok": True, "task_id": tid, "note": "后台收割中，轮询 /api/task/status"})
            return
        if p == "/api/task/status":
            tid = parse_qs(u.query).get("task", [""])[0]
            st = _TASKS.get(tid)
            if not st:
                self._json({"error": "task 不存在"}, 404)
                return
            self._json(st)
            return
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
                except Exception as exc:  # noqa: BLE001
                    print(f"[auto-harvest] 失败：{exc}", file=sys.stderr)
                time.sleep(harvest_secs)

        _threading.Thread(target=_harvest_loop, daemon=True, name="pmem-auto-harvest").start()

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