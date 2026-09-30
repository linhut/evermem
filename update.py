#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# update - 多源更新检查（自建清单 → GitHub 直连 → 镜像）
#
# 为什么单独一个模块：
#   更新检查是"网络不可靠"场景，必须能被单独测试、单独降级，不能和 Web 路由搅在一起。
#   策略层参考 DSH-manager 已上线验证的实现（多源候选 + 最快胜出 + 失败明示），
#   实现层按 Python 标准库重写（urllib + 线程竞速，无第三方依赖）。
#
# 三条硬约束：
#   1. 不依赖直连 GitHub：自建清单是首选源，镜像是可切换的兜底。
#   2. 全部源不可用必须明确报错：返回每个源的 URL/耗时/错误，绝不静默返回"已是最新"。
#   3. 只检查不安装：本模块不下载、不替换任何文件（下载与替换属 P2/P3）。

from __future__ import annotations

import json
import os
import platform as _platform
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths as _paths  # noqa: E402

REPO = "linhut/evermem"
GITHUB_API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"

# 自建清单（可选，默认关闭）。
#
# 参考 DSH-manager 的已验证做法：「GitHub 直连 + 镜像代理 + DoH 解析」三件套
# 已经能解决"访问不到 GitHub"，且不需要任何自有服务器 / CDN。
# 自建清单只是额外的可运维层（能远程下发镜像列表、能带 SHA256），
# 但它需要有人托管这个 JSON 文件；没托管位置就不启用，不因此引入任何外部依赖。
# 想用时在配置里填 manifest_url（填了才参与检查），留空即不参与。
DEFAULT_MANIFEST_URL = ""

# 镜像前缀：2026-09-30 实测 + 2026-10-01 复测（curl 真实请求 release 资产与 API）。
# 检查链（API 通）2026-10-01 复测：edgeone.gh-proxy.org 160ms < cdn.gh-proxy.org 354ms
#                                < gh-proxy.com 624ms（均在 200 + application/json）
# gh.llkk.cc 已移出检查链：复测 API 403（响应是 "API rate limit exceeded for <镜像出口IP>"，
#   即镜像共享出口被 GitHub 限流，不是站点挂），但文件通道 206 正常 → 归入下面的下载专用镜像。
# 已淘汰，别加回来：ghfast.top、mirror.ghproxy.com（已挂）、github.moeyy.xyz、
#                   ghps.cc（网页工具不是前缀代理）、hub.gitmirror.com（已挂）、
#                   ghproxy.homeboyc.cn（403 blocked）、gh.con.sh（停用）、gh.ddlc.top（429）
# 镜像存活周期短，这个名单要定期复测（改的时候连注释里的实测日期一起改）。
DEFAULT_MIRRORS = ["https://edgeone.gh-proxy.org/", "https://cdn.gh-proxy.org/",
                   "https://gh-proxy.com/"]

# 只通"文件下载"、不通 API 的镜像：版本检查用它没用，但下载可以用——下载链比检查链多一层。
# 2026-10-01 复测两者 Release 文件均 206 + magic bytes 正确（exe 的 MZ）：
#   ghproxy.net：API 403 Invalid input（一贯如此），文件 1.24s
#   gh.llkk.cc：API 403 限流，文件 998ms
DOWNLOAD_ONLY_MIRRORS = ["https://ghproxy.net/", "https://gh.llkk.cc/"]
# 清单不在默认源里：只有用户填了 manifest_url（自己托管）时才自动加入
DEFAULT_SOURCES = ["github", "mirror"]

CONFIG_NAME = "update.json"
STATE_NAME = "update_state.json"
CACHE_TTL_SECONDS = 24 * 3600

# 单源超时：宁可快失败换源，也不要吊住整个检查
SOURCE_TIMEOUT = 8.0

ALLOWED_CONFIG_KEYS = ("channel", "auto_check", "manifest_url", "sources", "mirrors")

