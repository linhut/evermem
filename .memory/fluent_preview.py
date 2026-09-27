#!/usr/bin/env python3
# pmem Fluent 质感骨架预览（PyQt-Fluent-Widgets）
# 验证方向：若质感 OK，再全量迁移 app.py
#
# Copyright (c) 2026 Jose-AI
# SPDX-License-Identifier: MIT

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from qfluentwidgets import (
    FluentWindow, FluentIcon, NavigationItemPosition,
    CardWidget, PrimaryPushButton, PushButton, SearchLineEdit,
    ListWidget, BodyLabel, CaptionLabel, InfoBar, InfoBarPosition,
    setTheme, Theme, SubtitleLabel, ComboBox, ProgressBar, PillPushButton,
)


class DemoCard(CardWidget):
    def __init__(self, title: str, desc: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(88)
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addWidget(SubtitleLabel(title))
        left.addWidget(CaptionLabel(desc))
        lay.addLayout(left, 1)
        lay.addWidget(PillPushButton("操作", self))


class Page(QWidget):
    """通用页面：顶部标题 + 卡片区。"""

    def __init__(self, title: str, desc: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.setSpacing(14)
        lay.addWidget(SubtitleLabel(title))
        lay.addWidget(CaptionLabel(desc))
        # 搜索 + 按钮行
        row = QHBoxLayout()
        search = SearchLineEdit(self)
        search.setPlaceholderText("搜索记忆… Ctrl+K")
        search.setFixedWidth(320)
        btn = PrimaryPushButton("新建笔记", self)
        btn.setIcon(FluentIcon.ADD)
        row.addWidget(search)
        row.addStretch(1)
        row.addWidget(btn)
        lay.addLayout(row)
        # 三张卡
        cards = QHBoxLayout()
        cards.addWidget(DemoCard("候选审核", "7 条 staged 待转正"))
        cards.addWidget(DemoCard("热层预览", "19 条注入可见"))
        cards.addWidget(DemoCard("统计诊断", "39 条 · 7 组测试全绿"))
        lay.addLayout(cards)
        # 列表
        lst = ListWidget(self)
        for i, t in enumerate(["政府应急指挥信息化项目方案编制要点", "融合通信平台能力模型与开放接口经验",
                               "机房整合与设备搬迁项目方案编制要点", "大型体育赛事场馆信息化勘察与保障要点"]):
            lst.addItem(t)
        lst.setFixedHeight(180)
        lay.addWidget(lst, 1)


class Preview(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pmem — Fluent 质感预览")
        self.resize(1200, 780)

        self.p_browse = Page("记忆浏览", "搜索 / 过滤 / BM25 分数 / 双击编辑")
        self.p_triage = Page("候选审核", "staged → 转正 / 暂缓")
        self.p_import = Page("文档导入", "F 盘任意盘目录 → 扫描 / 提取 / 块预览")
        self.p_hot = Page("热层预览", "19 条注入可见 · 一键移出")
        self.p_stats = Page("统计诊断", "分布 / 引擎信息")
        self.p_integ = Page("会话集成", "技能安装 · 热层同步 · 会话收割")

        self.addSubInterface(self.p_browse, FluentIcon.HOME, "记忆浏览")
        self.addSubInterface(self.p_triage, FluentIcon.EDIT, "候选审核")
        self.addSubInterface(self.p_import, FluentIcon.DOWNLOAD, "文档导入")
        self.addSubInterface(self.p_hot, FluentIcon.FIRE, "热层预览")
        self.addSubInterface(self.p_stats, FluentIcon.DATA, "统计诊断")
        self.addSubInterface(self.p_integ, FluentIcon.SETTING, "会话集成")

        self.navigationInterface.setExpandWidth(180)
        self.navigationInterface.setCollapsible(True)


def main() -> int:
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    setTheme(Theme.LIGHT)
    w = Preview()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())