#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# pmem Web 版后端 —— 零依赖（Python 内置 http.server）+ JSON API
#
#
# 启动：python web/server.py（解释器用 PMEM_SYS_PY 指定或当前 python）
# 打开：http://127.0.0.1:8765

from __future__ import annotations

import json
import os
import re
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
BASE = WEB.parent  # 代码目录（模板 / 脚本 / 前端资源 / 品牌资产）
BRAND = BASE / "brand"  # 品牌资源（logo/favicon）；冻结态随 --add-data brand 落到 _MEIPASS
# 数据目录与代码目录必须分开：冻结态下 BASE 落在临时解包目录，
# 把配置/备份/导入写到这里会在重启后消失，且与 mem.py 的核心检索不是同一个目录。
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
import paths as _paths  # noqa: E402
DATA_ROOT = _paths.data_root()
CODE_ROOT = _paths.code_root()
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

import mem  # noqa: E402
import backup  # noqa: E402
try:  # 更新检查是可选能力：模块缺失时接口报不可用，但服务照常启动
    import update
except Exception:  # noqa: BLE001
    update = None  # type: ignore
try:  # 导入模块依赖 harvest.redact；缺了也要能起服务，接口里另有兜底
    import memimport  # noqa: E402
except Exception:  # noqa: BLE001
    memimport = None  # type: ignore

PORT = int(os.environ.get("PMEM_WEB_PORT", "8765"))
INDEX_FILE = WEB / "index.html"

# ---------- 数据位置配置（可自由选择，env > 配置文件 > 默认） ----------
# 配置写在数据目录：界面保存的位置必须就是 mem.py / backup.py 读取的位置
CONFIG_FILE = _paths.config_file()
# 数据位置配置（env > pmem_config.json > 默认）：发布可移植，勿写死机器路径；
# 本机实际位置请在界面「数据位置」设置，或设 PMEM_HOME（配置已在 .gitignore，数据与代码分离）
_DEFAULTS = {
    "home": str(DATA_ROOT),
    "chunks": os.environ.get("PMEM_CHUNKS", str(DATA_ROOT / "chunks")),
    "spaces": os.environ.get("PMEM_SPACES", str(DATA_ROOT)),
}

def load_pmem_config() -> dict:
    return _paths.load_config()

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

def _import_desktop_module():
    """仅在桌面壳内导入 desktop（它带 GUI 依赖，独立 server 模式不该 import）。

    desktop.py 顶层只做惰性导入与常量定义，import 本身不会起窗口，可以安全调用。
    """
    if os.environ.get("PMEM_DESKTOP", "").strip() != "1":
        return None
    try:
        import desktop  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    return desktop


def _autostart_info() -> dict:
    """开机自启能力探测：桌面壳 + 平台支持才算可用。"""
    d = _import_desktop_module()
    if d is None:
        return {"supported": False, "enabled": False, "platform": sys.platform,
                "reason": "当前不是桌面壳运行（浏览器模式无系统自启权限）"}
    if not (sys.platform == "win32" or sys.platform == "darwin" or sys.platform.startswith("linux")):
        return {"supported": False, "enabled": False, "platform": sys.platform,
                "reason": f"当前平台不支持开机自启：{sys.platform}"}
    try:
        return {"supported": True, "enabled": bool(d.autostart_enabled()), "platform": sys.platform}
    except Exception as exc:  # noqa: BLE001
        return {"supported": False, "enabled": False, "platform": sys.platform,
                "reason": f"读取自启状态失败：{exc}"}


def save_pmem_config(patch: dict) -> tuple[bool, str]:
    """保存数据位置配置（跨会话一致：写 pmem_config.json，所有进程读同一文件）。"""
    cfg = load_pmem_config()
    for k in ("home", "chunks", "spaces"):
        if k in patch and patch[k] is not None:
            cfg[k] = str(patch[k]).strip()
    try:
        _atomic_write(CONFIG_FILE, json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
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
    ("Marvis (腾讯马维斯)", str(Path.home() / ".marvis" / "skills" / "custom" / "personal-memory" / "SKILL.md")),
]
SKILL_TEMPLATE = CODE_ROOT / "templates" / "personal-memory.SKILL.md"

# 宿主前置条件：不是所有技能目录都"建出来就能用"。
# Marvis 的 ~/.marvis 是指向 %APPDATA%\Tencent\Marvis\User\<openid> 的符号链接，未登录客户端时不存在。
# 此时若照着 dest 直接 mkdir，会凭空造出 C:\Users\<you>\.marvis 真目录：界面显示「已安装」但 Marvis 读不到，
# 而且会挡住客户端日后建立同名链接 —— 属于"假成功 + 破坏环境"，必须前置拦下。
HOST_PREREQ = {
    "Marvis (腾讯马维斯)": (
        Path.home() / ".marvis",
        "未检测到 Marvis 用户目录（~/.marvis）：请先安装并登录腾讯马维斯客户端。"
        "若已登录仍看不到，重启一次客户端再回本页。",
    ),
}