DEFAULT_CONFIG = {
    "channel": "stable",
    "auto_check": True,
    "manifest_url": DEFAULT_MANIFEST_URL,
    "sources": list(DEFAULT_SOURCES),
    "mirrors": list(DEFAULT_MIRRORS),
}


# ---------- 版本 ----------
def current_version() -> str:
    """当前版本：读代码目录的 VERSION 文件（打包后随资源一起分发）。"""
    try:
        return (_paths.code_root() / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def parse_semver(v: str):
    """把版本号拆成可比较元组：主.次.修订 + 预发布位次。

    预发布（0.2.4-rc.1）必须小于对应正式版（0.2.4），
    所以正式版的预发布段取更大位次。
    """
    s = str(v or "").strip().lstrip("vV")
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:[-.]([A-Za-z]+)[.]?(\d*))?", s)
    if not m:
        nums = re.findall(r"\d+", s)
        while len(nums) < 3:
            nums.append("0")
        return (int(nums[0]), int(nums[1]), int(nums[2]), 1, 0)
    pre_tag = (m.group(4) or "").lower()
    pre_num = int(m.group(5) or 0)
    rank = 1 if not pre_tag else 0
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), rank, pre_num)


def compare_semver(a: str, b: str) -> int:
    """a>b 返回正数，a<b 返回负数，相等返回 0。"""
    ta, tb = parse_semver(a), parse_semver(b)
    return (ta > tb) - (ta < tb)


# ---------- 平台 ----------
def platform_key() -> str:
    """当前平台资产键：windows-x64 / macos-arm64 / macos-x64 / linux-x64。"""
    sysname = sys.platform
    if sysname.startswith("win"):
        base = "windows"
    elif sysname == "darwin":
        base = "macos"
    else:
        base = "linux"
    machine = (_platform.machine() or "").lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else (
        "x64" if machine in ("x86_64", "amd64", "x64") else (machine or "x64"))
    return f"{base}-{arch}"


def _asset_matches(name: str, key: str) -> bool:
    """判定 GitHub Release 资产是否属于当前平台（名字里带平台关键字）。"""
    n = str(name or "").lower()
    base = key.split("-")[0]
    if base == "windows":
        return "windows" in n and n.endswith(".exe")
    if base == "macos":
        return "macos" in n and (n.endswith(".app.zip") or n.endswith(".zip"))
    return "linux" in n and not n.endswith((".exe", ".zip"))


# ---------- 配置与状态 ----------
def config_file() -> Path:
    return _paths.data_root() / CONFIG_NAME


