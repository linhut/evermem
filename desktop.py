#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# 恒忆 Evermem · Web 版桌面壳
#
# 把零依赖 Web 界面（web/server.py + index.html / index.js）直接作为桌面程序：
#   · 单进程：内嵌本地 HTTP 服务线程 + QtWebEngine 窗口加载首页
#   · 数据目录取 PMEM_HOME（与网页/CLI 同一套笔记与索引），采用空闲端口
#   · 单实例锁、系统托盘、明暗主题 / 中英语言菜单、F12 开发者工具
#   · 关闭窗口默认「最小化到托盘继续运行」，并弹窗询问是否停止服务
#   · Qt / WebEngine 不可用（精简 Linux / 无 GUI 环境）时自动回退：起服务 + 系统默认浏览器
#
# 运行：python desktop.py                  （开发态）
#       冒烟：QT_QPA_PLATFORM=offscreen python desktop.py --smoke
# 说明：Qt 相关全部惰性导入；本模块在纯 Python 环境也可被 import（EmbeddedServer 等不依赖 Qt）

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "web")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import paths as _paths  # noqa: E402 - 数据目录唯一入口（ensure_data_root 启动自检）

SMOKE = "--smoke" in sys.argv
AUTOSTART = "--autostart" in sys.argv

# 打包为 --windowed 时 stdout/stderr 为 None，print 会崩溃（Windows 尤甚）：先兜底重定向
if sys.stdout is None or sys.stderr is None:
    try:
        _devnull = open(os.devnull, "w", encoding="utf-8")
    except OSError:
        import io as _io
        _devnull = _io.StringIO()
    sys.stdout = sys.stderr = _devnull


def pick_free_port(preferred: int = 8765) -> int:
    import socket
    for port in range(preferred, preferred + 200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return 0


# ---------- 单实例锁（跨平台，零三方依赖） ----------
class SingleInstance:
    LOCK = Path(tempfile.gettempdir()) / "pmem-desktop.lock"

    @staticmethod
    def _alive(pid: int) -> bool:
        if pid <= 0:
            return False
        if sys.platform == "win32":
            try:
                import subprocess
                # tasklist 输出含本地化字符（俄/日/中系统）可能非 utf-8，加 errors 防解码崩线程
                out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                                     capture_output=True, text=True,
                                     encoding="utf-8", errors="ignore").stdout
                return f"PID {pid}" in out
            except Exception:
                return False
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def acquire(self) -> bool:
        try:
            if self.LOCK.exists():
                try:
                    old = int(self.LOCK.read_text(encoding="utf-8").strip() or "0")
                except (ValueError, OSError):
                    old = 0
                if old > 0 and self._alive(old):
                    return False
            self.LOCK.write_text(str(os.getpid()), encoding="utf-8")
            return True
        except OSError:
            return True  # 拿不到锁也放行，避免环境异常导致无法启动

    def release(self) -> None:
        try:
            if self.LOCK.exists():
                self.LOCK.unlink()
        except OSError:
            pass


# ---------- 开机自启注册（跨平台入口；常用于后台常驻服务随系统启动） ----------
def _launcher_cmd() -> list[str]:
    """值得写入自启项的启动命令：本程序 + --autostart。"""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--autostart"]
    return [sys.executable, str(Path(__file__).resolve()), "--autostart"]


def _win_autostart(enabled: bool) -> None:
    # 相对子键路径（与读取一致）；winreg 不支持 "HKCU\" 缩写前缀，
    # 曾因此 FileNotFoundError[WinError 2] 导致 --register-autostart 失败
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    from winreg import (HKEY_CURRENT_USER, KEY_SET_VALUE, REG_SZ,
                        OpenKey, SetValueEx, DeleteValue)
    with OpenKey(HKEY_CURRENT_USER, key, 0, KEY_SET_VALUE) as k:
        if enabled:
            SetValueEx(k, "Evermem", 0, REG_SZ, " ".join(_launcher_cmd()))
        else:
            try:
                DeleteValue(k, "Evermem")
            except OSError:
                pass


def _win_autostart_enabled() -> bool:
    from winreg import (HKEY_CURRENT_USER, KEY_READ, OpenKey, QueryValueEx)
    try:
        with OpenKey(HKEY_CURRENT_USER,
                     r"Software\Microsoft\Windows\CurrentVersion\Run", 0, KEY_READ) as k:
            QueryValueEx(k, "Evermem")
            return True
    except OSError:
        return False


def _plist_argv() -> str:
    import shlex
    return "".join(f"<string>{shlex.quote(a)}</string>" for a in _launcher_cmd())


