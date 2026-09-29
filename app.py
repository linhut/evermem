#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# pmem 桌面端 v0.3 —— 四视图导航（借鉴 dsh-memoir）
#

from __future__ import annotations

import html as _h
import json
import os
import subprocess
import sys
import time
from pathlib import Path

QT_MODE = False  # main() 里按 PMEM_THEME 设置

# 导入功能配置（env > 通用默认；勿写死用户盘符——发布约定，见 docs/PLATFORM.md）
# PMEM_CHUNKS / PMEM_SPACES 缺省落在项目内相对路径，本机实际位置可用环境变量或 pmem_config.json 指定
SYS_PY = os.environ.get("PMEM_SYS_PY") or sys.executable
CHUNKS_ROOT = Path(os.environ.get("PMEM_CHUNKS") or (BASE / "chunks"))
SPACES_ROOT = Path(os.environ.get("PMEM_SPACES") or BASE)
EXCLUDE_DIRS = {
    "$RECYCLE.BIN", "System Volume Information", "CPM_ENCRYPTED_FOLDER",
    "Game", "WeGameApps", "Wondershare", "Wondershare UniConverter 15",
    "Android", "iso", "hulu", "opgg", "canon", "Anki", "U盘file",
    "PSAutoRecover", "BaiduNetdiskDownload", "Package", "tmp", "tools",
    "master", "1111", "f", "data", "cod", "备份", "WeChat Files",
}
DOC_EXTS = {".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".pdf",
            ".md", ".txt", ".csv", ".html", ".py", ".json", ".yaml", ".yml"}

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import mem  # noqa: E402

try:
    from PySide6.QtCore import Qt, QTimer, QSettings
    from PySide6.QtGui import QFont, QKeySequence, QShortcut
    from PySide6.QtWidgets import (  # noqa: E402
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QListWidget, QListWidgetItem, QLineEdit, QTextBrowser, QComboBox,
        QPushButton, QStatusBar, QFrame, QStackedWidget, QTabBar, QLabel,
        QDialog, QPlainTextEdit, QFormLayout, QDialogButtonBox, QMessageBox,
    )
except ImportError:
    sys.stderr.write("未装 PySide6：pip install PySide6-Essentials\n")
    sys.exit(1)

TYPE_LABEL = {"fact": "事实", "lesson": "经验", "procedure": "配方"}

# ============ Apple 风格配色（HIG：灰白中性 + 系统蓝唯一强调）============
WB = {
    "primary": "#007AFF", "primary_hover": "#0066D6", "primary_deep": "#0040C0",
    "link": "#007AFF", "bg": "#F5F5F7", "card": "#FFFFFF", "hover": "#F0F0F2",
    "border": "#E5E5EA", "divider": "#E0E0E0", "text": "#1D1D1F", "text2": "#86868B",
    "ok_bg": "#E8F8EE", "ok_fg": "#1F7A3F",
    "warn_bg": "#FFF6E9", "warn_fg": "#A05E03",
    "err_bg": "#FFECEB", "err_fg": "#9D1C12",
    "info_bg": "#E6F1FF", "info_fg": "#0056B3",
    "gold_bg": "#FFF6D9", "gold_fg": "#8A6100",
    "gray_bg": "#F2F2F7", "gray_fg": "#6E6E73",
}

# WorkBuddy 风格徽章：浅底 + 深字（语义色板）
TYPE_BADGE = {
    "procedure": (WB["ok_bg"], WB["ok_fg"]),    # 青绿浅底
    "lesson": (WB["warn_bg"], WB["warn_fg"]),   # 琥珀浅底
    "fact": (WB["info_bg"], WB["info_fg"]),     # 蓝浅底
}
STATUS_BADGE = {
    "active": (WB["ok_bg"], WB["ok_fg"]),
    "staged": (WB["warn_bg"], WB["warn_fg"]),
    "suspect": (WB["gray_bg"], WB["gray_fg"]),
    "superseded": (WB["gray_bg"], "#9ca3af"),
}

# 完整主题（默认模式，window 级应用）—— Apple 风格：大留白、细分割线、圆角克制
QSS_FULL = f"""
QMainWindow {{ background: {WB['bg']}; }}
#nav {{ background: {WB['card']}; border-bottom: 1px solid {WB['border']}; }}
QTabBar::tab {{
    background: transparent; padding: 9px 26px; color: {WB['text2']};
    border: none; border-bottom: 2px solid transparent; font-size: 13px; min-width: 76px;
}}
QTabBar::tab:selected {{ color: {WB['primary']}; border-bottom: 2px solid {WB['primary']}; font-weight: 500; }}
QTabBar::tab:hover {{ color: {WB['primary']}; }}
#toolbar {{ background: {WB['card']}; border-bottom: 1px solid {WB['border']}; }}
QLineEdit#search {{
    background: {WB['bg']}; border: 1px solid transparent; border-radius: 10px;
    padding: 5px 14px; color: {WB['text']}; font-size: 13px;
}}
QLineEdit#search:focus {{ border: 1px solid {WB['primary']}; background: {WB['card']}; }}
QComboBox {{
    background: {WB['bg']}; border: 1px solid transparent; border-radius: 8px;
    padding: 5px 12px; color: {WB['text']}; font-size: 12px; min-width: 92px;
}}
QComboBox:hover {{ background: {WB['hover']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QPushButton#newbtn {{
    background: {WB['primary']}; color: #fff; border: none; border-radius: 8px;
    padding: 6px 20px; font-size: 13px; font-weight: 500;
}}
QPushButton#newbtn:hover {{ background: {WB['primary_hover']}; }}
QPushButton[accent="okay"] {{ background: {WB['primary']}; color: #fff; border: none; border-radius: 8px; padding: 6px 14px; }}
QPushButton[accent="okay"]:hover {{ background: {WB['primary_hover']}; }}
QPushButton[accent="warn"] {{ background: transparent; color: {WB['text2']}; border: 1px solid {WB['divider']}; border-radius: 8px; padding: 6px 14px; }}
QPushButton[accent="warn"]:hover {{ border-color: {WB['primary']}; color: {WB['primary']}; }}
#pane {{ background: {WB['card']}; border: 1px solid {WB['border']}; border-radius: 12px; }}
QListWidget#list {{ background: transparent; border: none; padding: 8px; outline: none; }}
QListWidget#list::item {{
    background: transparent; border-radius: 9px;
    padding: 9px 12px; margin: 2px 4px;
}}
QListWidget#list::item:selected {{ background: {WB['primary']}; color: #fff; }}
QListWidget#list::item:hover {{ background: {WB['hover']}; }}
QListWidget#list::item:selected:hover {{ background: {WB['primary']}; }}
QTextBrowser#detail {{ background: transparent; border: none; padding: 12px; font-size: 13px; }}
QStatusBar {{ background: transparent; color: {WB['text2']}; font-size: 11px; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #D1D1D6; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {WB['primary']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolTip {{ background: {WB['card']}; color: {WB['text']}; border: 1px solid {WB['border']}; padding: 6px 10px; border-radius: 6px; }}
"""

