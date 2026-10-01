#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# gen_update_manifest - 生成恒忆更新清单 update-manifest.json（手动工具）
#
# 2026-10-01 定案：CI 不再生成 / 上传 update-manifest.json（Release 不含清单）。
# 清单是官网云服务器上的固定文件（https://www.linhut.cn/evermem/update-manifest.json），
# 由维护者手动生成一次、长期有效——内容只应包含 sources.mirrors 等低频信息
# （不要写死版本号：版本判断由 GitHub Release 说了算，防"忘更新清单=永远显示已是最新"）。
# 本脚本保留为手动工具：需要更新云服务器清单时在本机跑一次 merge（fragment 命令已经不需要）。
#
# 用法（手动更新镜像列表等时）：
#   python scripts/gen_update_manifest.py merge \
#       --fragments <片段目录> --version 0.2.5 --out update-manifest.json \
#       --changelog CHANGELOG.md --mirror https://edgeone.gh-proxy.org/ --mirror https://cdn.gh-proxy.org/
#   然后手动上传 update-manifest.json 到 www.linhut.cn/evermem/update-manifest.json。
#   （fragment 命令供本地扫描单个平台产物仍可用；assets 建议按 {platform: {portable: ..., installer: ...}} 组织）
#
# 为什么曾分两步：
#   三平台是三个并行的 CI job，各只知道自己的产物。所以每个 job 先产出一份
#   「平台片段」，最后一个汇总 job 把片段合成完整的 update-manifest.json。
#   直接在一个 job 里生成是做不到的（拿不到其他平台的 sha256）。

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

REPO = "linhut/evermem"
GITHUB_DOWNLOAD = f"https://github.com/{REPO}/releases/download"
# 片段文件与校验清单不是"可下载资产"，扫描时要排除
NON_ASSET_NAMES = {"SHA256SUMS.txt", "update-fragment.json", "update-manifest.json"}
# GUI 冒烟可能在 exe 同级目录（dist/）留下运行时数据（历史上自动线程写入 index.json 等）。
# 这些不是发布资产，出现时应忽略而不是报"资产不止一个"（若未来真正混入其他文件仍会报错）。
DATA_FILE_NAMES = {
    "index.json", "harvest_state.json", "corpus_spaces.json", "kb.json", "knowledge-base.md",
    "pmem_config.json", "pmem_backup.json", ".pmem-backup-last.json", ".recipe-lock.json",
    "update_state.json", "backup.log",
}


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def find_asset(dist: Path) -> Path:
    """dist 里应该只剩一个平台产物（CI 已移除 .app 与裸二进制）。"""
    items = [p for p in dist.iterdir()
             if p.is_file() and p.name not in NON_ASSET_NAMES
             and not p.name.startswith(".") and p.name not in DATA_FILE_NAMES]
    if not items:
        raise SystemExit(f"[manifest] dist 中没有可发布资产：{dist}")
    if len(items) > 1:
        names = ", ".join(p.name for p in items)
        raise SystemExit(f"[manifest] dist 中资产不止一个（{names}），请检查重命名步骤")
    return items[0]


def cmd_fragment(args) -> int:
    dist = Path(args.dist)
    asset = find_asset(dist)
    version = args.version.strip()
    name = asset.name
    urls = []
    if args.base_url:
        urls.append(args.base_url.rstrip("/") + "/" + name)
    if not args.no_github:
        urls.append(f"{GITHUB_DOWNLOAD}/v{version}/{name}")
    frag = {
        "platform": args.platform,
        "version": version,
        "assets": {
            args.platform: {
                "name": name,
                "size": asset.stat().st_size,
                "sha256": sha256_of(asset),
                "urls": urls,
            }
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(frag, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[manifest] 片段已生成：{out}（{args.platform} · {name} · {frag['assets'][args.platform]['sha256'][:16]}…）")
    return 0


def changelog_notes(path: Path, version: str) -> str:
    """从 CHANGELOG.md 抽取该版本的段落（找不到返回空串，不阻断发布）。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## [") and line.split("]")[0].lstrip("## [").strip() == version:
            start = i + 1
            break
    if start is None:
        return ""
    body = []
    for line in lines[start:]:
        if line.startswith("## ["):
            break
        body.append(line)
    return "\n".join(body).strip()


def cmd_merge(args) -> int:
    frags_dir = Path(args.fragments)
    frags = sorted(frags_dir.glob("*.json"))
    if not frags:
        raise SystemExit(f"[manifest] 没有可合并的片段：{frags_dir}")

    assets: dict = {}
    versions = set()
    for f in frags:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"[manifest] 片段解析失败 {f}: {exc}")
        for key, val in (data.get("assets") or {}).items():
            assets[key] = val
        if data.get("version"):
            versions.add(str(data["version"]))

    version = args.version.strip() or (sorted(versions)[-1] if versions else "")
    if not version:
        raise SystemExit("[manifest] 无法确定版本号（片段无 version 且未传 --version）")
    if len(versions) > 1 and version not in versions:
        print(f"[manifest] 警告：片段版本不一致 {sorted(versions)}，按 --version={version} 汇总")

    notes = changelog_notes(Path(args.changelog), version) if args.changelog else ""
    manifest = {
        "schema": 1,
        "product": "evermem",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "channels": {
            "stable": {
                "version": version,
                "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "notes": notes,
                "assets": assets,
                "previous": None,
            },
            "beta": None,
        },
        # 镜像与端点随清单下发：镜像站存活周期短，客户端写死等于发布即过期
        "sources": {
            "github_api": f"https://api.github.com/repos/{REPO}/releases/latest",
            "mirrors": list(args.mirror or []),
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[manifest] 清单已生成：{out}（v{version} · 平台 {sorted(assets)}）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="生成恒忆更新清单 update-manifest.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fragment", help="生成单平台片段")
    f.add_argument("--platform", required=True, help="平台键，如 windows-x64")
    f.add_argument("--dist", required=True, help="产物目录")
    f.add_argument("--version", required=True, help="版本号（无 v 前缀）")
    f.add_argument("--out", required=True, help="片段输出路径")
    f.add_argument("--base-url", default="", help="自建下载根地址（对象存储/CDN）")
    f.add_argument("--no-github", action="store_true", help="不生成 GitHub 下载直链")
    f.set_defaults(func=cmd_fragment)

    m = sub.add_parser("merge", help="合并片段为完整清单")
    m.add_argument("--fragments", required=True, help="片段目录")
    m.add_argument("--version", default="", help="版本号（缺省取片段里最大的）")
    m.add_argument("--out", required=True, help="清单输出路径")
    m.add_argument("--changelog", default="CHANGELOG.md", help="变更日志路径")
    m.add_argument("--mirror", action="append", default=[], help="镜像前缀，可重复")
    m.set_defaults(func=cmd_merge)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    # Windows runner 控制台默认 cp1252，中文 print 会 UnicodeEncodeError：强制 UTF-8 输出
    if sys.stdout and getattr(sys.stdout, "encoding", "") and \
            sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