def state_file() -> Path:
    return _paths.data_root() / STATE_NAME


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        data = json.loads(config_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if isinstance(data, dict):
        for k in ALLOWED_CONFIG_KEYS:
            if k in data:
                cfg[k] = data[k]
    if not isinstance(cfg.get("sources"), list) or not cfg["sources"]:
        cfg["sources"] = list(DEFAULT_SOURCES)
    if not isinstance(cfg.get("mirrors"), list):
        cfg["mirrors"] = list(DEFAULT_MIRRORS)
    # 清单参与与否只看一件事：有没有填地址（填了就说明用户自己托管了）
    if not isinstance(cfg.get("manifest_url"), str):
        cfg["manifest_url"] = DEFAULT_MANIFEST_URL
    cfg["manifest_url"] = cfg["manifest_url"].strip()
    return cfg


def save_config(patch: dict) -> dict:
    """合并写入配置并回读真实值（写失败要能被调用方看到）。"""
    cfg = load_config()
    for k in ALLOWED_CONFIG_KEYS:
        if k in patch:
            cfg[k] = patch[k]
    p = config_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return load_config()


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


# ---------- 网络 ----------
def _ua() -> str:
    return f"Evermem/{current_version()}"


def _err_text(exc: Exception) -> str:
    msg = str(exc) or exc.__class__.__name__
    low = msg.lower()
    if "timed out" in low or "timeout" in low:
        return "超时"
    if "getaddrinfo" in low or "name or service not known" in low or "11001" in msg:
        return "DNS 解析失败"
    if "certificate" in low or "ssl" in low:
        return "TLS 校验失败"
    return msg[:120]


def http_json(url: str, timeout: float = SOURCE_TIMEOUT):
    """取 JSON：返回 (data, error, elapsed_ms)。4xx/5xx 都算失败并带状态码。"""
    started = time.time()
    req = urllib.request.Request(
        url, headers={"User-Agent": _ua(), "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
        return json.loads(raw), None, int((time.time() - started) * 1000)
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}", int((time.time() - started) * 1000)
    except Exception as exc:  # noqa: BLE001 - 超时/DNS/SSL 都要变成可读错误
        return None, _err_text(exc), int((time.time() - started) * 1000)


def http_text(url: str, timeout: float = SOURCE_TIMEOUT):
    started = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": _ua()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace"), None, int((time.time() - started) * 1000)
    except Exception as exc:  # noqa: BLE001
        return None, _err_text(exc), int((time.time() - started) * 1000)


# ---------- 各源解析 ----------
def _normalize_asset(raw: dict, fallback_name: str = "") -> dict:
    urls = [u for u in (raw.get("urls") or []) if isinstance(u, str) and u.strip()]
    if not urls and raw.get("url"):
        urls = [raw["url"]]
    return {"name": raw.get("name") or fallback_name,
            "size": raw.get("size"),
            "sha256": raw.get("sha256") or None,
            "urls": urls}


def _with_mirrors(urls: list, mirrors: list) -> list:
    """把镜像前缀拼到直链后面作为候选（直链仍排在最前）。"""
    out = [u for u in urls if u]
    for m in mirrors or []:
        prefix = m if m.endswith("/") else m + "/"
        for u in list(urls):
            if u and not u.startswith(prefix):
                cand = prefix + u
                if cand not in out:
                    out.append(cand)
    return out


def from_manifest(cfg: dict, url: str = ""):
    """自建清单源（可选：只有用户自己托管了清单文件才用得上）。"""
    url = url or (cfg.get("manifest_url") or "").strip()
    if not url:
        # 没托管清单是正常状态（DSH 那套直连+镜像+DoH 不需要它），如实记为"未配置"
        return None, {"source": "manifest", "url": "", "ok": False, "elapsed_ms": 0,
                      "error": "未配置清单地址（可选源，默认不启用）"}
    data, err, ms = http_json(url)
    attempt = {"source": "manifest", "url": url, "ok": False, "elapsed_ms": ms, "error": err}
    if err or not isinstance(data, dict):
        return None, attempt

    # 镜像下发：这一层与"版本号"无关，先取出来——清单可以只干这一件事。
    # 之所以允许"只下发镜像"：清单一旦写死版本，忘了覆盖上传就会让用户永远看到"已是最新"，
    # 而镜像列表是低频变更、上传一次即可长期有效的信息，两者必须能分开用。
    src = data.get("sources") if isinstance(data.get("sources"), dict) else {}
    mirrors = [m for m in (src.get("mirrors") or []) if isinstance(m, str)]
    dl_only = [m for m in (src.get("download_only_mirrors") or []) if isinstance(m, str)]
    attempt["mirrors"] = mirrors
    attempt["download_only_mirrors"] = dl_only

    channels = data.get("channels") or {}
    ch = channels.get(cfg.get("channel") or "stable")
    if not isinstance(ch, dict):
        attempt["error"] = f"清单无 channel={cfg.get('channel')}（只用于下发镜像列表时属正常）"
        return None, attempt
    version = str(ch.get("version") or "").strip()
    if not version:
        attempt["error"] = "清单未指定版本（只用于下发镜像列表时属正常）"
        return None, attempt
    assets = ch.get("assets") or {}
    key = platform_key()
    raw = assets.get(key) or assets.get(key.split("-")[0])
    if not isinstance(raw, dict):
        attempt["error"] = f"清单无当前平台资产（{key}），仅采用其镜像列表"
        return None, attempt

    eff_mirrors = mirrors or list(cfg.get("mirrors") or [])
    asset = _normalize_asset(raw)
    asset["urls"] = _with_mirrors(asset["urls"],
                                  eff_mirrors + (dl_only or list(DOWNLOAD_ONLY_MIRRORS)))
    attempt["ok"] = True
    attempt["error"] = None
    return {"latest": version,
            "notes": str(ch.get("notes") or "").strip(),
            "published_at": ch.get("published_at") or "",
            "generated_at": ch.get("generated_at") or data.get("generated_at") or "",
            "asset": asset,
            "mirrors": mirrors,
            "source": "manifest"}, attempt


def from_github(cfg: dict, url: str = GITHUB_API_LATEST, mirror: str = ""):
    """GitHub Release 源（直连或经镜像前缀）。"""
    data, err, ms = http_json(url)
    label = "mirror" if mirror else "github"
    attempt = {"source": label, "url": url, "ok": False, "elapsed_ms": ms, "error": err}
    if err or not isinstance(data, dict):
        return None, attempt

    tag = str(data.get("tag_name") or "").strip()
    version = tag.lstrip("vV")
    if not version:
        attempt["error"] = "响应无 tag_name"
        return None, attempt

    assets = [a for a in (data.get("assets") or []) if isinstance(a, dict)]
    key = platform_key()
    hit = None
    for a in assets:
        if _asset_matches(str(a.get("name") or ""), key):
            hit = a
            break
    if hit is None:
        attempt["error"] = f"Release 无当前平台资产（{key}）"
        return None, attempt

    dl = str(hit.get("browser_download_url") or "").strip()
    if not dl:
        attempt["error"] = "资产缺少下载链接"
        return None, attempt

    # 下载链比检查链多一层：加上只通文件的镜像
    dl_mirrors = list(cfg.get("mirrors") or []) + list(
        cfg.get("download_only_mirrors") or DOWNLOAD_ONLY_MIRRORS)
    asset = {"name": hit.get("name"), "size": hit.get("size"),
             "sha256": _sha256_from_release(assets, str(hit.get("name") or "")),
             "urls": _with_mirrors([dl], dl_mirrors)}
    attempt["ok"] = True
    attempt["error"] = None
    return {"latest": version,
            "notes": str(data.get("body") or "").strip()[:2000],
            "published_at": data.get("published_at") or "",
            "generated_at": data.get("published_at") or "",
            "asset": asset,
            "mirrors": list(cfg.get("mirrors") or []),
            "source": label}, attempt


def _sha256_from_release(assets: list, asset_name: str):
    """从 Release 的 SHA256SUMS.txt 取校验值；拿不到返回 None（不阻塞检查）。"""
    sums = None
    for a in assets:
        if str(a.get("name") or "").strip() == "SHA256SUMS.txt":
            sums = str(a.get("browser_download_url") or "").strip()
            break
    if not sums or not asset_name:
        return None
    text, err, _ = http_text(sums, timeout=6.0)
    if err:
        return None
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].endswith(asset_name):
            return parts[0]
    return None