def host_prereq(name: str) -> tuple[bool, str]:
    """宿主是否具备安装条件。返回 (ok, 不满足时的原因)；无前置要求的宿主恒为 True。"""
    req = HOST_PREREQ.get(name)
    if not req:
        return True, ""
    root, hint = req
    try:
        if root.exists():
            return True, ""
    except OSError:  # 断链符号链接 / 权限不足，一律按不满足处理
        pass
    return False, hint

def _hot_target() -> Path:
    """核心经验同步目标：宿主每次会话读取的 MEMORY.md。

    优先级：PMEM_HOT_TARGET 环境变量（显式指定，跨形态最可靠）
    > 源码态 BASE.parent = 知识库工作区（宿主在此读取 MEMORY.md）
    > 冻结态回退探测 home / 数据根上级 / cwd 的 .workbuddy（用户工作区常在主目录
      或数据根旁边），仍无则退回程序目录旁的默认（会在下次同步时自动创建）。
    """
    env = os.environ.get("PMEM_HOT_TARGET", "").strip()
    if env:
        return Path(env).expanduser()
    cfg = load_pmem_config()
    if cfg.get("hot_target"):
        return Path(cfg["hot_target"]).expanduser()
    base_target = Path(BASE.parent / ".workbuddy" / "memory" / "MEMORY.md")
    if not getattr(sys, "frozen", False):
        return base_target
    for root in (Path.home(), DATA_ROOT.parent, Path.cwd()):
        cand = root / ".workbuddy" / "memory" / "MEMORY.md"
        if cand.exists():
            return cand
    return base_target


# ---------- MCP 一键安装配置（各宿主） ----------
def _default_py() -> str:
    """系统 Python 解释器探测：PMEM_SYS_PY > 含文档库的系统 Python > PATH python。

    冻结态（PyInstaller 打包）下 sys.executable 是 Evermem 自己——**绝不能**把它当
    解释器去起子进程（ingest.py 提取 / MCP 服务器），否则参数会被当作 GUI 启动参数，
    再开一个程序窗口且脚本根本不执行（harvest 同款坑，此处一并预防）。
    探测到的解释器还要**验证能 import python-docx/pypdf**（文档提取的硬依赖），
    避免选中一个"存在但缺库"的 python 让 /api/extract 静默失败。
    """
    env = os.environ.get("PMEM_SYS_PY", "").strip()
    if env:
        return env
    import subprocess as _sp
    candidates = []
    if not getattr(sys, "frozen", False):
        candidates.append(sys.executable)
    for c in (_shutil.which("python"), _shutil.which("python3"),
              str(Path("C:/Python314/python.exe")) if os.name == "nt" else None):
        if c:
            candidates.append(str(c))
    for cand in candidates:
        if not cand or not Path(cand).exists():
            continue
        try:
            r = _sp.run([cand, "-c", "import docx, openpyxl, pypdf"],
                        capture_output=True, timeout=30)
            if r.returncode == 0:
                return cand
        except Exception:  # noqa: BLE001 - 探测失败换下一个候选
            continue
    # 找不到可用的：返回 PATH 上的 python 让子进程自行报错，至少不回退到 Evermem 自己
    for cand in (_shutil.which("python"), _shutil.which("python3")):
        if cand:
            return str(cand)
    return "python"

