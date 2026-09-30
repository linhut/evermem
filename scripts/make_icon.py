#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# make_icon - 生成恒忆桌面版图标（Windows .ico / macOS .icns / 通用 .png）
#
# 为什么做成脚本而不是直接提交二进制：
#   二进制图标改一版就得重新丢一个 blob 进仓库，且无法追溯画的是什么。
#   这里把「图案（SVG）→ 各尺寸 PNG → 平台容器」的过程固化成脚本，
#   任何人重跑一次就能得到一致的图标；产物提交到 assets/ 供打包使用。
#
# 使用（仅生成图标时需要 PySide6；构建打包时不需要，直接用 assets/ 里的产物）：
#   python scripts/make_icon.py
#
# 图案说明：渐变圆角方块 + 白色字母 E（Evermem 首字母）。
#   不用 SVG <text> 渲染中文/字体 —— 字体在不同机器不一致，小尺寸还会糊；
#   纯路径 + rect 保证 16px 下依然可辨。

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# 输出尺寸：ICO 需要多尺寸（任务栏/资源管理器/大图标各自取用）
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
# ICNS 条目：值为像素边长，键为 Apple 定义的类型
#   ic11/ic12 是 @2x 条目，实际存 32/64 像素
ICNS_TYPES = {"ic11": 32, "ic12": 64, "ic07": 128, "ic08": 256, "ic09": 512, "ic10": 1024}

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#4F46E5"/>
      <stop offset="1" stop-color="#0EA5A4"/>
    </linearGradient>
  </defs>
  <rect x="8" y="8" width="240" height="240" rx="56" ry="56" fill="url(#g)"/>
  <g fill="#FFFFFF">
    <rect x="78" y="62" width="26" height="132" rx="6" ry="6"/>
    <rect x="78" y="62" width="104" height="26" rx="6" ry="6"/>
    <rect x="78" y="117" width="88" height="26" rx="6" ry="6"/>
    <rect x="78" y="168" width="104" height="26" rx="6" ry="6"/>
  </g>
</svg>
"""


def render_png(size: int) -> bytes:
    """把 SVG 渲染成指定尺寸的 PNG 字节流。"""
    # 必须在导入 Qt 之前指定离屏平台：无显示器的 CI/沙箱里否则直接崩
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QGuiApplication, QImage
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    renderer = QSvgRenderer(QByteArray(SVG.encode("utf-8")))
    if not renderer.isValid():
        raise RuntimeError("SVG 解析失败")
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    from PySide6.QtGui import QPainter

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    from PySide6.QtCore import QBuffer, QIODevice

    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def build_ico(pngs: dict[int, bytes]) -> bytes:
    """打包 ICO：ICO 头 + 目录项 + PNG 数据（Vista 起支持 PNG 内联）。"""
    n = len(pngs)
    out = bytearray(struct.pack("<HHH", 0, 1, n))
    offset = 6 + 16 * n
    for size in sorted(pngs):
        data = pngs[size]
        # 维度字节：256 在单字节里只能写 0
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for size in sorted(pngs):
        out += pngs[size]
    return bytes(out)


def build_icns(pngs: dict[int, bytes]) -> bytes:
    """打包 ICNS：'icns' 魔数 + 总长 + 若干 (类型, 长度, PNG) 条目。"""
    body = bytearray()
    for typ in ("ic11", "ic12", "ic07", "ic08", "ic09", "ic10"):
        size = ICNS_TYPES[typ]
        data = pngs[size]
        body += typ.encode("ascii") + struct.pack(">I", len(data) + 8) + data
    return b"icns" + struct.pack(">I", len(body) + 8) + bytes(body)


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    sizes = sorted(set(ICO_SIZES) | set(ICNS_TYPES.values()))
    pngs = {s: render_png(s) for s in sizes}

    (ASSETS / "icon.png").write_bytes(pngs[256])
    (ASSETS / "icon.ico").write_bytes(build_ico({s: pngs[s] for s in ICO_SIZES}))
    (ASSETS / "icon.icns").write_bytes(build_icns(pngs))

    for name in ("icon.png", "icon.ico", "icon.icns"):
        p = ASSETS / name
        print(f"{name}: {p.stat().st_size} bytes -> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