def _mac_autostart(enabled: bool) -> None:
    # macOS 不支持 ~/.config/autostart/*.desktop（那是 Linux XDG 规范），
    # 必须写 launchd 用户代理：~/Library/LaunchAgents/<label>.plist。
    adir = Path.home() / "Library" / "LaunchAgents"
    plist = adir / "cn.linhut.evermem.plist"
    if not enabled:
        try:
            plist.unlink()
        except OSError:
            pass
        return
    adir.mkdir(parents=True, exist_ok=True)
    plist.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        '  <key>Label</key><string>cn.linhut.evermem</string>\n'
        '  <key>ProgramArguments</key><array>' + _plist_argv() + '</array>\n'
        '  <key>RunAtLoad</key><true/>\n'
        '  <key>ProcessType</key><string>Interactive</string>\n'
        '</dict></plist>\n', encoding="utf-8")


def _mac_autostart_enabled() -> bool:
    return (Path.home() / "Library" / "LaunchAgents" / "cn.linhut.evermem.plist").exists()


def _linux_autostart(enabled: bool) -> None:
    # Linux：XDG 自启规范（~/.config/autostart/*.desktop）
    adir = Path.home() / ".config" / "autostart"
    app = adir / "evermem.desktop"
    if not enabled:
        try:
            app.unlink()
        except OSError:
            pass
        return
    adir.mkdir(parents=True, exist_ok=True)
    import shlex
    exec_cmd = " ".join(shlex.quote(a) for a in _launcher_cmd())
    app.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=Evermem\n"
        "Comment=恒忆 Evermem 个人记忆库\n"
        f"Exec={exec_cmd}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n", encoding="utf-8")


def _linux_autostart_enabled() -> bool:
    return (Path.home() / ".config" / "autostart" / "evermem.desktop").exists()


def set_autostart(enabled: bool) -> None:
    """开机自启开关：按平台写入系统自启项，失败抛异常（调用方须如实反馈）。"""
    if sys.platform == "win32":
        _win_autostart(enabled)
        return
    if sys.platform == "darwin":
        _mac_autostart(enabled)
        return
    if sys.platform.startswith("linux"):
        _linux_autostart(enabled)
        return
    raise RuntimeError(f"当前平台不支持开机自启：{sys.platform}")


def autostart_enabled() -> bool:
    """读取系统真实自启状态（不是界面缓存；开关初始值与保存后校验都靠它）。"""
    if sys.platform == "win32":
        return _win_autostart_enabled()
    if sys.platform == "darwin":
        return _mac_autostart_enabled()
    if sys.platform.startswith("linux"):
        return _linux_autostart_enabled()
    return False


# ---------- 内嵌 Web 服务（持有句柄便于干净退出；规避冻结态用 sys.executable 起子进程的陷阱） ----------
class EmbeddedServer:
    def __init__(self, port: int):
        from http.server import ThreadingHTTPServer
        import server as srv
        srv.Handler.protocol_version = "HTTP/1.1"
        self.server = ThreadingHTTPServer(("127.0.0.1", port), srv.Handler)
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True, name="pmem-http")

    def start(self) -> None:
        # 冒烟模式只起 HTTP 线程：不启动自动备份/收割，避免后台线程把 index.json 等
        # 数据写进 exe 同级目录（CI 冒烟曾因此在 dist/ 留下数据，触发清单"资产不止一个"）。
        if SMOKE:
            self._thread.start()
            return
        # 自动备份循环（与 server.main 一致；收割走 CLI/Web 手动，避免打包后子进程陷阱）
        import backup
        secs = getattr(backup, "AUTO_CHECK_SECONDS", 3600)

        def _auto_loop():
            while True:
                try:
                    backup.auto_sync_if_due()
                except Exception as exc:  # noqa: BLE001
                    print(f"[auto-backup] 失败：{exc}", file=sys.stderr)
                time.sleep(secs)

        threading.Thread(target=_auto_loop, daemon=True, name="pmem-auto-backup").start()

        # 自动收割：桌面常驻必须与 server.py 对齐（README 声明了 PMEM_AUTO_HARVEST_SECONDS）。
        # 注意不能用 subprocess 拉 [sys.executable, harvest.py] —— 冻结态下 sys.executable
        # 是 Evermem 自己，会把参数当 GUI 启动参数；必须同进程调用 cmd_scan。
        if not os.environ.get("PMEM_NO_AUTO_HARVEST"):
            import time as _t
            harvest_secs = int(os.environ.get("PMEM_AUTO_HARVEST_SECONDS", "3600"))

            def _auto_harvest():
                while True:
                    try:
                        import harvest
                        from argparse import Namespace
                        harvest.cmd_scan(Namespace(days=1, min_failures=2, limit=20,
                                                   dry_run=False, include_pure_failure=False,
                                                   no_task_level=False))
                        import mem as _mem
                        _mem.cmd_candidates(Namespace(action="auto", cap=None, ids=None,
                                                      purge=False, no_purge=False, reindex=False))
                    except Exception as exc:  # noqa: BLE001
                        print(f"[auto-harvest] 失败：{exc}", file=sys.stderr)
                    _t.sleep(harvest_secs)

            threading.Thread(target=_auto_harvest, daemon=True, name="pmem-auto-harvest").start()

        self._thread.start()

    def stop(self) -> None:
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass


def _wait_health(port: int, timeout: float = 6.0) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as r:
                return r.status == 200
        except Exception:
            time.sleep(0.1)
    return False


# ---------- Qt 桌面壳（惰性导入；无 Qt 时走浏览器回退） ----------
def run_gui(url: str, server: EmbeddedServer) -> int:
    # 白屏修复：GPU 受限环境（远程桌面/虚拟机/沙箱会话）QtWebEngine 默认无法创建
    # GL 上下文，页面加载必失败。统一走软件渲染（--disable-gpu + 禁沙箱），换取稳定；
    # 用户可用 QTWEBENGINE_CHROMIUM_FLAGS 覆盖自定义（须在 QApplication 创建前生效）。
    if not os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS"):
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-gpu --disable-dev-shm-usage"

    from PySide6.QtCore import Qt, QUrl, QTimer
    from PySide6.QtGui import QKeySequence, QShortcut
    from PySide6.QtWidgets import (QApplication, QMainWindow, QMenu, QMessageBox, QStyle, QSystemTrayIcon)
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    app.setApplicationName("Evermem")
    app.setApplicationDisplayName("恒忆 Evermem")
    if app.style() is not None:
        app.setWindowIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))

    on_quit = lambda: app.quit()  # noqa: E731

    class Win(QMainWindow):
        def __init__(self):
            super().__init__()
            self.allow_quit = False
            self.smoke_loaded = False  # 冒烟真实校验：页面 loadFinished 是否成功（防"空心冒烟"）
            self._dev = None  # 开发者工具窗口
            self.web = QWebEngineView(self)
            self.web.setUrl(QUrl(url))
            self.web.loadFinished.connect(self._on_loaded)
            s = self.web.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
            self.setCentralWidget(self.web)
            self.resize(1280, 800)
            self.setWindowTitle("恒忆 Evermem")
            # 菜单/托盘在构造时即创建，不依赖页面加载回调：
            # 原实现放在 _on_loaded 里，页面加载异常时 --autostart 访问 w._tray 会 AttributeError 崩溃。
            self._build_chrome()

        def _on_loaded(self, ok: bool):
            self.smoke_loaded = ok

        def _build_chrome(self):
            mb = self.menuBar()
            m = mb.addMenu("视图")
            m.addAction("浅色主题", lambda: self._js("pmem-theme", "light"))
            m.addAction("深色主题", lambda: self._js("pmem-theme", "dark"))
            m.addSeparator()
            m.addAction("中文", lambda: self._js("pmem-lang", "zh"))
            m.addAction("English", lambda: self._js("pmem-lang", "en"))
            m.addSeparator()
            m.addAction("开发者工具", self._toggle_dev)
            a_auto = m.addAction("开机自启")
            a_auto.setCheckable(True)
            a_auto.setChecked(autostart_enabled())

            def _on_autostart(on: bool):
                # 写入可能失败（权限/策略）；失败必须把勾选态拉回系统真实状态，
                # 否则菜单显示「已开启」而系统里没注册，就是假成功。
                try:
                    set_autostart(on)
                except Exception as exc:  # noqa: BLE001
                    QMessageBox.warning(self, "开机自启", f"设置失败：{exc}")
                real = autostart_enabled()
                a_auto.blockSignals(True)
                a_auto.setChecked(real)
                a_auto.blockSignals(False)

            a_auto.toggled.connect(_on_autostart)
            QShortcut(QKeySequence(Qt.Key_F12), self, activated=self._toggle_dev)
            QShortcut(QKeySequence(Qt.Key_F5), self, activated=self.web.reload)

            self._dev_open = False
            tm = QMenu(self)
            tm.addAction("打开恒忆 Evermem", self.show_and_raise)
            tm.addSeparator()
            tm.addAction("停止服务并退出", self._quit_now)
            self._tray = QSystemTrayIcon(self)
            self._tray.setIcon(self.windowIcon())
            self._tray.setToolTip("恒忆 Evermem — 服务运行中")
            self._tray.setContextMenu(tm)
            self._tray.activated.connect(lambda r: self.show_and_raise()
                                         if r in (QSystemTrayIcon.ActivationReason.DoubleClick,
                                                  QSystemTrayIcon.ActivationReason.Trigger) else None)

        def _js(self, key, val):
            # 复用前端已有主题/语言键，改后刷新即时生效
            self.web.page().runJavaScript(f"localStorage.setItem('{key}','{val}'); location.reload();")

        def _toggle_dev(self):
            # 真实开发者工具：原实现只 setEnabled(True)+setDevicesPixelRatio，是空操作桩
            self._dev_open = not self._dev_open
            if self._dev_open:
                page = self.web.page()
                dv = QWebEngineView(self)
                page.setDevToolsPage(dv.page())
                dv.setWindowTitle("恒忆 Evermem · 开发者工具")
                dv.resize(900, 620)
                dv.show()
                self._dev = dv
            else:
                if self._dev is not None:
                    self.web.page().setDevToolsPage(None)
                    self._dev.close()
                    self._dev = None

        def show_and_raise(self):
            self.showNormal(); self.raise_(); self.activateWindow()
            self._tray.show()

        def _quit_now(self):
            self.allow_quit = True
            self.close()

        def closeEvent(self, e):
            if self.allow_quit:
                e.accept()
                return
            box = QMessageBox(self)
            box.setWindowTitle("恒忆 Evermem")
            box.setText("关闭窗口后将最小化到托盘，本地服务与后台钩子继续运行。")
            b_min = box.addButton("最小化（继续运行）", QMessageBox.ButtonRole.AcceptRole)
            b_quit = box.addButton("停止服务并退出", QMessageBox.ButtonRole.DestructiveRole)
            b_cancel = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(b_min)
            box.exec()
            c = box.clickedButton()
            if c is b_min:
                e.ignore(); self.hide(); self._tray.show()
                self._tray.showMessage("恒忆 Evermem", "已最小化到托盘，服务仍在运行")
            elif c is b_quit:
                self._quit_now()
            else:
                e.ignore()

    w = Win()
    if AUTOSTART:
        # 开机自启：直接进托盘常驻，不弹主窗
        w.hide()
        w._tray.show()
    else:
        w.show()
    app.aboutToQuit.connect(server.stop)
    if SMOKE:
        # 冒烟：6s 后按「页面是否成功加载」判定退出码（0=渲染通过），os._exit 最可靠
        def _smoke_exit():
            rc = 0 if getattr(w, "smoke_loaded", False) else 1
            if rc:
                print("[smoke] 页面加载失败（loadFinished=False，疑似白屏）", file=sys.stderr)
            os._exit(rc)
        QTimer.singleShot(6000, _smoke_exit)
    return app.exec()


