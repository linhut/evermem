#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# 恒忆 Evermem · 桌面封装版（网页 UI + 系统原生窗口）
#
#
# 原理：同进程启动本地 HTTP 服务，pywebview 原生窗口加载之。
# 系统 WebView：Win=Edge/WebView2、macOS=WKWebView、Linux=WebKitGTK，跨系统。
#
# 热预览（开发模式）：PMEM_DEV=1 时监听 index.html/index.js/server.py，
#   前端文件改动 → 窗口自动刷新；server.py 改动 → 服务自动重启。
# 生产模式：PMEM_DEV 未设，无 watch 开销。
#
# 运行：C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe launcher.py
#       PMEM_DEV=1 ... launcher.py   ← 开发热预览

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

WEB = Path(__file__).resolve().parent
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

PORT = int(os.environ.get("PMEM_WEB_PORT", "8765"))
DEV = os.environ.get("PMEM_DEV", "") == "1"

_server = None
_server_lock = threading.Lock()

def _start_server() -> None:
    global _server
    import server as srv
    from http.server import ThreadingHTTPServer

    srv.Handler.protocol_version = "HTTP/1.1"
    with _server_lock:
        try:
            _server = ThreadingHTTPServer(("127.0.0.1", PORT), srv.Handler)
        except OSError:
            time.sleep(0.8)
            _server = ThreadingHTTPServer(("127.0.0.1", PORT), srv.Handler)
        _server.serve_forever()

def _restart_server() -> None:
    global _server
    import importlib
    import server as srv_mod
    importlib.reload(srv_mod)  # 关键：重载模块，否则代码改动不生效
    srv = _server
    if srv:
        threading.Thread(target=srv.shutdown, daemon=True).start()
        _server = None
    threading.Thread(target=_start_server, daemon=True).start()

def _watch(webview_mod) -> None:
    """热预览：监听前端与 server 文件，变化自动刷新/重启。"""
    files = {
        WEB / "index.html": 0.0,
        WEB / "index.js": 0.0,
        WEB / "server.py": 0.0,
    }
    for p in files:
        try:
            files[p] = p.stat().st_mtime
        except OSError:
            pass
    while True:
        time.sleep(0.8)
        changed = {"ui": False, "srv": False}
        for p, m in list(files.items()):
            try:
                now = p.stat().st_mtime
            except OSError:
                continue
            if now != m:
                files[p] = now
                if p.name == "server.py":
                    changed["srv"] = True
                else:
                    changed["ui"] = True
        if changed["srv"]:
            print("[pmem-dev] server.py 变更 → 重启服务", file=sys.stderr)
            _restart_server()
        if changed["ui"]:
            print("[pmem-dev] 前端变更 → 刷新窗口", file=sys.stderr)
            try:
                for w in webview_mod.windows:
                    w.load_url(f"http://127.0.0.1:{PORT}")
            except Exception as exc:  # noqa: BLE001
                print(f"[pmem-dev] 刷新失败：{exc}", file=sys.stderr)

def main() -> int:
    threading.Thread(target=_start_server, daemon=True).start()
    try:
        import webview
    except ImportError:
        print("[恒忆] 未装 pywebview：pip install pywebview")
        return 1

    print(f"[恒忆] 服务 http://127.0.0.1:{PORT}，窗口即将弹出" + ("（开发热预览 ON）" if DEV else ""))
    win = webview.create_window(
        "恒忆 Evermem · 记忆管理",
        f"http://127.0.0.1:{PORT}",
        width=1180,
        height=780,
        min_size=(860, 560),
        confirm_close=False,
    )
    if DEV:
        threading.Thread(target=_watch, args=(webview,), daemon=True).start()
    webview.start()
    srv = _server
    if srv:
        srv.shutdown()
    return 0

if __name__ == "__main__":
    sys.exit(main())