# qt-material 模式下的增量样式（全局基础由 qt-material 打底）
QSS_INCR = """
#search {{
    background: #f2f3f5; border: 1px solid #e6e8ec; border-radius: 14px;
    padding: 4px 12px; color: #1f2328; font-size: 13px;
}}
#search:focus {{ border: 1px solid #0dbfa3; background: #ffffff; }}
#newbtn {{
    background: #0dbfa3; color: #fff; border: none; border-radius: 15px;
    padding: 5px 18px; font-size: 13px; font-weight: 600;
}}
#newbtn:hover {{ background: #0aa88f; }}
QPushButton[accent="okay"] {{ background: #0dbfa3; color: #fff; border: none; border-radius: 8px; padding: 6px 14px; }}
QPushButton[accent="warn"] {{ background: transparent; color: #6b7280; border: 1px solid #d0d3d9; border-radius: 8px; padding: 6px 14px; }}
QPushButton[accent="warn"]:hover {{ border-color: #0dbfa3; color: #087866; }}
#pane {{ background: #ffffff; border: 1px solid #ececf0; border-radius: 10px; }}
QListWidget#list {{ background: transparent; border: none; padding: 6px; outline: none; }}
QListWidget#list::item {{
    background: #ffffff; border: 1px solid #eef0f3; border-radius: 8px;
    padding: 8px 10px; margin: 3px 2px;
}}
QListWidget#list::item:selected {{ background: #e6f7f4; border: 1px solid #0dbfa3; }}
QListWidget#list::item:hover {{ background: #f5f7fa; }}
QTextBrowser#detail {{ background: transparent; border: none; padding: 10px; font-size: 13px; }}
QStatusBar {{ background: transparent; color: #8a8f98; font-size: 11px; }}
"""

def esc(s):
    return _h.escape(str(s) if s else "")

