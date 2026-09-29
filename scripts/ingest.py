#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# ingest - 存量文档提取（只读，不改动源文件）
#
#
# 依赖 python-docx / openpyxl / pypdf，需用系统 Python 运行：
#   C:/Python314/python.exe ingest.py list    "F:/市应急指挥中心" --out files.json
#   C:/Python314/python.exe ingest.py extract "F:/市应急指挥中心" --sample 100
#   C:/Python314/python.exe ingest.py extract "F:/政务云" --out-dir "F:/知识库数据/chunks"

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

DOC_EXT = {".docx", ".xlsx", ".pdf", ".doc", ".txt", ".md", ".pptx", ".csv"}
NOISE_PREFIX = ("~$", ".~")
CHUNK_LIMIT = 1500

def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith(NOISE_PREFIX):
            continue
        if path.suffix.lower() not in DOC_EXT:
            continue
        yield path

def chunk_text(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    """按段落累积成块，尽量不在句子中间断开。"""
    blocks: list[str] = []
    buf = ""
    for para in text.splitlines():
        para = para.strip()
        if not para:
            continue
        if len(buf) + len(para) + 1 > limit and buf:
            blocks.append(buf)
            buf = para
        else:
            buf = f"{buf}\n{para}" if buf else para
    if buf:
        blocks.append(buf)
    return blocks

def extract_docx(path: Path) -> str:
    import docx  # noqa: PLC0415

    doc = docx.Document(str(path))
    parts: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name or "").lower()
        if "heading" in style or "标题" in style:
            parts.append(f"\n## {text}\n")
        else:
            parts.append(text)
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return "\n".join(parts)

def extract_xlsx(path: Path) -> str:
    import openpyxl  # noqa: PLC0415

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    parts: list[str] = []
    try:
        for ws in wb.worksheets:
            parts.append(f"\n## 工作表：{ws.title}\n")
            rows = [
                r for r in ws.iter_rows(values_only=True)
                if any(c not in (None, "") for c in r)
            ]
            if not rows:
                continue
            # 真正的表头：第一个至少两个非空单元格的行；
            # 它之前的行是合并标题（如"电信巡检报告"横跨多列），单列出来即可
            header_idx = 0
            for i, r in enumerate(rows):
                if sum(1 for c in r if c not in (None, "")) >= 2:
                    header_idx = i
                    break
            if header_idx > 0:
                title = " ".join(
                    str(c) for c in rows[header_idx - 1] if c not in (None, "")
                )
                parts.append(f"标题：{title}")
            header = [str(c) if c is not None else "" for c in rows[header_idx]]
            parts.append(" | ".join(header))
            for row in rows[header_idx + 1:]:
                cells = [str(c) if c is not None else "" for c in row]
                desc = "；".join(f"{h}: {v}" for h, v in zip(header, cells) if h and v)
                parts.append(desc or " | ".join(cells))
    finally:
        wb.close()
    return "\n".join(parts)

def extract_pdf(path: Path) -> str:
    import pypdf  # noqa: PLC0415

    reader = pypdf.PdfReader(str(path))
    parts: list[str] = []
    for i, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        if text.strip():
            parts.append(f"\n## 第 {i} 页\n{text.strip()}")
    return "\n".join(parts)