def main() -> int:
    if "--register-autostart" in sys.argv:
        set_autostart(True)
        print("[autostart] 已注册开机自启")
        return 0
    if "--unregister-autostart" in sys.argv:
        set_autostart(False)
        print("[autostart] 已取消开机自启")
        return 0

    ok, reason = _paths.ensure_data_root()
    if not ok:
        # 数据根不可写属于阻断级：继续启动会造成「界面正常但什么都存不了」的假成功
        print(f"[main] {reason}", file=sys.stderr)
        try:
            import PySide6
            from PySide6.QtWidgets import QApplication, QMessageBox
            _qapp = QApplication(sys.argv)
            QMessageBox.critical(None, "恒忆 Evermem", reason)
        except Exception:
            pass
        return 5

    inst = SingleInstance()
    if not inst.acquire():
        print("[main] 恒忆已在运行（单实例），请切换至已打开的窗口。", file=sys.stderr)
        return 2

    # 桌面壳标识：内嵌 Web 服务据此暴露「桌面常驻」类能力（开机自启等）。
    # 不加标识的话，纯浏览器/独立 server 模式也会显示系统自启开关，点了不会有反应。
    os.environ["PMEM_DESKTOP"] = "1"

    port = pick_free_port()
    if not port:
        print("[main] 无法分配空闲端口", file=sys.stderr)
        inst.release()
        return 3

    server = EmbeddedServer(port)
    server.start()
    url = f"http://127.0.0.1:{port}/"
    if not _wait_health(port):
        print(f"[main] 本地服务未就绪：{url}", file=sys.stderr)
        server.stop(); inst.release()
        return 4
    print(f"[main] 本地服务就绪：{url}")

    try:
        import PySide6  # noqa: F401
        from PySide6 import QtWebEngineWidgets  # noqa: F401
        have_gui = True
    except Exception:
        have_gui = False

    rc = 0
    try:
        if have_gui:
            rc = run_gui(url, server)
        else:
            print("[main] 当前环境无 Qt/WebEngine，改用系统默认浏览器打开。")
            webbrowser.open(url)
            if SMOKE:
                # 回退路径（无 QtWebEngine）同样需要冒烟自退：否则 CI/无头环境挂起
                threading.Timer(6.0, lambda: os._exit(0)).start()
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        inst.release()
    return rc


if __name__ == "__main__":
    sys.exit(main())