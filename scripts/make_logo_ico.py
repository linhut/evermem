#!/usr/bin/env python3
# 恒忆 Evermem 品牌 Logo · ICO/Favicon 打包（零依赖：ICONDIR + 内嵌 PNG，Vista+ 支持）
# 用法：python scripts/make_logo_ico.py
# 产物：brand/favicon.ico（16+32）、brand/favicon.png（32）、brand/evermem.ico（16/32/48/64/128/256）

from __future__ import annotations

import struct
from pathlib import Path

BRAND = Path(__file__).resolve().parent.parent / "brand"
PNG = BRAND / "png"


def load_png(size: int) -> bytes:
    return (PNG / f"evermem-logo-{size}.png").read_bytes()


def build_ico(sizes: list[int], out: Path) -> None:
    """ICONDIR + ICONDIRENTRY* + PNG 数据（PNG 压缩 ICO）。"""
    count = len(sizes)
    header = struct.pack("<HHH", 0, 1, count)
    entries = b""
    blobs = []
    offset = 6 + 16 * count
    for size in sizes:
        blob = load_png(size)
        w = 0 if size >= 256 else size
        h = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(blob), offset)
        blobs.append(blob)
        offset += len(blob)
    out.write_bytes(header + entries + b"".join(blobs))
    print(f"ICO 打包 {out.name}: {count} 尺寸 -> {out.stat().st_size} 字节")


def main() -> None:
    build_ico([16, 32], BRAND / "favicon.ico")
    build_ico([16, 32, 48, 64, 128, 256], BRAND / "evermem.ico")
    # favicon.png = 32px（现代浏览器 HTML link 常用）
    (BRAND / "favicon.png").write_bytes(load_png(32))
    print("favicon.png 32px 就绪")


if __name__ == "__main__":
    main()