def extract_plain(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")

def is_clean_text(text: str) -> bool:
    """有效文本判定：控制字符比例过高视为解析失败，避免乱码入库。"""
    if not text or len(text) < 20:
        return False
    bad = sum(1 for ch in text if ord(ch) < 32 or 0x80 <= ord(ch) <= 0x9F)
    return bad / len(text) < 0.05

def extract_doc(path: Path) -> str:
    """老式 .doc（OLE2 复合文档）：读 WordDocument 流的文本区。

    质量不如新版解析器，但对绝大多数 .doc 足够；加密或损坏的会抛错。
    """
    import olefile  # noqa: PLC0415

    ole = olefile.OleFileIO(str(path))
    try:
        stream = ole.openstream("WordDocument")
        data = stream.read()
    finally:
        ole.close()
    if len(data) < 0x20:
        return ""
    fc_min = int.from_bytes(data[0x18:0x1C], "little")
    fc_mac = int.from_bytes(data[0x1C:0x20], "little")
    if fc_min < 0 or fc_mac < fc_min or fc_mac > len(data):
        return ""
    raw = data[fc_min:fc_mac]
    # 无 BOM 的 UTF-16LE 特征：偶数位置大量空字节
    if len(raw) >= 4:
        evens = raw[1::2]
        if evens.count(0) > max(2, int(len(evens) * 0.4)):
            try:
                return raw.decode("utf-16-le")
            except UnicodeDecodeError:
                pass
    # 中文老文档多用 GBK；UTF-16 编码的以 0xFF 0xFE 或 0xFE 0xFF 开头
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return raw.decode("utf-16-le" if raw[:2] == b"\xff\xfe" else "utf-16-be")
        except UnicodeDecodeError:
            pass
    for enc in ("gbk", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("gbk", errors="ignore")

EXTRACTORS = {
    ".docx": extract_docx,
    ".doc": extract_doc,
    ".xlsx": extract_xlsx,
    ".pdf": extract_pdf,
    ".txt": extract_plain,
    ".md": extract_plain,
    ".csv": extract_plain,
}

def cmd_list(args) -> int:
    root = Path(args.root)
    rows = []
    for path in iter_files(root):
        try:
            st = path.stat()
        except OSError:
            continue
        rows.append({
            "path": str(path),
            "ext": path.suffix.lower(),
            "size": st.st_size,
            "mtime": time.strftime("%Y-%m-%d", time.localtime(st.st_mtime)),
        })
    rows.sort(key=lambda r: -r["size"])
    print(f"目录：{root}")
    print(f"文档数：{len(rows)}")
    by_ext: dict[str, int] = {}
    total = 0
    for r in rows:
        by_ext[r["ext"]] = by_ext.get(r["ext"], 0) + 1
        total += r["size"]
    print(f"总大小：{total / 1048576:.1f} MB")
    print("类型分布：", dict(sorted(by_ext.items(), key=lambda kv: -kv[1])))
    if args.out:
        Path(args.out).write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"已保存：{args.out}")
    return 0

def cmd_extract(args) -> int:
    root = Path(args.root)
    files = list(iter_files(root))
    if args.sample and args.sample < len(files):
        random.seed(42)
        files = random.sample(files, args.sample)

    print(f"目录：{root}")
    print(f"待提取：{len(files)} 个文档\n")

    started = time.time()
    ok = 0
    failed: list[tuple[str, str]] = []
    total_chars = 0
    by_ext: dict[str, int] = {}
    samples: list[tuple[str, int, str]] = []

    for path in files:
        ext = path.suffix.lower()
        func = EXTRACTORS.get(ext)
        if func is None:
            failed.append((str(path), f"暂不支持 {ext}"))
            continue
        try:
            text = func(path)
        except Exception as exc:  # noqa: BLE001
            failed.append((str(path), f"{type(exc).__name__}: {exc}"))
            continue
        if not is_clean_text(text):
            failed.append((str(path), "文本疑似乱码或不可读"))
            continue
        blocks = chunk_text(text)
        ok += 1
        by_ext[ext] = by_ext.get(ext, 0) + 1
        total_chars += len(text)
        if len(samples) < 3:
            samples.append((path.name, len(text), text.strip()[:150]))
        if args.out_dir:
            out_root = Path(args.out_dir) / root.name
            out_root.mkdir(parents=True, exist_ok=True)
            stem = path.stem[:60]
            for i, block in enumerate(blocks, 1):
                (out_root / f"{stem}__{i:03d}.txt").write_text(block, encoding="utf-8")

    elapsed = time.time() - started
    print(f"成功 {ok} / 失败 {len(failed)}")
    print("成功类型分布：", dict(sorted(by_ext.items(), key=lambda kv: -kv[1])))
    print(f"提取文本：{total_chars / 1024:.1f} KB（{total_chars / 1048576:.2f} MB）")
    if ok:
        print(f"平均每个：{total_chars / ok / 1024:.1f} KB")
        print(f"全量外推（{len(list(iter_files(root)))} 个）：约 {total_chars / ok * len(list(iter_files(root))) / 1048576:.0f} MB")
    print(f"耗时：{elapsed:.1f} 秒")

    if failed and args.show_failed:
        print(f"\n失败样例（最多 10）：")
        for p, why in failed[:10]:
            print(f"  {Path(p).name}  ←  {why}")

    if samples:
        print("\n提取样例：")
        for name, size, head in samples:
            print(f"\n--- {name}（{size} 字）")
            print("   " + head.replace("\n", " ")[:150])

    return 0

def main() -> int:
    ap = argparse.ArgumentParser(description="存量文档提取（只读）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="列出文档清单")
    p.add_argument("root")
    p.add_argument("--out")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("extract", help="提取文本并分块")
    p.add_argument("root")
    p.add_argument("--sample", type=int, help="随机抽样个数")
    p.add_argument("--out-dir", help="分块输出目录")
    p.add_argument("--show-failed", action="store_true")
    p.set_defaults(func=cmd_extract)

    args = ap.parse_args()
    return args.func(args)

if __name__ == "__main__":
    sys.exit(main())