# ---------- 主流程 ----------
def check(force: bool = False, timeout: float = SOURCE_TIMEOUT) -> dict:
    """多源更新检查。

    默认：GitHub 直连 + 镜像前缀并行竞速，取最快成功者（即 DSH-manager 已验证的做法，
    不需要任何自有服务器 / CDN）。
    可选：用户自己托管了清单文件（manifest_url 非空）时，清单先试，失败再走上面那条。
    全部失败返回 ok=False + attempts（每个源的错误），调用方必须据此明确提示。
    """
    cfg = load_config()
    current = current_version()
    base = {"ok": False, "current": current, "channel": cfg.get("channel"),
            "manual_url": RELEASES_PAGE, "platform": platform_key()}

    # 只缓存成功结果：失败缓存会让用户没法重试
    if not force:
        state = _read_json(state_file())
        last = state.get("last_ok") if isinstance(state.get("last_ok"), dict) else None
        if last and time.time() - float(state.get("last_check_at") or 0) < CACHE_TTL_SECONDS:
            out = dict(base)
            out.update(last)
            out["ok"] = True
            out["cached"] = True
            return out

    attempts: list[dict] = []
    sources = list(cfg.get("sources") or DEFAULT_SOURCES)

    # 可选的第一跳：自建清单（填了 manifest_url 才存在，命中即返回）
    if cfg.get("manifest_url"):
        manifest_res, attempt = from_manifest(cfg)
        if attempt:
            attempts.append(attempt)
            # 清单可以只下发镜像列表而不写版本号：版本仍交给 GitHub/镜像竞速去问。
            # 这样清单上传一次就长期有效，不会出现"清单忘了更新 = 永远显示已是最新"。
            if attempt.get("mirrors"):
                cfg["mirrors"] = list(attempt["mirrors"])
            if attempt.get("download_only_mirrors"):
                cfg["download_only_mirrors"] = list(attempt["download_only_mirrors"])
        if manifest_res:
            return _finish(base, manifest_res, attempts)

    # 第二跳：GitHub 直连与镜像并行竞速，取最快成功者
    tasks = []
    if "github" in sources:
        tasks.append(("github", GITHUB_API_LATEST, ""))
    if "mirror" in sources:
        for m in cfg.get("mirrors") or []:
            prefix = m if m.endswith("/") else m + "/"
            tasks.append(("mirror", prefix + GITHUB_API_LATEST, m))

    if tasks:
        remote_res = _race_github(cfg, tasks, attempts)
        if remote_res:
            return _finish(base, remote_res, attempts)

    out = dict(base)
    out.update({"ok": False, "latest": None, "has_update": False,
                "error": "全部更新源不可用", "attempts": attempts, "cached": False})
    return out


