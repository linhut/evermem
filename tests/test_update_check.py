#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 许可: MIT License（SPDX-License-Identifier: MIT）

# 更新检查回归测试：多源降级、失败明示、版本比较、配置读写、缓存
#
# 全部用例不联网：用 unittest.mock 替换 update.http_json / http_text。
# 数据目录用临时目录（PMEM_HOME），跑完即删，不碰真实数据。

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="pmem_update_test_")
os.environ["PMEM_HOME"] = TMP

import update  # noqa: E402

PLAT = update.platform_key()
BASE = PLAT.split("-")[0]

# 清单是默认启用的官方云服务器固定文件（www.linhut.cn 托管，镜像列表长期有效；见 update.py 注释）。
# 要测清单行为就用真实域名占位（本项目自有站点），不用 *.example.com 造一个不存在的加速源。
MANIFEST_URL = update.DEFAULT_MANIFEST_URL or "https://www.linhut.cn/evermem/update-manifest.json"


def now_iso(offset_hours=0):
    return (datetime.now(timezone.utc) - timedelta(hours=offset_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def form_asset_name(version: str, form: str = "portable") -> str:
    """按发行形态构造资产名（与 CI 打包产物命名约定一致）。"""
    if BASE == "windows":
        return f"Evermem-windows-v{version}-portable.zip" if form == "portable" \
            else f"Evermem-setup-v{version}.exe"
    if BASE == "macos":
        return f"Evermem-macos-v{version}.app.zip"
    return f"Evermem-linux-v{version}-portable.tar.gz"


def manifest_payload(version="0.9.9", with_platform=True, mirrors=None, generated_at=None):
    assets = {}
    if with_platform:
        assets[PLAT] = {"name": form_asset_name(version), "size": 123,
                        "sha256": "a" * 64,
                        "urls": [f"https://cdn.example.com/{form_asset_name(version)}"]}
    return {
        "schema": 1, "product": "evermem",
        "generated_at": generated_at if generated_at is not None else now_iso(),
        "channels": {"stable": {"version": version, "notes": "修了点东西",
                                "published_at": "2026-09-30T00:00:00Z", "assets": assets}},
        "sources": {"mirrors": mirrors or ["https://m1.example/"]},
    }


def github_payload(version="0.9.9", with_asset=True, sha_asset=False, form="portable"):
    assets = []
    if with_asset:
        name = form_asset_name(version, form)
        assets.append({"name": name, "size": 456,
                       "browser_download_url": f"https://github.com/linhut/evermem/releases/download/v{version}/x"})
    if sha_asset:
        assets.append({"name": "SHA256SUMS.txt", "size": 10,
                       "browser_download_url": "https://example.com/SHA256SUMS.txt"})
    return {"tag_name": f"v{version}", "body": "release notes",
            "published_at": "2026-09-30T00:00:00Z", "assets": assets}


class UpdateCheckTest(unittest.TestCase):
    def setUp(self):
        # 每个用例都从干净的数据目录开始，避免状态串味
        for name in (update.CONFIG_NAME, update.STATE_NAME):
            p = Path(TMP) / name
            if p.exists():
                p.unlink()

    # ---------- 版本比较 ----------
    def test_01_semver_compare(self):
        print("\n一、语义化版本比较")
        cases = [("0.2.4", "0.2.3", 1), ("0.2.3", "0.2.4", -1), ("0.2.3", "0.2.3", 0),
                 ("0.10.0", "0.9.9", 1), ("1.0.0", "0.9.9", 1)]
        for a, b, want in cases:
            got = update.compare_semver(a, b)
            self.assertEqual((got > 0) - (got < 0), want, f"{a} vs {b}")
            print(f"  PASS  {a} vs {b} → {want}")
        # 预发布必须小于对应正式版（DSH 的 latest/next 教训）
        self.assertLess(update.compare_semver("0.2.4-rc.1", "0.2.4"), 0)
        print("  PASS  预发布 0.2.4-rc.1 < 正式版 0.2.4")
        # 带 v 前缀与脏字符串不能崩
        self.assertEqual(update.compare_semver("v0.2.3", "0.2.3"), 0)
        self.assertEqual(update.compare_semver("garbage", "0.2.3"), -1)
        print("  PASS  v 前缀与非法字符串不崩")

    # ---------- 可选源：自建清单（只有配置了才参与） ----------
    def test_02_manifest_success(self):
        print("\n二、配置了自建清单 → 命中即返回（不再请求 GitHub）")
        update.save_config({"manifest_url": MANIFEST_URL})
        with mock.patch.object(update, "http_json", return_value=(manifest_payload(), None, 120)) as m:
            r = update.check(force=True)
            self.assertTrue(r["ok"])
            self.assertEqual(r["latest"], "0.9.9")
            self.assertTrue(r["has_update"])
            self.assertEqual(r["attempts"][0]["source"], "manifest")
            # 清单命中后不应再去打 GitHub：省一次跨境请求
            self.assertEqual(m.call_count, 1)
            # 镜像由清单下发，且拼到直链之后
            self.assertIn("https://m1.example/", " ".join(r["asset"]["urls"]))
            print("  PASS  清单命中，仅请求一次，镜像已下发")

    # ---------- 清单缺当前平台不能算成功 ----------
    def test_03_manifest_missing_platform_is_failure(self):
        print("\n三、清单缺当前平台资产 → 判失败并降级，不能静默说最新")
        update.save_config({"manifest_url": MANIFEST_URL})
        # 按 URL 分派：清单源返回"缺平台"，GitHub 直连与镜像都返回可用结果
        def fake_json(url, timeout=None):
            if "api.github.com" in url:
                return github_payload(), None, 150
            return manifest_payload(with_platform=False), None, 90
        with mock.patch.object(update, "http_json", side_effect=fake_json):
            r = update.check(force=True)
            self.assertTrue(r["ok"], "应降级到 GitHub 源")
            self.assertEqual(r["attempts"][0]["source"], "manifest")
            self.assertEqual(r["attempts"][0]["ok"], False)
            self.assertIn("仅采用其镜像列表", r["attempts"][0]["error"],
                          "缺平台资产时清单仍可只贡献镜像列表")
            self.assertEqual(r["latest"], "0.9.9", "降级后应拿到 GitHub 的版本")
            print("  PASS  清单缺平台判失败并降级到 GitHub")

    # ---------- 全部源失败必须明示 ----------
    def test_04_all_sources_fail_is_explicit(self):
        print("\n四、全部源不可用必须明确报错（禁止静默成功）")
        with mock.patch.object(update, "http_json", return_value=(None, "DNS 解析失败", 3000)):
            r = update.check(force=True)
            self.assertFalse(r["ok"])
            self.assertIsNone(r["latest"])
            self.assertFalse(r["has_update"])
            self.assertEqual(r["error"], "全部更新源不可用")
            # 至少覆盖 manifest + github + 2 个镜像
            self.assertGreaterEqual(len(r["attempts"]), 3)
            for a in r["attempts"]:
                self.assertFalse(a["ok"])
                self.assertTrue(a["error"])
                self.assertTrue(a["url"])
            print(f"  PASS  返回 ok=False 且 {len(r['attempts'])} 个源均有错误与 URL")

    # ---------- HTTP 4xx 也要落到 attempts ----------
    def test_05_http_error_recorded(self):
        print("\n五、HTTP 状态码转成可读错误")
        with mock.patch.object(update, "http_json", return_value=(None, "HTTP 404", 88)):
            r = update.check(force=True)
            self.assertFalse(r["ok"])
            self.assertTrue(all(a["error"] == "HTTP 404" for a in r["attempts"]))
            print("  PASS  HTTP 404 被记录为可读错误")

    # ---------- 缓存 ----------
    def test_06_cache_success_only(self):
        print("\n六、成功结果缓存 24h，失败不缓存")
        update.save_config({"manifest_url": MANIFEST_URL})
        with mock.patch.object(update, "http_json", return_value=(manifest_payload(), None, 100)) as m:
            update.check(force=True)
            again = update.check(force=False)
            self.assertTrue(again.get("cached"))
            self.assertEqual(m.call_count, 1, "缓存命中不应重复联网")
            print("  PASS  命中缓存不重复联网")
        with mock.patch.object(update, "http_json", return_value=(None, "超时", 8000)) as m2:
            per_check = 1 + 1 + len(update.DEFAULT_MIRRORS)  # 清单 + 直连 + 镜像
            f1 = update.check(force=True)
            f2 = update.check(force=True)
            self.assertFalse(f1["ok"]); self.assertFalse(f2["ok"])
            self.assertEqual(m2.call_count, per_check * 2, "失败不应缓存，两次都真的重试了")
            print(f"  PASS  失败不缓存，可重试（每次 {per_check} 个源）")

    # ---------- 配置读写 ----------
    def test_07_config_roundtrip(self):
        print("\n七、更新源配置可切换并回读真实值")
        cfg = update.load_config()
        self.assertEqual(cfg["sources"], ["github", "mirror"], "默认源：GitHub + 镜像（清单默认启用）")
        self.assertEqual(cfg["manifest_url"], "https://www.linhut.cn/evermem/update-manifest.json",
                         "默认清单 = 官方云服务器固定地址")
        saved = update.save_config({"sources": ["github", "mirror"], "mirrors": ["https://x/"]})
        self.assertEqual(saved["sources"], ["github", "mirror"])
        self.assertEqual(saved["mirrors"], ["https://x/"])
        # 回读必须一致（界面显示的就是实际生效配置）
        self.assertEqual(update.load_config()["mirrors"], ["https://x/"])
        print("  PASS  配置写入后回读一致")
        # 默认启用官方云清单（2026-10-01 定案）：检查会先请求它
        with mock.patch.object(update, "http_json", return_value=(github_payload(), None, 60)) as m:
            r = update.check(force=True)
            self.assertTrue(r["ok"])
            self.assertTrue(any(MANIFEST_URL in u for u in [c.args[0] for c in m.call_args_list]),
                            "默认应请求官方云清单")
            print("  PASS  默认请求官方云清单")
        # 用户显式清空 → 不再请求清单（回退 GitHub 直连 + 镜像）
        update.save_config({"manifest_url": ""})
        with mock.patch.object(update, "http_json", return_value=(github_payload(), None, 60)) as m2:
            r2 = update.check(force=True)
            self.assertTrue(r2["ok"])
            self.assertTrue(all(a["source"] != "manifest" for a in r2["attempts"]))
            print("  PASS  清空清单地址后不再请求清单")
        # 填了就用
        update.save_config({"manifest_url": MANIFEST_URL})
        with mock.patch.object(update, "http_json", return_value=(manifest_payload(), None, 50)):
            self.assertEqual(update.check(force=True)["source"], "manifest")
            print("  PASS  填了清单地址即启用清单源")
        # 坏配置退回默认，不让检查崩
        (Path(TMP) / update.CONFIG_NAME).write_text('{"sources": null, "mirrors": "x"}', encoding="utf-8")
        cfg2 = update.load_config()
        self.assertEqual(cfg2["sources"], update.DEFAULT_SOURCES)
        self.assertEqual(cfg2["mirrors"], update.DEFAULT_MIRRORS)
        print("  PASS  配置被改坏时退回默认值")

    # ---------- GitHub 源与 sha256 ----------
    def test_08_github_source_and_sha256(self):
        print("\n八、GitHub 源能取到版本与 sha256")
        def fake_json(url, timeout=None):
            if "SHA256SUMS" in url:
                raise AssertionError("SHA256SUMS 应走 http_text，不是 http_json")
            return github_payload(sha_asset=True), None, 70
        sums = f"{'b' * 64}  {form_asset_name('0.9.9')}\n"
        with mock.patch.object(update, "http_json", side_effect=fake_json), \
             mock.patch.object(update, "http_text", return_value=(sums, None, 40)):
            r = update.check(force=True, )
            self.assertTrue(r["ok"])
            self.assertEqual(r["latest"], "0.9.9")
            self.assertEqual(r["asset"]["sha256"], "b" * 64)
            print("  PASS  从 Release 的 SHA256SUMS.txt 取到校验值")

    # ---------- 平台资产匹配 ----------
    def test_09_platform_asset_match(self):
        print("\n九、平台资产匹配不会串台（平台 × 发行形态）")
        if BASE == "windows":
            self.assertTrue(update._asset_matches("Evermem-windows-v0.2.3-portable.zip", PLAT, "portable"))
            self.assertFalse(update._asset_matches("Evermem-setup-v0.2.3.exe", PLAT, "portable"))
            self.assertTrue(update._asset_matches("Evermem-setup-v0.2.3.exe", PLAT, "installer"))
            self.assertFalse(update._asset_matches("Evermem-windows-v0.2.3-portable.zip", PLAT, "installer"))
            self.assertFalse(update._asset_matches("Evermem-linux-v0.2.3", PLAT))
        elif BASE == "linux":
            self.assertTrue(update._asset_matches("Evermem-linux-v0.2.3-portable.tar.gz", PLAT, "portable"))
            self.assertTrue(update._asset_matches("Evermem-linux-v0.2.3.deb", PLAT, "installer"))
            self.assertFalse(update._asset_matches("Evermem-linux-v0.2.3.AppImage", PLAT, "installer"))
            self.assertFalse(update._asset_matches("Evermem-windows-v0.2.3-portable.zip", PLAT))
        else:
            self.assertTrue(update._asset_matches("Evermem-macos-v0.2.3.app.zip", PLAT))
            self.assertFalse(update._asset_matches("Evermem-linux-v0.2.3-portable.tar.gz", PLAT))
        print(f"  PASS  {PLAT} 匹配正确（portable/installer 不串台）")

    # ---------- 清单生成脚本 ----------
    def test_10_manifest_generator(self):
        print("\n十、清单生成脚本（片段 + 汇总）")
        import subprocess
        py = sys.executable
        dist = Path(TMP) / "fake_dist"
        dist.mkdir(exist_ok=True)
        (dist / "Evermem-windows-v1.2.3.exe").write_bytes(b"binary")
        (dist / "SHA256SUMS.txt").write_text("ignored\n", encoding="utf-8")
        frag = Path(TMP) / "frag.json"
        rc = subprocess.run([py, str(ROOT / "scripts" / "gen_update_manifest.py"), "fragment",
                             "--platform", "windows-x64", "--dist", str(dist),
                             "--version", "1.2.3", "--out", str(frag)],
                            capture_output=True, text=True)
        self.assertEqual(rc.returncode, 0, rc.stderr)
        data = json.loads(frag.read_text(encoding="utf-8"))
        self.assertEqual(data["assets"]["windows-x64"]["name"], "Evermem-windows-v1.2.3.exe")
        self.assertIn("github.com", data["assets"]["windows-x64"]["urls"][0])
        print("  PASS  片段生成（排除 SHA256SUMS.txt）")

        frags = Path(TMP) / "frags"
        frags.mkdir(exist_ok=True)
        shutil.copy(frag, frags / "windows.json")
        out = Path(TMP) / "update.json"
        rc = subprocess.run([py, str(ROOT / "scripts" / "gen_update_manifest.py"), "merge",
                             "--fragments", str(frags), "--version", "1.2.3", "--out", str(out),
                             "--changelog", "/nonexistent/CHANGELOG.md", "--mirror", "https://m/"],
                            capture_output=True, text=True)
        self.assertEqual(rc.returncode, 0, rc.stderr)
        man = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(man["channels"]["stable"]["version"], "1.2.3")
        self.assertEqual(man["sources"]["mirrors"], ["https://m/"])
        self.assertIn("windows-x64", man["channels"]["stable"]["assets"])
        print("  PASS  汇总生成（CHANGELOG 缺失不阻断）")

    # ---------- 直连挂了由镜像接管（真实能力，不需要自有托管） ----------
    def test_11_mirror_takes_over(self):
        print("\n十一、直连不可用时镜像接管")
        def fake(url, timeout=None):
            if url.startswith("https://api.github.com"):
                return None, "DNS 解析失败", 3000
            return github_payload(), None, 120
        with mock.patch.object(update, "http_json", side_effect=fake):
            r = update.check(force=True)
            self.assertTrue(r["ok"])
            self.assertEqual(r["source"], "mirror")
            self.assertTrue(any(a["source"] == "mirror" and a["ok"] for a in r["attempts"]))
            self.assertTrue(any(a["source"] == "github" and not a["ok"] for a in r["attempts"]))
            print("  PASS  直连失败不影响拿到版本，来源如实标记为镜像")

    # ---------- 候选地址拼接 ----------
    def test_12_mirror_urls_wellformed(self):
        print("\n十二、镜像候选地址 = 前缀 + 原 URL")
        with mock.patch.object(update, "http_json", return_value=(github_payload(), None, 80)) as m:
            r = update.check(force=True)
            urls = [c.args[0] for c in m.call_args_list]
            self.assertIn(update.GITHUB_API_LATEST, urls)
            for mir in update.DEFAULT_MIRRORS:
                self.assertIn(mir + update.GITHUB_API_LATEST, urls)
            print(f"  PASS  检查 {len(urls)} 个候选：直连 + {len(update.DEFAULT_MIRRORS)} 个镜像")
            # 下载链必须比检查链多一层：只通文件的镜像也要进下载候选
            dl = r["asset"]["urls"]
            self.assertGreater(len(dl), 1)
            self.assertTrue(any("ghproxy.net" in u for u in dl),
                            "ghproxy.net 虽然不能查版本，但能下文件，必须进下载链")
            self.assertTrue(any("gh.llkk.cc" in u for u in dl),
                            "gh.llkk.cc 的 API 被限流但文件正常，同样必须进下载链")
            # 反过来：只通文件的镜像不能混进检查链，否则每次检查都白吃一个 403
            self.assertFalse(any(u for u in urls
                                 if "gh.llkk.cc" in u or "ghproxy.net" in u),
                             "只通文件的镜像不应出现在检查链里")
            print(f"  PASS  下载 {len(dl)} 个候选（含 2 个只通文件的镜像）")

    # ---------- 默认启用官方云清单（2026-10-01 定案：清单不进 Release，云服务器固定文件）----------
    def test_13_cloud_manifest_is_default(self):
        print("\n十三、默认启用官方云服务器固定清单；清单不可用时自动降级")
        self.assertEqual(update.load_config()["manifest_url"],
                         "https://www.linhut.cn/evermem/update-manifest.json",
                         "默认清单 = 云服务器固定地址")
        # 云清单 404 → 自动降级 GitHub 直连 + 镜像，不能静默失败
        def fake_json(url, timeout=None):
            if "linhut.cn" in url:
                return None, "HTTP 404", 90
            return github_payload(), None, 100
        with mock.patch.object(update, "http_json", side_effect=fake_json):
            r = update.check(force=True)
            self.assertTrue(r["ok"], "云清单不可用应降级 GitHub")
            self.assertEqual(r["latest"], "0.9.9")
            self.assertNotEqual(r["source"], "manifest")
        print("  PASS  云清单默认启用，404 自动降级 GitHub/镜像")
        # 云清单与 GitHub 全部不可用时仍必须明确失败
        with mock.patch.object(update, "http_json", return_value=(None, "HTTP 404", 88)):
            r2 = update.check(force=True)
            self.assertFalse(r2["ok"])
            self.assertTrue(any("linhut.cn" in a["url"] for a in r2["attempts"]),
                            "失败明细必须包含云清单这一跳")
        print("  PASS  全部源失败时清单跳有据可查")
        # 只通文件的镜像不能混进检查链（防误加回）
        self.assertNotIn("https://gh.llkk.cc/", update.DEFAULT_MIRRORS)
        self.assertIn("https://gh.llkk.cc/", update.DOWNLOAD_ONLY_MIRRORS)
        print("  PASS  只通文件的镜像留在下载链、不进检查链")

    # ---------- 清单资产按发行形态分组 ----------
    def test_15_manifest_form_groups(self):
        print("\n十五、清单资产按发行形态分组（portable/installer）")
        form = update.install_form()
        other = "installer" if form == "portable" else "portable"
        payload = manifest_payload(with_platform=False)
        payload["channels"]["stable"]["assets"] = {
            update.platform_key(): {
                form: {"name": "Evermem-current", "size": 1, "urls": ["https://x/f"]},
                other: {"name": "Evermem-other", "size": 2, "urls": ["https://y/f"]},
            }
        }
        with mock.patch.object(update, "http_json", return_value=(payload, None, 80)):
            r = update.check(force=True)
        self.assertTrue(r["ok"])
        self.assertEqual(r["asset"]["name"], "Evermem-current", "应命中当前形态资产，不串形态")
        print(f"  PASS  命中当前形态（{form}），不串到 {other}")

    # ---------- 清单只下发镜像列表（不写版本）----------
    def test_14_manifest_mirrors_only(self):
        print("\n十四、清单可只下发镜像列表：版本仍由 GitHub 说了算")
        # 只有 sources、没有 channels：这是"上传一次、长期有效"的用法。
        # 防的是这个失败模式：清单写死版本号，维护者忘了覆盖上传 →
        # 客户端命中清单即返回，永远看不到 GitHub 上的新版本（假最新）。
        manifest = {"schema": 1, "product": "evermem",
                    "generated_at": now_iso(),
                    "sources": {"mirrors": ["https://cdn.gh-proxy.org/"],
                                "download_only_mirrors": ["https://gh.llkk.cc/"]}}
        update.save_config({"manifest_url": MANIFEST_URL})

        def fake_json(url, timeout=None):
            if MANIFEST_URL in url:
                return manifest, None, 120
            return github_payload(), None, 300

        with mock.patch.object(update, "http_json", side_effect=fake_json) as m:
            r = update.check(force=True)
            urls = [c.args[0] for c in m.call_args_list]
        self.assertTrue(r["ok"])
        self.assertEqual(r["latest"], "0.9.9", "版本必须来自 GitHub，不是清单给的")
        self.assertIn(r["source"], ("github", "mirror"))
        self.assertIn("https://cdn.gh-proxy.org/" + update.GITHUB_API_LATEST, urls,
                      "清单下发的镜像必须被采用")
        self.assertTrue(any("gh.llkk.cc" in u for u in r["asset"]["urls"]),
                        "清单下发的下载专用镜像必须进下载链")
        # 清单自身记为未命中，但不算错误——它只干镜像下发这一件事
        man = [a for a in r["attempts"] if a["source"] == "manifest"]
        self.assertTrue(man and man[0]["ok"] is False,
                        "没有版本号的清单不应被当作版本真相源")
        print("  PASS  清单只下发镜像，版本来自 GitHub（不会假最新）")


class UpdateDownloadTest(unittest.TestCase):
    """P2/P3 更新下载与替换（全部离线：只测纯函数与参数校验，不测真实网络）。"""

    def test_safe_filename(self):
        import update
        # 点号是安全字符（.exe/.zip 后缀必须保留），只替换真正危险的字符
        cases = {"../../Evermem.exe": "Evermem.exe", "a/b/c.exe": "c.exe",
                 "Evermem-windows-v0.2.3.exe": "Evermem-windows-v0.2.3.exe",
                 "": "update.bin", "a..b": "a..b", "x\\y.exe": "y.exe",
                 "a b*c?.exe": "a_b_c_.exe"}
        for raw, want in cases.items():
            self.assertEqual(update._safe_filename(raw), want, f"{raw!r} → {want!r}")
        print("  PASS  资产名安全化（防路径穿越，保留点号）")

    def test_url_candidates_order_and_dedup(self):
        import update
        urls = ["https://github.com/a/Evermem.exe", "https://ghproxy.net/g/a/Evermem.exe"]
        cands = update._url_candidates(urls)
        self.assertEqual(cands[0][1], urls[0])            # 直连在前
        self.assertEqual(cands[1][1], urls[1])            # 镜像在后
        self.assertEqual(cands[0][0], "直连")
        self.assertEqual(cands[1][0], "镜像")
        # 去重：重复直连不重复进列表
        cands2 = update._url_candidates([urls[0], urls[0]])
        self.assertEqual(len(cands2), 1)
        print("  PASS  下载候选顺序与去重")

    def test_sha256_of(self):
        import update
        p = Path(TMP) / "sample.bin"
        p.write_bytes(b"evermem-sha256-probe" * 100)
        want = update._sha256_of(p)
        import hashlib
        self.assertEqual(want, hashlib.sha256(b"evermem-sha256-probe" * 100).hexdigest())
        print("  PASS  sha256 计算")

    def test_download_params(self):
        import update
        r = update.download({})                       # 缺 name/urls
        self.assertFalse(r["ok"])
        r2 = update.download({"name": "x.exe", "urls": []})
        self.assertFalse(r2["ok"])
        print("  PASS  下载缺参即报错")

    def test_download_cached_valid(self):
        """已下载且 sha256 匹配 → 不重新下载（幂等）。"""
        import update
        name = "ok.exe"
        payload = b"cached-bytes"
        import hashlib
        dst = update.updates_dir()
        dst.mkdir(parents=True, exist_ok=True)
        (dst / name).write_bytes(payload)
        r = update.download({"name": name, "urls": ["https://x.invalid/ok.exe"],
                             "sha256": hashlib.sha256(payload).hexdigest()})
        self.assertTrue(r["ok"])
        self.assertEqual(r["source"], "本机缓存")
        print("  PASS  本机缓存在校验通过时直接复用")

    def test_apply_requires_frozen_windows(self):
        """源码态（未打包）调用 apply_update 必须明确拒绝并给出指引，不能假装成功。"""
        import update
        r = update.apply_update(str(Path(TMP) / "Evermem.exe"))
        self.assertFalse(r["ok"])
        self.assertIn("仅支持", r["error"])
        print("  PASS  源码态 apply 明确拒绝（防假成功）")


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
