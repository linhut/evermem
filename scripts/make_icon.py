#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# make_icon - 恒忆应用图标打包
#
# 单一事实源：brand/evermem-logo.svg（改完品牌后先跑 node scripts/render_logo.js）。
# 本脚本只负责"把 PNG 装进平台容器"，零渲染依赖，纯 Python 标准库即可执行。
#
# 产物：
#   assets/icon.ico  —— Windows exe/安装包图标（16/24/32/48/64/128/256 帧）
#   assets/icon.icns —— macOS .app 图标（32/64/128/256/512/1024 条目）
#   assets/icon.png  —— Linux/通用图标（256px，PyInstaller/AppImage/Deb 使用）
#
# 用法：python scripts/make_icon.py

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
PNG = ROOT / "brand" / "png"

# Windows ICO：含 24px，Win11 任务栏会自动取这一帧
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]

# macOS ICNS 条目：值为像素边长，键为 Apple 定义的类型
# ic11/ic12 是 @2x 条目，实际存 32/64 像素
ICNS_TYPES = {"ic11": 32, "ic12": 64, "ic07": 128, "ic08": 256, "ic09": 512, "ic10": 1024}


def load_png(size: int) -> bytes:
    p = PNG / f"evermem-logo-{size}.png"
    if not p.exists():
        raise FileNotFoundError(
            f"找不到 {p}。请先运行："
            f"NODE_PATH=.../node_modules node scripts/render_logo.js"
        )
    return p.read_bytes()


def build_ico(pngs: dict[int, bytes]) -> bytes:
    """打包 ICO：ICO 头 + 目录项 + PNG 数据（Vista 起支持 PNG 内联）。"""
    n = len(pngs)
    out = bytearray(struct.pack("<HHH", 0, 1, n))
    offset = 6 + 16 * n
    for size in sorted(pngs):
        data = pngs[size]
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
    ico_sizes = sorted(set(ICO_SIZES) | {24})
    icns_sizes = sorted(set(ICNS_TYPES.values()))
    all_sizes = sorted(set(ico_sizes) | set(icns_sizes))
    pngs = {s: load_png(s) for s in all_sizes}

    (ASSETS / "icon.png").write_bytes(load_png(256))
    (ASSETS / "icon.ico").write_bytes(build_ico({s: pngs[s] for s in ico_sizes}))
    (ASSETS / "icon.icns").write_bytes(build_icns({s: pngs[s] for s in icns_sizes}))

    for name in ("icon.png", "icon.ico", "icon.icns"):
        p = ASSETS / name
        print(f"{name}: {p.stat().st_size} bytes -> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