def _race_github(cfg: dict, tasks: list, attempts: list):
    """GitHub 直连与镜像并行竞速：取最快成功者。"""
    with ThreadPoolExecutor(max_workers=max(1, len(tasks))) as pool:
        futures = {pool.submit(from_github, cfg, url, mirror): (label, url, mirror)
                   for label, url, mirror in tasks}
        collected = {t[1]: (None, None) for t in tasks}
        for fut in as_completed(futures):
            res, att = fut.result()
            collected[futures[fut][1]] = (res, att)
    best = None
    for _label, url, _m in tasks:
        res, att = collected[url]
        if att:
            attempts.append(att)
        if res and best is None:
            best = res
    return best


def _finish(base: dict, result: dict, attempts: list) -> dict:
    current = base["current"]
    latest = result["latest"]
    has_update = compare_semver(latest, current) > 0 if current not in ("", "unknown") else False
    out = dict(base)
    out.update({"ok": True, "latest": latest, "has_update": has_update,
                "notes": result.get("notes", ""), "published_at": result.get("published_at", ""),
                "asset": result.get("asset"), "mirrors": result.get("mirrors", []),
                "attempts": attempts, "cached": False,
                # 结果实际来自哪个源：诊断信息，界面可据实提示
                "source": result.get("source", "github")})
    try:
        state_file().parent.mkdir(parents=True, exist_ok=True)
        state_file().write_text(json.dumps(
            {"last_check_at": time.time(),
             "last_ok": {k: v for k, v in out.items() if k != "cached"}},
            ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return out


def sources_info() -> dict:
    """供 UI 展示与编辑的源配置（含默认值）。"""
    return {"config": load_config(), "defaults": dict(DEFAULT_CONFIG),
            "download_only_mirrors": list(DOWNLOAD_ONLY_MIRRORS),
            "github_api": GITHUB_API_LATEST, "releases_page": RELEASES_PAGE,
            "platform": platform_key(), "current": current_version()}


if __name__ == "__main__":
    print(json.dumps(check(force=True), ensure_ascii=False, indent=2))