def markdown(body: str) -> str:
    out: list[str] = []
    in_code = False
    for raw in (body or "").split("\n"):
        line = raw.rstrip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            out.append(f"<pre style='background:#f6f7f9;border-radius:6px;padding:8px;font-size:12px'>{esc(line)}</pre>")
        elif line.startswith("### "):
            out.append(f"<h4 style='margin:14px 0 6px;color:#1f2328'>{esc(line[4:])}</h4>")
        elif line.startswith("## "):
            out.append(f"<h4 style='margin:14px 0 6px;color:#1f2328'>{esc(line[3:])}</h4>")
        elif line.startswith("# "):
            out.append(f"<h3 style='margin:14px 0 6px;color:#1f2328'>{esc(line[2:])}</h3>")
        elif line.startswith("- ") or line.startswith("* "):
            out.append(f"<p style='margin:2px 0;color:#2a2e34'>• {esc(line[2:])}</p>")
        elif line.strip():
            out.append(f"<p style='margin:5px 0;color:#2a2e34;line-height:1.7'>{esc(line)}</p>")
    return "\n".join(out)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pmem 记忆管理")
        self._settings = QSettings("pmem", "pmem")
        geo = self._settings.value("window_geometry")
        if geo:
            self.restoreGeometry(geo)
        else:
            self.resize(1180, 760)
        self.setStyleSheet(QSS_INCR if QT_MODE else QSS_FULL)

        self.idx = mem.load_index()
        self.docs = self.idx.get("docs", {})

        # —— 二级导航 ——
        self.tabs = QTabBar()
        for t in ("记忆浏览", "候选审核", "数据导入", "热层预览", "统计诊断", "会话集成"):
            self.tabs.addTab(t)
        nav_widget = QWidget()
        nav_widget.setObjectName("nav")
        nav = QHBoxLayout(nav_widget)
        nav.setContentsMargins(12, 0, 12, 0)
        nav.addWidget(self.tabs)
        nav.addStretch(1)
        nav_lab = QLabel("pmem")
        nav_lab.setStyleSheet("color:#185FA5;font-weight:700;font-size:14px;padding-right:12px")
        nav.addWidget(nav_lab)

        self.stack = QStackedWidget()
        self.page_browse = self.build_browse()
        self.page_triage = self.build_triage()
        self.page_import = self.build_import()
        self.page_hot = self.build_hot()
        self.page_stats = self.build_stats()
        self.page_integration = self.build_integration()
        self.stack.addWidget(self.page_browse)
        self.stack.addWidget(self.page_triage)
        self.stack.addWidget(self.page_import)
        self.stack.addWidget(self.page_hot)
        self.stack.addWidget(self.page_stats)
        self.stack.addWidget(self.page_integration)
        self.tabs.currentChanged.connect(self.switch_page)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(nav_widget)
        body.addWidget(self.stack, 1)
        main_widget = QWidget()
        main_widget.setLayout(body)
        self.setCentralWidget(main_widget)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.search_box.setFocus)
        self.refresh_all()

    def closeEvent(self, event):  # noqa: N802
        self._settings.setValue("window_geometry", self.saveGeometry())
        if getattr(self, "imp_space", None) and self.imp_space.currentData():
            self._settings.setValue("last_import_dir", self.imp_space.currentData())
        if getattr(self, "tabs", None):
            self._settings.setValue("last_tab", self.tabs.currentIndex())
        super().closeEvent(event)

    def switch_page(self, i: int):
        self.stack.setCurrentIndex(i)
        if i == 1:
            self.reload_triage()
        elif i == 2:
            self.reload_import()
        elif i == 3:
            self.reload_hot()
        elif i == 4:
            self.reload_stats()
        elif i == 5:
            self.reload_integration()
        else:
            self.refresh_list()

    # ============ 记忆浏览 ============
    def build_browse(self) -> QWidget:
        self.search_box = QLineEdit()
        self.search_box.setObjectName("search")
        self.search_box.setPlaceholderText("搜索记忆…（融合通信 / 方案 / 公文）")
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self.refresh_list)
        self.search_box.textChanged.connect(lambda _: self._debounce.start())

        self.type_filter = QComboBox()
        self.type_filter.addItems(["全部类型", "配方", "经验", "事实"])
        self.type_filter.currentIndexChanged.connect(self.refresh_list)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["全部状态", "active", "staged", "suspect", "superseded"])
        self.status_filter.currentIndexChanged.connect(self.refresh_list)
        self.new_btn = QPushButton("+ 新建笔记")
        self.new_btn.setObjectName("newbtn")
        self.new_btn.clicked.connect(self.on_new)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(16, 8, 16, 8)
        toolbar.addWidget(self.search_box, 3)
        toolbar.addSpacing(10)
        toolbar.addWidget(self.type_filter)
        toolbar.addSpacing(6)
        toolbar.addWidget(self.status_filter)
        toolbar.addStretch(1)
        toolbar.addWidget(self.new_btn)
        tw = QWidget()
        tw.setObjectName("toolbar")
        tw.setLayout(toolbar)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("list")
        self.list_widget.setFont(QFont("Microsoft YaHei UI", 10))
        self.list_widget.currentItemChanged.connect(self.show_note)
        self.list_widget.itemDoubleClicked.connect(lambda it: self.on_edit(self.docs.get(it.data(Qt.ItemDataRole.UserRole))))
        lp = QFrame()
        lp.setObjectName("pane")
        lp_layout = QVBoxLayout(lp)
        lp_layout.setContentsMargins(6, 6, 6, 6)
        lp_layout.addWidget(self.list_widget)

        self.detail = QTextBrowser()
        self.detail.setObjectName("detail")
        self.detail.setFont(QFont("Microsoft YaHei UI", 10))

        self.edit_btn = QPushButton("✎ 编辑")
        self.edit_btn.setProperty("accent", "warn")
        self.edit_btn.setToolTip("修改标题/类型/状态/标签/正文（写回原文件）")
        self.edit_btn.clicked.connect(lambda: self.on_edit(self.current_doc()))
        self.suspect_btn = QPushButton("标记 suspect")
        self.suspect_btn.setProperty("accent", "warn")
        self.suspect_btn.setToolTip("标记为存疑，从正常召回中移除")
        self.suspect_btn.clicked.connect(lambda: self.set_status(self.current_doc(), "suspect"))
        self.archive_btn = QPushButton("归档")
        self.archive_btn.setProperty("accent", "warn")
        self.archive_btn.setToolTip("标记 superseded（已被替代），不再参与召回")
        self.archive_btn.clicked.connect(lambda: self.set_status(self.current_doc(), "superseded"))
        opbar = QHBoxLayout()
        opbar.addWidget(self.edit_btn)
        opbar.addWidget(self.suspect_btn)
        opbar.addWidget(self.archive_btn)
        opbar.addStretch(1)

        dp = QFrame()
        dp.setObjectName("pane")
        dp_layout = QVBoxLayout(dp)
        dp_layout.setContentsMargins(14, 10, 14, 12)
        dp_layout.addLayout(opbar)
        dp_layout.addWidget(self.detail)

        central = QHBoxLayout()
        central.setContentsMargins(16, 12, 16, 12)
        central.addWidget(lp, 5)
        central.addSpacing(12)
        central.addWidget(dp, 7)
        root = QWidget()
        root.setLayout(central)

        page = QVBoxLayout()
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)
        page.addWidget(tw)
        page.addWidget(root, 1)
        w = QWidget()
        w.setLayout(page)
        return w

    def visible_ids(self) -> list[str]:
        q = self.search_box.text().strip()
        tf = self.type_filter.currentText()
        sf = self.status_filter.currentText()
        tmap = {"全部类型": None, "配方": "procedure", "经验": "lesson", "事实": "fact"}
        want_t, want_s = tmap[tf], (None if sf == "全部状态" else sf)
        if q:
            hits = mem.search(self.idx, q, limit=200, include_all=True)
            self._last_scores = {h["id"]: round(h["score"], 1) for h in hits}
            ids = [h["id"] for h in hits]
        else:
            self._last_scores = {}
            ids = [d["id"] for d in self.docs.values()]
        out = [i for i in ids
               if (not want_t or self.docs.get(i, {}).get("type") == want_t)
               and (not want_s or self.docs.get(i, {}).get("status") == want_s)]
        return out

    def refresh_list(self, *_):
        self.list_widget.clear()
        ids = self.visible_ids()
        for did in ids:
            d = self.docs.get(did)
            if not d:
                continue
            label = TYPE_LABEL.get(d.get("type"), "?")
            hot = "★" if d.get("hot") in ("true", "1") else ""
            tags = " · ".join((d.get("tags") or [])[:3])
            score = self._last_scores.get(did)
            sfx = f"　{score}分" if score is not None else ""
            item = QListWidgetItem(f"{d.get('title') or '（无标题）'}\n{label} {hot}  {tags}{sfx}")
            item.setData(Qt.ItemDataRole.UserRole, did)
            self.list_widget.addItem(item)
        self.status.showMessage(self.status_line(len(ids)))

    def status_line(self, n: int) -> str:
        active = sum(1 for d in self.docs.values() if d.get("status") == "active")
        hot = sum(1 for d in self.docs.values() if d.get("hot") in ("true", "1"))
        staged = sum(1 for d in self.docs.values() if d.get("status") == "staged")
        return f"共 {len(self.docs)} 条 · Active {active} · 热层 {hot} · 候选 {staged} · 列表 {n} 条"

    def current_doc(self) -> dict | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return self.docs.get(item.data(Qt.ItemDataRole.UserRole))

    def on_edit(self, d: dict | None):
        """编辑已有笔记：标题/类型/状态/标签/正文，写回原文件并重建索引。"""
        if not d or not d.get("path"):
            self.status.showMessage("请先选择一条笔记")
            return
        path = Path(d["path"])
        if not path.exists():
            self.status.showMessage(f"原文件不存在：{path}")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("编辑记忆")
        dlg.resize(620, 480)
        form = QFormLayout(dlg)
        title_edit = QLineEdit(d.get("title", ""))
        type_edit = QComboBox()
        type_edit.addItems(["procedure", "lesson", "fact"])
        type_edit.setCurrentText(d.get("type", "lesson"))
        status_edit = QComboBox()
        status_edit.addItems(["active", "staged", "suspect", "superseded"])
        status_edit.setCurrentText(d.get("status", "active"))
        tags_edit = QLineEdit("，".join(d.get("tags") or []))
        tags_edit.setPlaceholderText("逗号分隔")
        body_edit = QPlainTextEdit(d.get("body", ""))
        body_edit.setPlaceholderText("正文（Markdown）")
        form.addRow("标题", title_edit)
        form.addRow("类型", type_edit)
        form.addRow("状态", status_edit)
        form.addRow("标签", tags_edit)
        form.addRow("正文", body_edit)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("保存")
        box.button(QDialogButtonBox.Cancel).setText("取消")
        form.addRow(box)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        if not dlg.exec():
            return
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            self.status.showMessage(f"读取失败：{exc}")
            return
        # 重写 frontmatter（保留 id/created/hot/source 等未编辑字段）
        head, _, rest = raw.partition("---\n")
        body_raw = rest[rest.find("\n---\n") + 5:].lstrip("\n") if "\n---\n" in rest else rest
        meta: dict[str, str] = {}
        for line in rest.split("\n---\n", 1)[0].splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        meta["type"] = type_edit.currentText()
        meta["status"] = status_edit.currentText()
        meta["title"] = title_edit.text().strip().replace("\n", " ")
        meta["tags"] = "[" + ", ".join(f'"{t.strip()}"' for t in tags_edit.text().split("，") if t.strip()) + "]"
        new_head = "\n".join(f"{k}: {v}" for k, v in meta.items())
        text = "---\n" + new_head + "\n---\n\n" + body_edit.toPlainText().strip() + "\n"
        try:
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            self.status.showMessage(f"写入失败：{exc}")
            return
        mem.build_index()
        self.idx = mem.load_index(force=True)
        self.docs = self.idx.get("docs", {})
        self.refresh_list()
        self.status.showMessage(f"已更新：{meta['title']}")

    def set_status(self, d: dict | None, status: str):
        """改笔记状态（suspect/superseded/active…），写回文件。"""
        if not d or not d.get("path"):
            self.status.showMessage("请先选择一条笔记")
            return
        path = Path(d["path"])
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            self.status.showMessage(f"读取失败：{exc}")
            return
        import re as _re
        if _re.search(r"^status:\s*\S+", raw, _re.M):
            raw = _re.sub(r"^status:\s*\S+", f"status: {status}", raw, count=1, flags=_re.M)
        else:
            raw = raw.replace("---\n", f"---\nstatus: {status}\n", 1)
        try:
            path.write_text(raw, encoding="utf-8")
        except OSError as exc:
            self.status.showMessage(f"写入失败：{exc}")
            return
        mem.build_index()
        self.idx = mem.load_index(force=True)
        self.docs = self.idx.get("docs", {})
        self.refresh_list()
        self.status.showMessage(f"已标记 {status}：{d.get('title')}")

    def on_unhot(self, d: dict | None):
        """移出热层：去掉 frontmatter 的 hot: true。"""
        if not d or not d.get("path"):
            self.status.showMessage("请先选择一条热层笔记")
            return
        path = Path(d["path"])
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            self.status.showMessage(f"读取失败：{exc}")
            return
        import re as _re
        new = _re.sub(r"^hot:\s*(true|1|yes)\s*\n", "", raw, flags=_re.M)
        if new == raw:
            self.status.showMessage("该笔记没有热层标记")
            return
        try:
            path.write_text(new, encoding="utf-8")
        except OSError as exc:
            self.status.showMessage(f"写入失败：{exc}")
            return
        mem.build_index()
        self.idx = mem.load_index(force=True)
        self.docs = self.idx.get("docs", {})
        self.reload_hot()
        self.refresh_list()
        self.status.showMessage(f"已移出热层：{d.get('title')}")

    def show_note(self, current, _prev=None):
        if current is None:
            return
        self.detail.setHtml(self.render_note(self.docs.get(current.data(Qt.ItemDataRole.UserRole))))

    def render_note(self, d: dict) -> str:
        if not d:
            return "<p style='color:#999'>（无内容）</p>"
        tlabel = TYPE_LABEL.get(d.get("type"), d.get("type", ""))
        tb, tf = TYPE_BADGE.get(d.get("type"), (WB["gray_bg"], WB["gray_fg"]))
        status = d.get("status", "")
        hot = d.get("hot") in ("true", "1")
        tags = "、".join(d.get("tags") or [])
        sb, sf = STATUS_BADGE.get(status, (WB["gray_bg"], WB["gray_fg"]))
        badges = (f"<span style='background:{tb};color:{tf};border-radius:9px;padding:1px 9px;font-size:11px'>{esc(tlabel)}</span> "
                  f"<span style='background:{sb};color:{sf};border-radius:9px;padding:1px 9px;font-size:11px'>{esc(status)}</span>")
        if hot:
            badges += f" <span style='background:{WB['gold_bg']};color:{WB['gold_fg']};border-radius:9px;padding:1px 9px;font-size:11px'>★ 热层</span>"
        meta = (f"<div style='color:#8a8f98;font-size:11px;margin:8px 0 4px'>{esc(tags) or '无标签'}</div>"
                f"<div style='color:#b0b5bd;font-size:10px;word-break:break-all'>来源：{esc(d.get('source') or '—')}</div>")
        return (f"<h2 style='margin:2px 0 6px;font-size:19px;color:#1f2328'>{esc(d.get('title') or '')}</h2>"
                f"<div>{badges}</div>{meta}<hr style='border:none;border-top:1px solid #ececf0'>{markdown(d.get('body') or '')}")

    # ============ 候选审核 ============
    def build_triage(self) -> QWidget:
        self.tri_list = QListWidget()
        self.tri_list.setObjectName("list")
        self.tri_list.setFont(QFont("Microsoft YaHei UI", 10))
        self.tri_list.currentItemChanged.connect(self.show_triage_detail)
        btns = QHBoxLayout()
        self.approve_btn = QPushButton("通过并转正 → active")
        self.approve_btn.setProperty("accent", "okay")
        self.approve_btn.clicked.connect(self.approve_selected)
        self.discard_btn = QPushButton("保持暂缓")
        self.discard_btn.setProperty("accent", "warn")
        self.discard_btn.clicked.connect(lambda: self.status.showMessage("已保留在候选中，稍后再审"))
        btns.addWidget(self.approve_btn)
        btns.addWidget(self.discard_btn)
        btns.addStretch(1)
        self.tri_detail = QTextBrowser()
        self.tri_detail.setObjectName("detail")
        self.tri_detail.setFont(QFont("Microsoft YaHei UI", 10))
        right = QVBoxLayout()
        right.addWidget(QLabel("候选详情（含证据，供判断）"), 0)
        right.addLayout(btns)
        right.addWidget(self.tri_detail, 1)
        lf = QFrame(); lf.setObjectName("pane")
        ll = QVBoxLayout(lf); ll.setContentsMargins(6, 6, 6, 6); ll.addWidget(self.tri_list)
        rf = QFrame(); rf.setObjectName("pane")
        rl = QVBoxLayout(rf); rl.setContentsMargins(14, 12, 14, 12); rl.addLayout(right)
        h = QHBoxLayout(); h.setContentsMargins(16, 12, 16, 12); h.addWidget(lf, 5); h.addSpacing(12); h.addWidget(rf, 7)
        w = QWidget(); w.setLayout(h)
        return w

    def staged_ids(self):
        return [i for i, d in self.docs.items() if d.get("status") == "staged"]

    def reload_triage(self):
        self.tri_list.clear()
        for did in self.staged_ids():
            d = self.docs.get(did)
            if not d:
                continue
            item = QListWidgetItem(f"{d.get('title') or '（无标题）'}\ntype={d.get('type')} · staged")
            item.setData(Qt.ItemDataRole.UserRole, did)
            self.tri_list.addItem(item)
        self.status.showMessage(f"候选 {self.tri_list.count()} 条待审（自动抽取未验证，全部以 staged 状态入库）")

    def show_triage_detail(self, current, _prev=None):
        if current is None:
            return
        self.tri_detail.setHtml(self.render_note(self.docs.get(current.data(Qt.ItemDataRole.UserRole))))

    def approve_selected(self):
        cur = self.tri_list.currentItem()
        if cur is None:
            self.status.showMessage("请先选择要转正的候选")
            return
        did = cur.data(Qt.ItemDataRole.UserRole)
        d = self.docs.get(did)
        path = (BASE / d.get("path", "")) if d else None
        if path and path.exists():
            t = path.read_text(encoding="utf-8")
            t = t.replace("status: staged", "status: active", 1)
            path.write_text(t, encoding="utf-8")
            mem.build_index()
            self.idx = mem.load_index(force=True)
            self.docs = self.idx.get("docs", {})
            self.reload_triage()
            self.refresh_list()
            self.status.showMessage(f"已转正：{d.get('title')}")

    # ============ 数据导入 · 子模块：文档导入 ============
    def build_import(self) -> QWidget:
        from PySide6.QtWidgets import QPushButton as _PB, QFileDialog as _FD

        self.imp_space = QComboBox()
        self.imp_space.setMinimumWidth(220)
        self.pick_btn = _PB("选择目录…")
        self.pick_btn.setProperty("accent", "warn")
        self.pick_btn.clicked.connect(self.do_pick_dir)
        self.scan_btn = _PB("扫描空间")
        self.scan_btn.setProperty("accent", "warn")
        self.scan_btn.clicked.connect(self.do_scan)
        self.extract_btn = _PB("提取到块库")
        self.extract_btn.setProperty("accent", "okay")
        self.extract_btn.clicked.connect(self.do_extract)
        hint = QLabel("导入：选空间或任意盘/目录 → 扫描统计 → 提取文本块（调系统 Python）→ 在对话中提炼为经验。")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{WB['text2']};font-size:11px;padding:2px 12px")

        bar = QHBoxLayout()
        bar.setContentsMargins(16, 10, 16, 2)
        bar.addWidget(QLabel("数据源："))
        bar.addWidget(self.imp_space, 1)
        bar.addSpacing(8)
        bar.addWidget(self.pick_btn)
        bar.addSpacing(6)
        bar.addWidget(self.scan_btn)
        bar.addSpacing(6)
        bar.addWidget(self.extract_btn)

        self.imp_info = QTextBrowser()
        self.imp_info.setObjectName("detail")
        self.imp_info.setFont(QFont("Microsoft YaHei UI", 10))
        self.imp_info.setMinimumHeight(120)

        self.imp_blocks = QListWidget()
        self.imp_blocks.setObjectName("list")
        self.imp_blocks.setFont(QFont("Microsoft YaHei UI", 9))
        self.imp_blocks.currentItemChanged.connect(self.show_block)

        self.imp_preview = QTextBrowser()
        self.imp_preview.setObjectName("detail")
        self.imp_preview.setFont(QFont("Microsoft YaHei UI", 10))

        left = QFrame(); left.setObjectName("pane")
        ll = QVBoxLayout(left); ll.setContentsMargins(6, 6, 6, 6)
        ll.addWidget(self.imp_info)
        ll.addWidget(QLabel("已提取文本块（点击预览）"), 0)
        ll.addWidget(self.imp_blocks, 1)

        right = QFrame(); right.setObjectName("pane")
        rl = QVBoxLayout(right); rl.setContentsMargins(12, 10, 12, 10)
        rl.addWidget(self.imp_preview)

        mid = QHBoxLayout()
        mid.setContentsMargins(16, 4, 16, 12)
        mid.addWidget(left, 2)
        mid.addSpacing(12)
        mid.addWidget(right, 3)

        page = QVBoxLayout()
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)
        page.addLayout(bar)
        page.addWidget(hint)
        page.addLayout(mid, 1)
        w = QWidget()
        w.setLayout(page)
        return w

    def reload_import(self):
        """填充空间下拉（F 盘顶层目录，按文档数过滤）。"""
        self.imp_space.blockSignals(True)
        self.imp_space.clear()
        self._imp_docs: dict[str, int] = {}
        if SPACES_ROOT.exists():
            for entry in sorted(SPACES_ROOT.iterdir(), key=lambda p: p.name.lower()):
                if not entry.is_dir() or entry.name in EXCLUDE_DIRS:
                    continue
                n = sum(1 for f in entry.rglob("*")
                        if f.is_file() and f.suffix.lower() in DOC_EXTS and not f.name.startswith("~$"))
                if n >= 3:
                    self.imp_space.addItem(f"{entry.name}（{n} 文档）", str(entry))
                    self._imp_docs[entry.name] = n
        self.imp_space.blockSignals(False)
        # 恢复上次选择
        last = getattr(self, "_imp_last", None)
        if last:
            i = self.imp_space.findText(last)
            if i >= 0:
                self.imp_space.setCurrentIndex(i)
        self.imp_info.setHtml("<p style='color:#86868b'>选择上方空间后点击「扫描空间」查看文档构成。</p>")
        self.imp_blocks.clear()

    def do_pick_dir(self):
        """通过系统目录选择器选任意盘/目录，加入数据源下拉并立即扫描。"""
        from PySide6.QtWidgets import QFileDialog

        start = self.imp_space.currentData() or str(SPACES_ROOT)
        d = QFileDialog.getExistingDirectory(self, "选择要导入的目录（任意盘/路径）", start)
        if not d:
            return
        d = os.path.normpath(d)
        label = f"{os.path.basename(d) or d}（{d[:1]}: 盘）"
        for i in range(self.imp_space.count()):
            if self.imp_space.itemData(i) == d:
                self.imp_space.setCurrentIndex(i)
                self.do_scan()
                return
        self.imp_space.addItem(label, d)
        self.imp_space.setCurrentIndex(self.imp_space.count() - 1)
        self.do_scan()

    def do_scan(self):
        d = self.imp_space.currentData()
        if not d:
            self.status.showMessage("请先选择空间")
            return
        name = self.imp_space.currentText().split("（")[0]
        self._imp_last = self.imp_space.currentText()
        root = Path(d)
        by_ext: dict[str, int] = {}
        total = 0
        for f in root.rglob("*"):
            if f.is_file() and f.suffix.lower() in DOC_EXTS and not f.name.startswith("~$"):
                ext = f.suffix.lower()
                by_ext[ext] = by_ext.get(ext, 0) + 1
                total += 1
        rough = "；".join(f"{e[1:]} {c}" for e, c in sorted(by_ext.items(), key=lambda kv: -kv[1]))
        self.imp_info.setHtml(
            f"<h3 style='color:#1d1d1f'>空间：{name}</h3>"
            f"<p>路径：<span style='font-size:11px;color:#86868b'>{root}</span></p>"
            f"<p>文档：<b>{total}</b> 个</p>"
            f"<p>构成：{rough or '—'}</p>"
            "<p style='color:#86868b;font-size:11px'>下一步：点「提取到块库」把文本提取为可浏览的分块（docx/pdf/xlsx 走系统 Python）。</p>"
        )
        self.status.showMessage(f"扫描完成：{name} 共 {total} 个文档")
        self.reload_blocks(name)

    def reload_blocks(self, space_name: str | None = None):
        self.imp_blocks.clear()
        name = space_name or self.imp_space.currentText().split("（")[0]
        d = CHUNKS_ROOT / name
        if not d.exists():
            # 块库可能按子目录分散（按项目/主题组织），列出可用块库目录
            avail = sorted(x.name for x in CHUNKS_ROOT.iterdir() if x.is_dir()) if CHUNKS_ROOT.exists() else []
            hit = [x for x in avail if name in x or x in name]
            self.status.showMessage(
                f"「{name}」尚无顶层块库；可用块库：{hit[:6] or avail[:8] or '空'}。点「提取到块库」生成。"
            )
            return
        for f in sorted(d.glob("*.txt")):
            item = QListWidgetItem(f.stem[:48])
            item.setData(Qt.ItemDataRole.UserRole, str(f))
            self.imp_blocks.addItem(item)
        self.status.showMessage(f"块库 {name}：{self.imp_blocks.count()} 个文本块")

    def show_block(self, current, _prev=None):
        if current is None:
            return
        p = Path(current.data(Qt.ItemDataRole.UserRole))
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = "（读取失败）"
        self.imp_preview.setPlainText(text[:4000])

    def do_extract(self):
        d = self.imp_space.currentData()
        if not d:
            self.status.showMessage("请先选择空间")
            return
        name = self.imp_space.currentText().split("（")[0]
        CHUNKS_ROOT.mkdir(parents=True, exist_ok=True)
        self.status.showMessage(f"正在提取 {name}…（文档较多时请稍候）")
        QApplication.processEvents()
        cmd = [SYS_PY, str(BASE / "ingest.py"), "extract", str(d), "--out-dir", str(CHUNKS_ROOT)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=1800)
            out = (r.stdout or "") + (r.stderr or "")
        except Exception as exc:  # noqa: BLE001
            self.status.showMessage(f"提取失败：{exc}")
            return
        self.imp_info.append("<hr><pre style='font-size:11px'>" + _h.escape(out[-1200:]) + "</pre>")
        self.reload_blocks(name)
        self.status.showMessage(f"{name} 提取完成")

    # ============ 热层预览 ============
    def build_hot(self) -> QWidget:
        self.hot_list = QListWidget()
        self.hot_list.setObjectName("list")
        self.hot_list.setFont(QFont("Microsoft YaHei UI", 10))
        self.hot_list.currentItemChanged.connect(self.show_hot_detail)
        hint = QLabel("以下条目将随热层同步到宿主必读文件，下一会话开始必然注入上下文（上限 20 条）。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a8f98;font-size:11px;padding:4px 12px")
        self.unhot_btn = QPushButton("移出热层")
        self.unhot_btn.setProperty("accent", "warn")
        self.unhot_btn.setToolTip("去掉 hot: true（有进有出，腾位给新经验）")
        self.unhot_btn.clicked.connect(lambda: self.on_unhot(self.hot_current_doc()))
        unhot_bar = QHBoxLayout()
        unhot_bar.addWidget(hint, 1)
        unhot_bar.addWidget(self.unhot_btn)
        self.hot_detail = QTextBrowser()
        self.hot_detail.setObjectName("detail")
        self.hot_detail.setFont(QFont("Microsoft YaHei UI", 10))
        lf = QFrame(); lf.setObjectName("pane")
        ll = QVBoxLayout(lf); ll.setContentsMargins(6, 6, 6, 6); ll.addLayout(unhot_bar); ll.addWidget(self.hot_list, 1)
        rf = QFrame(); rf.setObjectName("pane")
        rl = QVBoxLayout(rf); rl.setContentsMargins(14, 12, 14, 12); rl.addWidget(self.hot_detail)
        h = QHBoxLayout(); h.setContentsMargins(16, 12, 16, 12); h.addWidget(lf, 5); h.addSpacing(12); h.addWidget(rf, 7)
        w = QWidget(); w.setLayout(h)
        return w

    def hot_current_doc(self) -> dict | None:
        item = self.hot_list.currentItem()
        if item is None:
            return None
        return self.docs.get(item.data(Qt.ItemDataRole.UserRole))

    def hot_ids(self):
        return [i for i, d in self.docs.items() if d.get("hot") in ("true", "1")]

    def reload_hot(self):
        self.hot_list.clear()
        for did in self.hot_ids():
            d = self.docs.get(did)
            if not d:
                continue
            item = QListWidgetItem(f"★ {d.get('title') or '（无标题）'}\n{TYPE_LABEL.get(d.get('type'), '?')} · hot")
            item.setData(Qt.ItemDataRole.UserRole, did)
            self.hot_list.addItem(item)
        self.status.showMessage(f"热层 {self.hot_list.count()} 条（上限 20）")

    def show_hot_detail(self, current, _prev=None):
        if current is None:
            return
        self.hot_detail.setHtml(self.render_note(self.docs.get(current.data(Qt.ItemDataRole.UserRole))))

    # ============ 统计诊断 ============
    def build_stats(self) -> QWidget:
        self.stat_box = QTextBrowser()
        self.stat_box.setObjectName("detail")
        self.stat_box.setFont(QFont("Microsoft YaHei UI", 10))
        w = QFrame(); w.setObjectName("pane")
        l = QVBoxLayout(w); l.setContentsMargins(20, 16, 20, 16)
        l.addWidget(self.stat_box)
        return w

    def reload_stats(self):
        total = len(self.docs)
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        hot = 0
        for d in self.docs.values():
            by_type[d.get("type", "?")] = by_type.get(d.get("type", "?"), 0) + 1
            by_status[d.get("status", "?")] = by_status.get(d.get("status", "?"), 0) + 1
            if d.get("hot") in ("true", "1"):
                hot += 1
        rows = ["<h3 style='color:#1f2328'>记忆库统计</h3>",
                f"<p>笔记总数：<b>{total}</b></p>",
                "<p>类型：" + " · ".join(f"{TYPE_LABEL.get(k, k)} {v}" for k, v in sorted(by_type.items())) + "</p>",
                "<p>状态：" + " · ".join(f"{k} {v}" for k, v in sorted(by_status.items())) + "</p>",
                f"<p>热层：<b>{hot}</b> 条（上限 20，满足「有进有出」治理）</p>",
                "<hr><h4>检索说明</h4>",
                "<p>引擎：本地 BM25（中文 2/3-gram + 英文词 + 代码标识符），标题加权，无向量、无云服务。</p>",
                "<p>命中率：在记忆浏览页输入关键词查看 Top-N 与分数，比无命中强过凭印象。</p>",
                "<h4>数据</h4>",
                f"<p>数据目录：<span style='font-size:11px'>{BASE}</span></p>",
                f"<p>索引词项：{self.idx.get('postings', {}) and '就绪' or '空'}</p>"]
        self.stat_box.setHtml("\n".join(rows))

    # ============ 会话集成（会话层工具安装布置）============
    HOSTS = [
        ("WorkBuddy", Path.home() / ".workbuddy" / "skills" / "personal-memory" / "SKILL.md",
         "用户级技能热加载，装机即生效"),
        ("Claude Code", Path.home() / ".claude" / "skills" / "personal-memory" / "SKILL.md",
         "Claude Code 会读取 skills/ 目录（兼容 SKILL.md 格式）"),
        ("CodeBuddy", Path.home() / ".codebuddy" / "skills" / "personal-memory" / "SKILL.md",
         "与 WorkBuddy 技能格式互通"),
    ]

    def build_integration(self) -> QWidget:
        from PySide6.QtWidgets import QPushButton as _PB

        # —— 卡 1：会话层技能 · 多宿主安装布置 ——
        self.host_list = QListWidget()
        self.host_list.setObjectName("list")
        self.host_list.setFont(QFont("Microsoft YaHei UI", 10))
        self.host_list.setMaximumHeight(168)
        self.host_install_btn = _PB("安装到选中宿主")
        self.host_install_btn.setProperty("accent", "okay")
        self.host_install_btn.clicked.connect(self.install_skill)
        self.host_refresh_btn = _PB("刷新状态")
        self.host_refresh_btn.setProperty("accent", "warn")
        self.host_refresh_btn.clicked.connect(self.reload_integration)
        c1 = QFrame(); c1.setObjectName("pane")
        c1l = QVBoxLayout(c1); c1l.setContentsMargins(16, 12, 16, 12)
        c1l.addWidget(QLabel("<b>① 会话层技能安装布置</b>——选中宿主 → 一键安装 personal-memory 技能，让每个新会话「开始 recall、行动前 recall、收尾 add」"))
        c1l.addWidget(self.host_list)
        hb = QHBoxLayout()
        hb.addWidget(self.host_refresh_btn)
        hb.addStretch(1)
        hb.addWidget(self.host_install_btn)
        c1l.addLayout(hb)

        # —— 卡 2：热层同步 ——
        self.hot_lbl = QLabel()
        self.hot_lbl.setStyleSheet(f"color:{WB['text2']};font-size:11px")
        self.hot_sync_btn = _PB("同步热层 → 宿主必读文件")
        self.hot_sync_btn.setProperty("accent", "okay")
        self.hot_sync_btn.clicked.connect(self.sync_hot)
        c2 = QFrame(); c2.setObjectName("pane")
        c2l = QVBoxLayout(c2); c2l.setContentsMargins(16, 12, 16, 12)
        c2l.addWidget(QLabel("<b>② 热层注入</b>——19 条方法论 → MEMORY.md → 新会话必读"))
        c2l.addWidget(self.hot_lbl)
        c2l.addWidget(self.hot_sync_btn)

        # —— 卡 3：会话收割 ——
        self.harvest_lbl = QLabel()
        self.harvest_lbl.setStyleSheet(f"color:{WB['text2']};font-size:11px")
        self.harvest_btn = _PB("立即收割近 3 天会话")
        self.harvest_btn.setProperty("accent", "okay")
        self.harvest_btn.clicked.connect(self.run_harvest)
        c3 = QFrame(); c3.setObjectName("pane")
        c3l = QVBoxLayout(c3); c3l.setContentsMargins(16, 12, 16, 12)
        c3l.addWidget(QLabel("<b>③ 会话收割</b>——从执行记录挖「失败→重试→成功」模式，进候选"))
        c3l.addWidget(self.harvest_lbl)
        c3l.addWidget(self.harvest_btn)

        # —— 卡 4：宿主状态说明 ——
        self.host_lbl = QLabel()
        self.host_lbl.setWordWrap(True)
        self.host_lbl.setStyleSheet(f"color:{WB['text2']};font-size:11px")
        c4 = QFrame(); c4.setObjectName("pane")
        c4l = QVBoxLayout(c4); c4l.setContentsMargins(16, 12, 16, 12)
        c4l.addWidget(QLabel("<b>④ 宿主适配状态</b>"))
        c4l.addWidget(self.host_lbl)

        page = QVBoxLayout()
        page.setContentsMargins(16, 12, 16, 12)
        page.setSpacing(10)
        page.addWidget(c1)
        page.addWidget(c2)
        page.addWidget(c3)
        page.addWidget(c4)
        page.addStretch(1)
        w = QWidget()
        w.setLayout(page)
        return w

    def reload_integration(self):
        # 技能状态：多宿主清单
        self.host_list.clear()
        for i, (name, dest, note) in enumerate(self.HOSTS):
            if dest.exists():
                st = f"已安装（{time.strftime('%m-%d %H:%M', time.localtime(dest.stat().st_mtime))}）"
            else:
                st = "未安装"
            item = QListWidgetItem(f"{name}\n  状态：{st} ｜ {note}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.host_list.addItem(item)
        if self.host_list.count():
            self.host_list.setCurrentRow(0)
        # 热层状态
        hot_n = sum(1 for d in self.docs.values() if d.get("hot") in ("true", "1"))
        hot_lbl = f"当前热层 {hot_n} 条（上限 20）"
        hp = BASE / "index.json"
        if hp.exists():
            hot_lbl += f" · 索引更新于 {self.idx.get('built_at', '?')}"
        self.hot_lbl.setText(hot_lbl)
        # 收割状态
        st = {}
        sp = BASE / "harvest_state.json"
        if sp.exists():
            try:
                st = json.loads(sp.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                st = {}
        cand = len(list((BASE / "notes" / "candidates").glob("*.md"))) if (BASE / "notes" / "candidates").exists() else 0
        self.harvest_lbl.setText(
            f"上次收割：{st.get('last_run', '从未')} · 已处理记录 {len(st.get('processed_callids', []))} · 候选 {cand} 条"
        )
        # 宿主状态
        self.host_lbl.setText(
            "· WorkBuddy 桌面端：第三方插件钩子被禁用（宿主信任模型），自建能力走 skill + MCP。\n"
            "· personal-memory skill：用户级技能热加载，无需重启即可用（已在本页安装）。\n"
            "· 热层注入：通过 MEMORY.md 热层区 → 新会话上下文（上限 20，有进有出）。\n"
            "· MCP 通道：如需 MCP 服务，用独立注册（.mcp.json）绕开插件市场限制。"
        )

    def install_skill(self):
        """从项目模板安装/更新 personal-memory skill 到用户级技能目录。"""
        src = BASE / "templates" / "personal-memory.SKILL.md"
        if not src.exists():
            self.status.showMessage("项目内没有技能模板（templates/personal-memory.SKILL.md）")
            return
        try:
            self.SKILL_DEST.parent.mkdir(parents=True, exist_ok=True)
            self.SKILL_DEST.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError as exc:
            self.status.showMessage(f"安装失败：{exc}")
            return
        self.reload_integration()
        self.status.showMessage("技能已安装/更新（用户级技能热加载，新会话即生效）")

    def sync_hot(self):
        """同步热层到宿主必读文件（项目工作记忆 MEMORY.md 的热层区）。"""
        target = BASE.parent / ".workbuddy" / "memory" / "MEMORY.md"
        cmd = [sys.executable, str(BASE / "mem.py"), "hot", "--limit", "20", "--apply", "--target", str(target)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=120)
            out = (r.stdout or "") + (r.stderr or "")
        except Exception as exc:  # noqa: BLE001
            self.status.showMessage(f"同步失败：{exc}")
            return
        self.status.showMessage(out.strip() or "热层已同步")
        self.reload_integration()

    def run_harvest(self):
        """收割近 3 天会话 → 候选。"""
        self.status.showMessage("收割中…（扫描执行记录，可能需要十几秒）")
        QApplication.processEvents()
        cmd = [sys.executable, str(BASE / "harvest.py"), "scan", "--days", "3"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=600)
            out = (r.stdout or "") + (r.stderr or "")
        except Exception as exc:  # noqa: BLE001
            self.status.showMessage(f"收割失败：{exc}")
            return
        self.status.showMessage("收割完成")
        self.harvest_lbl.setText("收割完成：" + out.strip().splitlines()[0] if out else "完成（无输出）")
        self.idx = mem.load_index(force=True)
        self.docs = self.idx.get("docs", {})
        self.reload_integration()

    # ============ 动作 ============
    def refresh_all(self):
        self.refresh_list()

    def on_new(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("新建记忆")
        dlg.resize(560, 420)
        form = QFormLayout(dlg)
        title_edit = QLineEdit()
        title_edit.setPlaceholderText("一句话标题")
        body_edit = QPlainTextEdit()
        body_edit.setPlaceholderText("正文（Markdown）：问题 → 无效做法 → 已验证做法 → 适用范围")
        form.addRow("标题", title_edit)
        form.addRow("正文", body_edit)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("保存")
        box.button(QDialogButtonBox.Cancel).setText("取消")
        form.addRow(box)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        if dlg.exec() and title_edit.text().strip():
            import time as _t
            title = title_edit.text().strip()
            body = body_edit.toPlainText().strip()
            nid = _t.strftime("%Y%m%d-%H%M-%S") + "-manual"
            note = (f"---\nid: {nid}\ntype: lesson\nstatus: staged\ntitle: {title}\n"
                    f"tags: [待整理]\ncreated: {_t.strftime('%Y-%m-%d')}\n---\n\n{body}\n")
            (BASE / "notes" / "lessons" / f"manual-{nid}.md").write_text(note, encoding="utf-8")
            mem.build_index()
            self.idx = mem.load_index(force=True)
            self.docs = self.idx.get("docs", {})
            self.refresh_list()
            self.status.showMessage(f"已保存：{title}（staged，转正后才能被 recall 命中）")

def main() -> int:
    global QT_MODE
    QT_MODE = bool(os.environ.get("PMEM_THEME", "").strip())

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("pmem")

    if QT_MODE:
        _theme = os.environ["PMEM_THEME"]
        try:
            import qt_material
            from qt_material import apply_stylesheet

            # 绕开 qt-material 的图标资源重置（rmtree 重建 ~/.qt_material，
            # 被宿主删除防护拦截）。本应用不用它的图标，QSS 主题照常生效。
            qt_material.set_icons_theme = lambda *a, **k: None
            apply_stylesheet(app, theme=_theme)
        except Exception as exc:  # noqa: BLE001
            print(f"[pmem] qt-material 未生效，回退内置 WorkBuddy 主题：{exc}", file=sys.stderr)

    win = MainWindow()
    win.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