PY_ABS = _default_py()
MCP_SCRIPT = str(CODE_ROOT / "evermem_mcp.py")
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
        _atomic_write(p, json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
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
        _atomic_write(p, raw.rstrip() + "\n" + block, encoding="utf-8")
        return True, str(p)
    except OSError as exc:
        return False, str(exc)

# ---------- 异步任务系统（extract/harvest 不阻塞 UI，含失败重试） ----------
import threading as _threading
import uuid as _uuid

_TASKS: dict[str, dict] = {}

def _atomic_write(path: Path, text: str, encoding: str = "utf-8") -> None:
    """原子写：先写临时文件再 os.replace。

    服务是 ThreadingHTTPServer 多线程，且可能和 MCP 常驻、CLI、后台任务并发写同一批文件；
    直接 write_text 中途被打断会留下截断的 JSON/Markdown（表现为"记忆无声消失"）。
    """
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    try:
        tmp.write_text(text, encoding=encoding)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _parse_note_or_none(path):
    """读笔记/候选文件；读不到返回 None，调用方必须跳过而不是当成空笔记。

    并发写者（收割 / MCP / 导入器 / CLI）可能在读者眼皮底下改文件。只要有一个
    文件读失败就让整个列表接口 500，界面会误报「服务未响应」；更糟的是自动评审
    会把"读空"的候选判为低质而错误归档。所以单文件失败一律降级为跳过。
    """
    try:
        return mem.parse_note(path)
    except Exception:  # noqa: BLE001 - 单个文件异常不能打死整表
        return None


def _read_note_text(path) -> str | None:
    """读笔记原文；读失败返回 None，调用方必须**放弃本次写**。

    这是 read-modify-write 的前置读：读到被并发写截断的内容又落盘，笔记正文会被
    永久截短——不是报错，是内容无声消失。宁可返回 409 让用户重试。
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


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
    _threading.Thread(target=_worker, daemon=True,
                      name=f"pmem-task-{task_id[:8]}").start()


def _run_inline_task(task_id: str, fn) -> None:
    """同进程任务执行：fn 在后台线程运行并自行更新 _TASKS[task_id]。

    与 _run_task 的区别：后者接受子进程命令列表；下载/进度类任务需要在进程内
    跑 Python 函数并持续上报 progress，不能走子进程（冻结态下 sys.executable 是自己）。
    """

    def _worker():
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            _TASKS[task_id] = {"state": "error", "output": f"任务异常：{exc}"}

    # 若调用方已预建任务对象（如带 progress 的下载任务），不覆盖它——fn 更新同一引用
    if task_id not in _TASKS:
        _TASKS[task_id] = {"state": "running", "output": "",
                           "started": time.strftime("%H:%M:%S")}
    _threading.Thread(target=_worker, daemon=True,
                      name=f"pmem-inline-{task_id[:8]}").start()


TYPE_LABEL = {"fact": "事实", "lesson": "经验", "procedure": "配方"}

# 「来源是本地绝对路径」判定 —— 盘符无关。
#   ① Windows 盘符前缀（C:\ / D:/，任意位置）
#   ② UNC 共享（\\host\share）
#   ③ POSIX 绝对路径（只认行首或分隔符之后，避免把 URL 片段 /api/xxx 误判成文件路径）
# 旧实现写死 "F:/"，换个盘符或换到 macOS/Linux 就整体失效，也违反「代码不得出现用户盘符」的发布约定。
_ABS_PATH_RE = re.compile(r"[A-Za-z]:[\\/]|\\\\[^\\/\s]+[\\/]|(?:^|[;、,，\n])/[^\s/*]")

def provenance_of(source: str, tags: list, note_id: str) -> str:
    """判定记忆来源通道（界面显示来源图标）。"""
    s = source or ""
    t = "".join(tags or [])
    if _ABS_PATH_RE.search(s):
        return "doc"        # 文档提炼（来源为本地资料文件/目录）
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

    # 标记 HEAD 请求：各 _bytes/_json/_html 只回头部、不写 body（POST/GET 不受影响）。
    head_only = False

    # ---------- 工具 ----------
    def _json(self, obj: dict, code: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not self.head_only:
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
        if not self.head_only:
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
        if not self.head_only:
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

    def _host_ok(self) -> bool:
        # 防 DNS rebinding / 恶意网页调用本地 API：只接受本机 Host。
        # 本服务绑定 127.0.0.1 无鉴权，Host 校验是成本最低的一道闸。
        host = self.headers.get("Host", "").strip()
        if not host:
            return False
        h = host.split(":", 1)[0].strip().strip("[]").lower()
        if h not in ("127.0.0.1", "localhost", "::1"):
            return False
        # CSRF 第二道闸：跨站简单请求（text/plain 等不触发预检）Host 天然就是
        # 127.0.0.1:PORT，Host 校验拦不住，必须再核 Origin。
        #   · 无 Origin（curl / CLI / 同源 GET）：放行
        #   · Origin 与本服务同源（http://127.0.0.1:PORT / localhost）：放行
        #   · 其余（跨站、Origin:null 的 no-cors 探测）：拒绝
        origin = self.headers.get("Origin", "").strip().rstrip("/")
        if origin:
            port = self.server.server_address[1]
            allowed = {f"http://127.0.0.1:{port}", f"http://localhost:{port}",
                       "http://127.0.0.1", "http://localhost"}
            if origin not in allowed:
                return False
        return True

    # ---------- HEAD / OPTIONS ----------
    def do_HEAD(self):
        """HEAD：与 GET 同路由（校验/分发一致），但不返回 body。

        Python 标准库 BaseHTTPRequestHandler 对未实现的 do_HEAD 一律回 501
        （历史现象：浏览器/QWebEngine 探测 favicon、curl -I、健康探针发 HEAD
        → "501 Unsupported method ('HEAD')"，被误报为服务故障）。补上以消除。
        """
        self.head_only = True
        try:
            self._do_GET()
        except Exception as exc:  # noqa: BLE001 - 与 GET 一致的异常兜底
            try:
                self._json({"ok": False, "error": f"内部错误：{type(exc).__name__}"}, 500)
            except Exception:
                pass
        finally:
            self.head_only = False

    def do_OPTIONS(self):
        """OPTIONS：预检请求（CORS preflight / 探测）——回允许的方法即可。

        同样由 BaseHTTPRequestHandler 默认 501；补上避免前端预检报错。
        本地服务无跨域需求，Allow 恒为 GET/HEAD/POST + OPTIONS 本身。
        """
        self.send_response(204)
        self.send_header("Allow", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---------- GET ----------
    def do_GET(self):
        """GET 入口：异常兜底，任何路由抛错都不打挂服务。"""
        try:
            self._do_GET()
        except Exception as exc:  # noqa: BLE001 - 未知异常不能打死服务
            try:
                self._json({"ok": False, "error": f"内部错误：{type(exc).__name__}"}, 500)
            except Exception:
                pass

    def _do_GET(self):
        if not self._host_ok():
            self.send_error(403, "host not allowed")
            return
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
        # 浏览器会自动请求 /favicon.ico，映射到品牌 favicon（要在静态通配前命中）
        if p == "/favicon.ico":
            try:
                self._bytes((BRAND / "favicon.ico").read_bytes(), static_ext[".ico"])
                return
            except OSError:
                pass
            self.send_error(404)
            return
        # 品牌资源：/brand/ 路由，供前端、README、安装包统一引用。
        # 单独路由避免把 brand/ 放进 web/ 导致重复；--add-data brand 在冻结态保证可用。
        if p.startswith("/brand/"):
            try:
                rel = Path(p[len("/brand/"):].replace("\\", "/"))
                full = (BRAND / rel).resolve()
                if (str(full).startswith(str(BRAND.resolve())) and full.is_file()
                        and suffix in static_ext):
                    self._bytes(full.read_bytes(), static_ext[suffix])
                    return
            except OSError:
                pass
            self.send_error(404)
            return
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
                d = _parse_note_or_none(f)
                if not d:
                    continue
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
            skipped = 0
            idx = cached_index()
            if cand_dir.exists():
                now = time.time()
                for f in sorted(cand_dir.glob("cand-*.md")):
                    d = _parse_note_or_none(f)
                    if not d:
                        # 并发写入留下的半成品文件：跳过这一条，不能让整表 500
                        skipped += 1
                        continue
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
                        "skipped": skipped,
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
            # 只扫描用户声明的知识空间（SPACES_ROOT）内的目录，拒绝任意路径探测
            try:
                if not root.resolve().is_relative_to(SPACES_ROOT.resolve()):
                    self._json({"error": "越界：只能扫描知识空间目录"}, 403)
                    return
            except OSError:
                self._json({"error": "路径不可解析"}, 400)
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
            full = Path(path)
            try:
                full = full.resolve()
            except OSError:
                self._json({"error": "路径不可解析"}, 400)
                return
            # 只允许读块库或知识空间内的文件，拒绝任意路径读取（曾可读 C:\Users\...\id_rsa 等）
            if not (full.is_file()
                    and (full.is_relative_to(CHUNKS_ROOT.resolve()) or full.is_relative_to(SPACES_ROOT.resolve()))):
                self._json({"error": "越界或非文件"}, 403)
                return
            try:
                text = full.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                self._json({"error": "read failed"}, 404)
                return
            self._json({"path": str(full), "text": text[:5000]})
            return
        if p == "/api/hosts":
            hosts = []
            for name, dest in HOSTS:
                installed = Path(dest).exists()
                ts = time.strftime("%m-%d %H:%M", time.localtime(Path(dest).stat().st_mtime)) if installed else None
                ready, hint = host_prereq(name)
                hosts.append({"name": name, "path": dest, "installed": installed, "updated": ts,
                              "ready": ready, "hint": hint})
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
            cur = {"home": str(DATA_ROOT), "chunks": str(CHUNKS_ROOT), "spaces": str(SPACES_ROOT),
                   "config_file": str(CONFIG_FILE)}
            self._json({"current": cur,
                        "checks": {k: path_check(str(Path(v))) for k, v in cur.items()},
                        "note": "配置优先级：环境变量 > pmem_config.json > 默认；修改后重启 server/launcher 生效。跨会话一致：所有进程读同一配置文件。"})
            return
        if p == "/api/autostart":
            """开机自启状态：只在桌面壳内可用（PMEM_DESKTOP=1），
            纯浏览器/独立 server 模式必须如实报 unsupported，前端据此禁用开关。"""
            info = _autostart_info()
            self._json(info)
            return
        if p == "/api/version":
            """读取 VERSION 文件，返回当前版本和官方发布页，供「检查更新」入口使用。"""
            version = "unknown"
            try:
                version = (CODE_ROOT / "VERSION").read_text(encoding="utf-8").strip()
            except Exception:
                pass
            self._json({
                "version": version,
                "releases_url": "https://github.com/linhut/evermem/releases/latest",
                "form": update.install_form() if update is not None else "portable",
                "installed": _paths.is_installed(),
            })
            return
        if p == "/api/update/check":
            """多源更新检查：自建清单 → GitHub 直连/镜像。
            全部源不可用必须返回 ok=False + attempts，由前端明确提示，不允许静默说"已是最新"。"""
            if update is None:
                self._json({"ok": False, "error": "更新模块不可用"}, 500)
                return
            q = parse_qs(u.query)
            force = str(q.get("force", ["0"])[0]).strip() in ("1", "true", "yes")
            try:
                self._json(update.check(force=force))
            except Exception as exc:  # noqa: BLE001 - 网络异常不能打挂服务
                self._json({"ok": False, "error": f"检查失败：{exc}"}, 500)
            return
        if p == "/api/update/sources":
            if update is None:
                self._json({"error": "更新模块不可用"}, 500)
                return
            self._json(update.sources_info())
            return
        if p == "/api/profile/prompt":
            # 「其他记忆导入」页的「导出记忆提示词」卡片数据源：直接读模板里的 COPY 区间。
            # 提示词只有一份事实源（templates/usage-profile.prompt.md），前端不硬编码。
            # 必须用 CODE_ROOT（代码目录）：mem.ROOT 是**数据根**，模板不在那里，
            # 写错会永远报「模板未找到」——曾实际发生。
            tpl = CODE_ROOT / "templates" / "usage-profile.prompt.md"
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
        """POST 入口：异常兜底（曾因 SYS_PY 未定义直接 NameError 断连，前端只看到"处理中"）。"""
        try:
            self._do_POST()
        except Exception as exc:  # noqa: BLE001 - 未知异常不能打死服务
            try:
                self._json({"ok": False, "error": f"内部错误：{type(exc).__name__}"}, 500)
            except Exception:
                pass

    def _do_POST(self):
        if not self._host_ok():
            self.send_error(403, "host not allowed")
            return
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
                    d = _parse_note_or_none(f)
                    if not d:
                        # 读到半成品会被判成"空/过短"→ 错误归档，必须跳过
                        continue
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
                    d = _parse_note_or_none(f)
                    if not d:
                        continue
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
            if not ids:
                # 拒绝空 ids：无明确目标时绝不批量移动。
                # 旧实现存在"空 ids 自动归档全部≥60天候选"的隐蔽分支，正是 CSRF 的攻击面
                # （跨站 text/plain POST 会解析成 {} → ids 为空 → 批量归档）。已移除。
                self._json({"error": "ids 必填"}, 400)
                return
            moved = []
            if cand_dir.exists():
                for f in sorted(cand_dir.glob("cand-*.md")):
                    d = _parse_note_or_none(f)
                    if not d:
                        continue
                    if str(d.get("id")) in ids:
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
                    d = _parse_note_or_none(f)
                    if not d:
                        continue
                    nid = str(d.get("id"))
                    if nid not in want:
                        continue
                    raw = _read_note_text(f)
                    if raw is None:
                        # 读不到原文就不能改写：否则会把半成品当成新正文落盘
                        failed.append(nid)
                        continue
                    try:
                        if _re.search(r"^status:\s*\S+", raw, _re.M):
                            raw = _re.sub(r"^status:\s*\S+", f"status: {status}", raw, count=1, flags=_re.M)
                        else:
                            raw = raw.replace("---\n", f"---\nstatus: {status}\n", 1)
                        _atomic_write(f, raw)
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
            title = (b.get("title") or "").strip().replace("\n", " ").replace("\r", " ")
            if not title:
                self._json({"error": "title 必填"}, 400)
                return
            body = (b.get("body") or "").strip()
            ntype = b.get("type", "lesson") if b.get("type") in ("procedure", "lesson", "fact") else "lesson"
            status = b.get("status") if b.get("status") in ("active", "staged", "suspect", "superseded") else "staged"
            tags_raw = (b.get("tags") or "").strip()
            tags = [t.strip() for t in tags_raw.replace("，", ",").split(",") if t.strip()] or ["手动", "待整理"]
            # 毫秒级 id：原来只到秒，同秒新建会生成同名文件互相覆盖（曾实际发生）
            nid = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}-web"
            # 按类型落目录（procedure/procedures、fact/facts、lesson/lessons），原来一律写 lessons/
            ntype_dir = {"procedure": "procedures", "fact": "facts", "lesson": "lessons"}.get(ntype, "lessons")
            note = (f"---\nid: {nid}\ntype: {ntype}\nstatus: {status}\ntitle: {title}\n"
                    f"tags: [{', '.join(tags)}]\ncreated: {time.strftime('%Y-%m-%d')}\n---\n\n{body}\n")
            target = mem.NOTES / ntype_dir / f"web-{nid}.md"
            # 类型目录按需创建（双保险）：数据根由旧版本创建、或用户手工指定了空目录时，
            # 这里没有子目录就会 FileNotFoundError → 界面显示「内部错误」，表现为"新装就用不了"。
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                self._json({"error": "id 冲突，请重试"}, 409)
                return
            _atomic_write(target, note)
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
                raw = _read_note_text(path)
                if raw is None:
                    self._json({"error": "原笔记读取失败（可能正被并发写入），请稍后重试"}, 409)
                    return
                if _re.search(r"^status:\s*\S+", raw, _re.M):
                    raw = _re.sub(r"^status:\s*\S+", f"status: {status}", raw, count=1, flags=_re.M)
                else:
                    raw = raw.replace("---\n", f"---\nstatus: {status}\n", 1)
                _atomic_write(path, raw)
                mem.build_index()
                self._json({"ok": True, "status": status})
                return
            if action == "unhot":
                import re as _re
                raw = _read_note_text(path)
                if raw is None:
                    self._json({"error": "原笔记读取失败（可能正被并发写入），请稍后重试"}, 409)
                    return
                new = _re.sub(r"^hot:\s*(true|1|yes)\s*\n", "", raw, flags=_re.M)
                if new != raw:
                    _atomic_write(path, new)
                    mem.build_index()
                self._json({"ok": True})
                return
            if action == "edit":
                b = self._body()
                import re as _re
                raw = _read_note_text(path)
                if raw is None:
                    self._json({"error": "原笔记读取失败（可能正被并发写入），请稍后重试"}, 409)
                    return
                head, _, rest = raw.partition("---\n")
                meta: dict[str, str] = {}
                for line in rest.split("\n---\n", 1)[0].splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
                if b.get("type"):
                    if b["type"] not in ("procedure", "lesson", "fact"):
                        self._json({"error": "bad type"}, 400)
                        return
                    meta["type"] = b["type"]
                if b.get("status"):
                    if b["status"] not in ("active", "staged", "suspect", "superseded"):
                        self._json({"error": "bad status"}, 400)
                        return
                    meta["status"] = b["status"]
                if b.get("title"):
                    meta["title"] = b["title"].strip().replace("\n", " ")
                if "tags" in b:
                    # 防 frontmatter 注入：tag 值过滤引号与换行，避免破坏笔记元数据结构
                    clean_tag = lambda t: t.strip().replace('"', "").replace("\n", " ").replace("\r", " ")
                    tags_clean = [clean_tag(t) for t in str(b["tags"]).split(",") if clean_tag(t)]
                    meta["tags"] = "[" + ", ".join(f'"{t}"' for t in tags_clean) + "]"
                snap = _parse_note_or_none(path)
                if snap is None:
                    # 读不到原文件就绝不能落盘：body_old 会变空串，把正文清空
                    self._json({"error": "原笔记读取失败（可能正被并发写入），请稍后重试"}, 409)
                    return
                body_old = snap.get("body", "")
                # 索引瘦身后 docs 不存正文全文（仅 snippet 200 字）；未传 body 时禁止用
                # d.get("body") 兜底——会拿截断摘要覆盖全文导致笔记内容丢失。改读原文件保留。
                body_new = b.get("body") if "body" in b else body_old
                text = "---\n" + "\n".join(f"{k}: {v}" for k, v in meta.items()) + "\n---\n\n" + body_new.strip() + "\n"
                _atomic_write(path, text)
                mem.build_index()
                self._json({"ok": True})
                return
            if action == "hot":
                import re as _re
                raw = _read_note_text(path)
                if raw is None:
                    self._json({"error": "原笔记读取失败（可能正被并发写入），请稍后重试"}, 409)
                    return
                if not _re.search(r"^hot:\s*", raw, _re.M):
                    raw = raw.replace("---\n", "---\nhot: true\n", 1)
                else:
                    raw = _re.sub(r"^hot:\s*\S+", "hot: true", raw, count=1, flags=_re.M)
                _atomic_write(path, raw)
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
            # 冻结态下 PY_ABS 已是"非 Evermem 自己"的系统 Python（_default_py 冻结态跳过
            # sys.executable）。但系统 Python 未必装了 python-docx/pypdf——提前探测，
            # 缺依赖直接报明原因，避免静默失败（曾表现为点「提取」没反应/再开窗口）。
            try:
                import subprocess as _sp
                _probe = _sp.run(
                    [PY_ABS, "-c", "import docx, openpyxl, pypdf"],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="ignore", timeout=30)
                if _probe.returncode != 0:
                    self._json({"error": "文档提取需要系统 Python 且装有 python-docx / "
                                        "openpyxl / pypdf；请安装或用 PMEM_SYS_PY 指定后重试。"
                                        f"（{PY_ABS}）"}, 400)
                    return
            except Exception as _exc:  # noqa: BLE001 - 探测超时/解释器不可执行
                self._json({"error": f"无法执行文档提取解释器 {PY_ABS}：{_exc}"}, 400)
                return
            CHUNKS_ROOT.mkdir(parents=True, exist_ok=True)
            tid = _uuid.uuid4().hex[:10]
            _run_task(tid, [PY_ABS, str(CODE_ROOT / "scripts" / "ingest.py"), "extract", path, "--out-dir", str(CHUNKS_ROOT)])
            self._json({"ok": True, "task_id": tid, "note": "后台提取中，轮询 /api/task/status"})
            return
        if p == "/api/harvest":
            tid = _uuid.uuid4().hex[:10]
            # 同进程收割：不能启子进程 [sys.executable, harvest.py] —— 冻结态下
            # sys.executable 是 Evermem 自己，会把参数当 GUI 启动参数再开一个程序窗口
            # （desktop.py 的自动收割早有同款注释警告）。同进程调用能拿到 print 输出，
            # 收割完自动 reindex，让新候选立即可检索。
            def _harvest_worker():
                try:
                    from argparse import Namespace
                    import io as _io
                    import contextlib as _cl
                    import harvest as _harvest
                    buf = _io.StringIO()
                    with _cl.redirect_stdout(buf), _cl.redirect_stderr(buf):
                        rc = _harvest.cmd_scan(Namespace(days=3, min_failures=2, limit=20,
                                                         dry_run=False, include_pure_failure=False,
                                                         no_task_level=False))
                    text = buf.getvalue()
                    if not _TASKS.get(tid):
                        _TASKS[tid] = {"state": "running", "output": ""}
                    if rc != 0:
                        _TASKS[tid] = {"state": "error", "output": text[-800:] or f"收割返回码 {rc}"}
                        return
                    # 收割写入候选后重建索引，新候选立即可检索（自动收割线程同一做法）
                    try:
                        idx = mem.build_index()
                        terms = len(idx.get("postings", {}))
                        built = f"\n[索引] 重建完成：{idx.get('doc_count', '?')} 条笔记，{terms} 个词项"
                    except Exception as _e:  # noqa: BLE001 - 索引失败不影响收割结果展示
                        built = f"\n[索引] 重建失败：{_e}"
                    _TASKS[tid] = {"state": "done", "output": (text + built)[-1500:], "rc": rc}
                except Exception as exc:  # noqa: BLE001
                    _TASKS[tid] = {"state": "error", "output": f"收割异常：{exc}"}

            _TASKS[tid] = {"state": "running", "output": "正在扫描会话记录…\n"}
            _threading.Thread(target=_harvest_worker, daemon=True,
                              name=f"pmem-harvest-{tid[:8]}").start()
            self._json({"ok": True, "task_id": tid, "note": "后台收割中，轮询 /api/task/status"})
            return
        # /api/task/status 只在 do_GET 定义：任务进度是只读查询，POST 版是历史复制残留
        # （前端 index.js 轮询用 GET，全仓无 POST 调用方），保留两份只会让两份实现各自漂移。
        if p == "/api/hotsync":
            # 同进程执行：冻结态下 sys.executable 是 Evermem 自己，启子进程会把参数当
            # GUI 启动参数再开一个程序窗口（desktop.py 自动收割的同款坑）。mem 已在
            # 顶部 import，直接调 cmd_hot 拿 print 输出。
            # 目标：优先「宿主会话读取的工作区 MEMORY.md」（BASE.parent 即代码目录上级，
            # 源码态=知识库工作区；冻结态需回落 data_root 上级），不存在时创建空文件——
            # cmd_hot 要求目标已存在，缺失直接报错（曾因此"同步成功但宿主读不到"）。
            try:
                import io as _io
                import contextlib as _cl
                from argparse import Namespace as _NS
                target = _hot_target()
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_text("", encoding="utf-8")
                buf = _io.StringIO()
                with _cl.redirect_stdout(buf), _cl.redirect_stderr(buf):
                    rc = mem.cmd_hot(_NS(action="list", limit=20, apply=True,
                                         reindex=False, auto_fill=False,
                                         include_auto=False, tokens=None,
                                         digest=45, target=str(target)))
                out = buf.getvalue()
                if rc != 0:
                    self._json({"ok": False, "error": out[-500:] or f"hot 返回码 {rc}"}, 500)
                    return
                self._json({"ok": True, "output": out[-800:], "target": str(target)})
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 500)
            return
        if p == "/api/installhost":
            b = self._body()
            name = (b.get("host") or "").strip()
            dest = next((d for n, d in HOSTS if n == name), None)
            if not dest or not SKILL_TEMPLATE.exists():
                self._json({"error": "host 或模板不存在"}, 400)
                return
            ready, hint = host_prereq(name)
            if not ready:
                # 409：宿主环境未就绪，拒绝创建 —— 见 HOST_PREREQ 注释（Marvis 的 .marvis 是符号链接）
                self._json({"error": hint, "prereq": False}, 409)
                return
            dpath = Path(dest)
            try:
                text = SKILL_TEMPLATE.read_text(encoding="utf-8")
                dpath.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(dpath, text, encoding="utf-8")
                # 回读校验：只写不验会出现"提示成功但实际没落盘"（磁盘满、被杀软拦、被重定向）
                if dpath.read_text(encoding="utf-8") != text:
                    self._json({"error": "写入后回读不一致：" + str(dpath)}, 500)
                    return
            except OSError as exc:
                self._json({"error": str(exc)}, 500)
                return
            self._json({"ok": True, "host": name, "path": dest,
                        "bytes": len(text.encode("utf-8"))})
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
        if p == "/api/update/sources/save":
            """保存更新源配置：写完回读真实值，界面显示的就是实际生效的配置。"""
            if update is None:
                self._json({"ok": False, "error": "更新模块不可用"}, 500)
                return
            b = self._body()
            try:
                cfg = update.save_config(b if isinstance(b, dict) else {})
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"保存失败：{exc}"}, 500)
                return
            self._json({"ok": True, "config": cfg, "file": str(update.config_file())})
            return
        if p == "/api/update/download":
            """P2 内置下载：后台线程下载到 <数据根>/updates/，进度经 /api/task/status 轮询。"""
            if update is None:
                self._json({"ok": False, "error": "更新模块不可用"}, 500)
                return
            b = self._body() or {}
            asset = b.get("asset") or {}
            if not str(asset.get("name") or "").strip() or not (asset.get("urls") or []):
                self._json({"error": "资产参数缺失（name/urls 必填）"}, 400)
                return
            tid = _uuid.uuid4().hex[:10]
            state = {"progress": {"done": 0, "total": int(asset.get("size") or 0) or None,
                                  "phase": "排队中"}, "state": "running",
                     "output": "", "started": time.strftime("%H:%M:%S")}
            _TASKS[tid] = state

            def _dl():
                def cb(done, total):
                    state["progress"] = {"done": done, "total": total, "phase": "下载中"}
                try:
                    res = update.download(asset, progress_cb=cb)
                    if res.get("ok"):
                        state.update({"state": "done",
                                      "output": f"下载完成：{res['path']}（{res['source']}）"})
                    else:
                        state.update({"state": "error", "output": res.get("error", "下载失败")})
                except Exception as exc:  # noqa: BLE001
                    state.update({"state": "error", "output": f"下载异常：{exc}"})

            _run_inline_task(tid, _dl)  # 同进程下载（可上报进度；不能走子进程）
            self._json({"ok": True, "task_id": tid, "note": "后台下载中，轮询 /api/task/status"})
            return
        if p == "/api/update/apply":
            """P3 一键替换（Windows 打包版）：暂存→备份 .old→延迟替换→重启→失败回滚。"""
            if update is None:
                self._json({"ok": False, "error": "更新模块不可用"}, 500)
                return
            b = self._body() or {}
            name = str(b.get("name") or "").strip()
            if not name:
                self._json({"error": "name 必填"}, 400)
                return
            pkg = update.updates_dir() / update._safe_filename(name)
            if not pkg.is_file():
                self._json({"error": f"更新包不存在：{pkg.name}"}, 404)
                return
            r = update.apply_update(str(pkg))
            self._json(r)
            return
        if p == "/api/update/sources/test":
            """P1 逐源测试：对指定 URL 发一次请求，报告可用性与耗时（不缓存结果）。"""
            if update is None:
                self._json({"ok": False, "error": "更新模块不可用"}, 500)
                return
            b = self._body() or {}
            url = str(b.get("url") or "").strip()
            if not url:
                self._json({"error": "url 必填"}, 400)
                return
            data, err, ms = update.http_json(url, timeout=8.0)
            self._json({"ok": err is None, "url": url[:120], "elapsed_ms": ms,
                        "error": err or "可用", "json_ok": data is not None})
            return
        if p == "/api/autostart/save":
            """设置开机自启：写完立刻回读系统真实状态，不一致就报失败，
            绝不直接返回 ok（否则界面开关与系统状态脱节，属于假成功）。"""
            b = self._body()
            wanted = bool(b.get("enabled"))
            info = _autostart_info()
            if not info.get("supported"):
                self._json({"ok": False, "error": info.get("reason") or "当前环境不支持开机自启"}, 400)
                return
            try:
                _import_desktop_module().set_autostart(wanted)
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"设置失败：{exc}"}, 500)
                return
            after = _autostart_info()
            real = bool(after.get("enabled"))
            if real != wanted:
                self._json({"ok": False, "error": "系统未接受该设置（可能被安全策略拦截）",
                            "enabled": real}, 500)
                return
            self._json({"ok": True, "enabled": real,
                        "note": "已写入系统自启项，下次登录后生效。"})
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
    ok, reason = _paths.ensure_data_root()
    if not ok:
        print(f"[server] {reason}", file=sys.stderr)
        return 5
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
    # 默认开启，环境变量 PMEM_NO_AUTO_HARVEST=1 可禁用。
    # 同进程调用（与 desktop.py 一致）：不能 subprocess [sys.executable, ...] ——
    # 冻结态下 sys.executable 是 Evermem 自己，会把参数当 GUI 启动参数再开一个窗口。
    if not os.environ.get("PMEM_NO_AUTO_HARVEST"):
        harvest_secs = int(os.environ.get("PMEM_AUTO_HARVEST_SECONDS", "3600"))

        def _harvest_loop():
            while True:
                try:
                    from argparse import Namespace as _NS
                    import harvest as _harvest
                    _harvest.cmd_scan(_NS(days=1, min_failures=2, limit=20,
                                          dry_run=False, include_pure_failure=False,
                                          no_task_level=False))
                    # 扫描后自动评审：多角色转正（仅 lesson）+ 否决项归档，防止候选池随收割爆满
                    import mem as _mem
                    _mem.cmd_candidates(_NS(action="auto", cap=None, ids=None,
                                            purge=False, no_purge=False, reindex=False))
                except Exception as exc:  # noqa: BLE001
                    print(f"[auto-harvest] 失败：{exc}", file=sys.stderr)
                time.sleep(harvest_secs)

        _threading.Thread(target=_harvest_loop, daemon=True, name="pmem-auto-harvest").start()

    # 引擎变更检测：mem.py 等改动后提示重启（进程是启动时代码快照）。
    # server.py 在 web/ 子目录，原用 CODE_ROOT/name 构造路径导致它永远匹配不到，已改为按实际位置。
    _engine_files = {"mem.py": CODE_ROOT / "mem.py", "backup.py": CODE_ROOT / "backup.py",
                     "harvest.py": CODE_ROOT / "harvest.py", "server.py": WEB / "server.py"}
    _engine_mtimes = {name: p.stat().st_mtime
                      for name, p in _engine_files.items() if p.exists()}

    def _engine_watch():
        while True:
            try:
                for name, m in _engine_mtimes.items():
                    p = _engine_files[name]
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
