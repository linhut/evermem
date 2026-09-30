#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# pmem backup v3 - 恒忆多渠道数据备份（零依赖 + 可选 ssh/scp、smtplib）
#
#
# 规格见 docs/BACKUP-DESIGN.md。要点：
#   - 本地数据 = 唯一事实源，所有渠道为副本，方向默认 upload（单向，无跨渠道冲突）
#   - 渠道：local(增量镜像) / archive(全量快照保留N份) / remote(ssh/scp 增量镜像) / mail(SMTP 附件)
#   - 每渠道独立频率、失败记录、连续失败告警（邮件可选）
#   - 数据与代码分离：数据只经本系统进出，不进 Git/GitHub
#
# 配置 pmem_backup.json：
#   {"auto": true, "alert_email": "me@x.com", "channels": [
#      {"type":"local","name":"本地网盘","enabled":true,"target":"<网盘同步目录>/evermem-backup",
#       "scope":["notes","events","index","meta"],"frequency_hours":24},
#      {"type":"archive","name":"本机快照","enabled":true,"target":"<快照目录>","retention":7},
#      {"type":"remote","name":"服务器","enabled":false,"target":"user@host:/backup/evermem","ssh_port":22},
#      {"type":"mail","name":"邮箱","enabled":false,"target":"bk@x.com",
#       "smtp":{"host":"smtp.x.com","port":465,"user":"me@x.com","pass":"***"}}]}
# 旧格式 {target,note,scope,auto,interval_hours} 自动迁移为单 local 渠道。
#
# 用法：status / --dry-run / [--channel name] / --restore [--channel name] / [--scope n,e]

from __future__ import annotations

import io
import hashlib
import json
import os
import shutil
import smtplib
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import sys as _sys
if str(Path(__file__).resolve().parent) not in _sys.path:
    _sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths as _paths  # noqa: E402

# 数据根目录：备份/恢复读写的是用户数据，必须走唯一解析入口
# （env > 持久化配置 > 可移植默认），否则打包后会备份/恢复到临时解包目录。
BASE = _paths.data_root()
# 代码根目录：只用于定位 openssl、快照打包等随程序分发的资源。
CODE_ROOT = _paths.code_root()
CONFIG_FILE = BASE / "pmem_backup.json"
MANIFEST = ".pmem-backup-last.json"
LOG_FILE = "backup.log"
AUTO_CHECK_SECONDS = 300
CHANNEL_TYPES = ("local", "archive", "remote", "mail", "s3", "baidu-pan")

SCOPE_GROUPS = {
    "notes": ["notes"],
    "events": ["events"],
    "index": ["index.json"],
    "meta": ["harvest_state.json", "corpus_spaces.json", "kb.json", "knowledge-base.md",
            "pmem_config.json", "update.json", "update_state.json"],
    # 块库：路径取自 pmem_config.json 的 chunks 字段（可能不在数据根，data_items 单独解析）
    "chunks": ["chunks"],
}
ALL_SCOPES = list(SCOPE_GROUPS)

# ---------------- 配置 ----------------

def _atomic_write(path: Path, text: str, encoding: str = "utf-8") -> None:
    """原子写：tmp + os.replace，避免并发/中断留下截断 JSON。"""
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    try:
        tmp.write_text(text, encoding=encoding)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def load_cfg() -> dict:
    cfg = {}
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    if not isinstance(cfg, dict):
        cfg = {}
    auto = bool(cfg.get("auto", False))
    alert = str(cfg.get("alert_email") or "").strip()
    channels = cfg.get("channels")
    if not isinstance(channels, list):
        # 旧格式迁移：顶层 target/note/scope/interval_hours → 单 local 渠道
        target = str(cfg.get("target") or os.environ.get("PMEM_BACKUP_TARGET") or "").strip()
        if target:
            scope = [s for s in (cfg.get("scope") or ALL_SCOPES) if s in SCOPE_GROUPS] or list(ALL_SCOPES)
            try:
                freq = max(1, int(cfg.get("interval_hours", 24)))
            except (TypeError, ValueError):
                freq = 24
            channels = [{"type": "local", "name": "主备份", "enabled": True, "target": target,
                         "scope": scope, "frequency_hours": freq, "note": str(cfg.get("note") or "")}]
        else:
            channels = []
    out = []
    for i, c in enumerate(channels):
        if not isinstance(c, dict) or c.get("type") not in CHANNEL_TYPES:
            continue
        scope = [s for s in (c.get("scope") or ALL_SCOPES) if s in SCOPE_GROUPS] or list(ALL_SCOPES)
        try:
            freq = max(1, int(c.get("frequency_hours", 24)))
        except (TypeError, ValueError):
            freq = 24
        out.append({
            "type": c["type"], "name": str(c.get("name") or f"{c['type']}-{i}"),
            "enabled": bool(c.get("enabled", True)), "target": str(c.get("target") or "").strip(),
            "scope": scope, "frequency_hours": freq,
            "note": str(c.get("note") or ""), "retention": int(c.get("retention", 7) or 7),
            "ssh_port": int(c.get("ssh_port", 22) or 22),
            "smtp": c.get("smtp") if isinstance(c.get("smtp"), dict) else {},
            # s3：对象存储渠道（SigV4 零依赖直传，凭证本机混淆存储）
            "endpoint": str(c.get("endpoint") or "").strip(),
            "region": str(c.get("region") or "us-east-1").strip(),
            "bucket": str(c.get("bucket") or "").strip(),
            "prefix": str(c.get("prefix") or "").strip(),
            "access_key": str(c.get("access_key") or "").strip(),
            "secret_key": str(c.get("secret_key") or "").strip(),
            # 归档加密统一字段（s3 / baidu-pan 共用，丢失=数据不可解）
            "archive_password": str(c.get("archive_password") or "").strip(),
        })
    return {"auto": auto, "alert_email": alert, "channels": out}

def save_cfg(cfg: dict) -> None:
    _atomic_write(CONFIG_FILE, json.dumps(cfg, ensure_ascii=False, indent=1))

# ---------------- 数据收集与校验 ----------------

def scope_paths(scope: list[str] | None = None) -> list[str]:
    out = []
    for s in (scope or ALL_SCOPES):
        out += SCOPE_GROUPS.get(s, [])
    return out

def _resolve_scope(name: str) -> Path | None:
    """scope 条目 → 真实路径：chunks 读 pmem_config.json 的 chunks 字段；其余支持绝对路径。"""
    if name == "chunks":
        try:
            c = str(_paths.load_config().get("chunks") or "").strip()
            return Path(c).expanduser() if c else None
        except (OSError, ValueError):
            return None
    p = Path(name)
    return p if p.is_absolute() else BASE / p


def data_items(scope: list[str] | None = None) -> list[dict]:
    items = []
    for name in scope_paths(scope):
        p = _resolve_scope(name)
        if p and p.exists():
            collect(p, name, items)
    return items

def collect(src: Path, rel: str, items: list[dict]) -> None:
    if src.is_file():
        st = src.stat()
        items.append({"rel": rel, "mtime": st.st_mtime, "size": st.st_size})
    else:
        for f in sorted(src.rglob("*")):
            if (f.is_file() and not f.name.startswith(".pmem-")
                    and not f.name.startswith("evermem-")
                    and not f.name.endswith(".tar.aes")
                    and not f.name.endswith(".sha256")
                    and f.name != "UPLOAD.md"):
                st = f.stat()
                items.append({"rel": str(Path(rel) / f.relative_to(src)), "mtime": st.st_mtime, "size": st.st_size})

def total_size(items: list[dict]) -> int:
    return sum(i["size"] for i in items)

def verify_target(root: Path, items: list[dict]) -> dict:
    missing, total = 0, 0
    for i in items:
        p = root / i["rel"]
        if not p.exists():
            missing += 1
            continue
        try:
            total += p.stat().st_size
        except OSError:
            missing += 1
    expected = total_size(items)
    ok = missing == 0 and (expected == 0 or abs(total - expected) <= max(64, expected * 0.01))
    return {"ok": ok, "files": len(items), "missing": missing, "bytes": total, "expected_bytes": expected}

# ---------------- 渠道状态（本地清单） ----------------

def _manifest() -> dict:
    try:
        return json.loads((BASE / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

def channel_state(name: str) -> dict:
    st = _manifest().get("channels", {}).get(name, {})
    return st if isinstance(st, dict) else {}

def mark_channel(name: str, ok: bool, error: str = "", verified=None, extra: dict | None = None) -> None:
    m = _manifest()
    st = m.setdefault("channels", {}).setdefault(name, {})
    st["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    st["ok"] = bool(ok)
    st["fail_count"] = 0 if ok else int(st.get("fail_count", 0)) + 1
    if ok:
        st["last_error"] = ""
    else:
        st["last_error"] = error[:300]
    if verified is not None:
        st["verified"] = bool(verified)
    if extra:
        st.update(extra)
    history = m.setdefault("history", [])
    history.insert(0, {"at": st["at"], "channel": name, "ok": bool(ok),
                       "files": (extra or {}).get("files", 0),
                       "synced": (extra or {}).get("synced", 0),
                       "verified": verified})
    m["history"] = history[:20]
    _atomic_write(BASE / MANIFEST, json.dumps(m, ensure_ascii=False, indent=1))

def log_line(text: str) -> None:
    try:
        with open(BASE / LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {text}\n")
    except OSError:
        pass

# ---------------- 渠道适配器 ----------------

def _due(name: str, ch: dict) -> bool:
    st = channel_state(name)
    if not st.get("at"):
        return True
    try:
        last_ts = time.mktime(time.strptime(st["at"][:19], "%Y-%m-%d %H:%M:%S"))
    except (ValueError, TypeError):
        return True
    return (time.time() - last_ts) >= ch["frequency_hours"] * 3600

def run_local(ch: dict) -> dict:
    """增量镜像到本机可写目录（网盘挂载/NAS）。"""
    dst = Path(ch["target"])
    dst.mkdir(parents=True, exist_ok=True)
    if not dst.is_dir() or not os.access(dst.parent, os.W_OK):
        raise RuntimeError(f"目标不可写：{ch['target']}")
    items = data_items(ch["scope"])
    state_p = dst / ".pmem-state.json"
    last_map = {}
    try:
        last_map = {i["rel"]: i for i in json.loads(state_p.read_text(encoding="utf-8")).get("items", [])}
    except (OSError, json.JSONDecodeError):
        pass
    synced = skipped = 0
    for i in items:
        old = last_map.get(i["rel"])
        d = dst / i["rel"]
        if old and old["mtime"] == i["mtime"] and old["size"] == i["size"] and d.exists():
            skipped += 1
            continue
        s = BASE / i["rel"]
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
        synced += 1
    _atomic_write(state_p, json.dumps({"items": items}, ensure_ascii=False))
    ver = verify_target(dst, items)
    return {"synced": synced, "skipped": skipped, "files": len(items), "verified": ver["ok"],
            "missing": ver["missing"]}

def run_archive(ch: dict) -> dict:
    """全量快照 zip 到归档目录，保留最近 retention 份。"""
    dst = Path(ch["target"])
    dst.mkdir(parents=True, exist_ok=True)
    if not dst.is_dir() or not os.access(dst.parent, os.W_OK):
        raise RuntimeError(f"归档目录不可写：{ch['target']}")
    snap_dir = dst / "snapshots"
    snap_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    zpath = snap_dir / f"evermem-{stamp}.zip"
    items = data_items(ch["scope"])
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for i in items:
            z.write(BASE / i["rel"], i["rel"])
    size = zpath.stat().st_size
    snaps = sorted(snap_dir.glob("evermem-*.zip"))
    removed = []
    for old in snaps[:-max(1, int(ch["retention"]))]:
        old.unlink()
        removed.append(old.name)
    return {"synced": len(items), "files": len(items), "bytes": size, "snapshot": zpath.name,
            "retention": len(snaps) - len(removed), "removed": removed, "verified": True}

def _read_state(remote_state: str) -> dict:
    try:
        return json.loads(remote_state) if remote_state else {}
    except json.JSONDecodeError:
        return {}

def run_remote(ch: dict) -> dict:
    """增量镜像到 ssh/scp 可达的异地服务器。"""
    target = ch["target"]
    if "@" not in target or ":" not in target:
        raise RuntimeError(f"remote 目标格式应为 user@host:path：{target}")
    user_host, remote_dir = target.rsplit(":", 1)
    port = ch["ssh_port"]
    base = f"{user_host}:{remote_dir.rstrip('/')}"
    items = data_items(ch["scope"])
    tmp_state = BASE / ".pmem-remote-state.tmp"
    remote_state = ""
    try:
        r = subprocess.run(["scp", "-P", str(port), "-q", f"{base}/.pmem-state.json", str(tmp_state)],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and tmp_state.exists():
            remote_state = tmp_state.read_text(encoding="utf-8")
        tmp_state.unlink(missing_ok=True)
    except (OSError, subprocess.SubprocessError):
        pass
    last_map = {i["rel"]: i for i in _read_state(remote_state).get("items", [])}
    changed = [i for i in items
               if not (last_map.get(i["rel"]) and last_map[i["rel"]]["mtime"] == i["mtime"]
                       and last_map[i["rel"]]["size"] == i["size"])]
    synced = 0
    for i in changed:
        r = subprocess.run(["scp", "-P", str(port), "-q", str(BASE / i["rel"]), f"{base}/{i['rel']}"],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"scp 失败：{i['rel']} {r.stderr[:150]}")
        synced += 1
    _atomic_write(tmp_state, json.dumps({"items": items}, ensure_ascii=False))
    subprocess.run(["scp", "-P", str(port), "-q", str(tmp_state), f"{base}/.pmem-state.json"],
                   capture_output=True, text=True, timeout=30)
    tmp_state.unlink(missing_ok=True)
    return {"synced": synced, "skipped": len(items) - synced, "files": len(items),
            "verified": None, "host": user_host}

def run_mail(ch: dict) -> dict:
    """全量打包 zip 经 SMTP 发送附件到目标邮箱。"""
    smtp = ch.get("smtp") or {}
    host, port = smtp.get("host", ""), int(smtp.get("port", 465) or 465)
    user = smtp.get("user", "")
    passwd = deobscure(smtp.get("pass") or "") or os.environ.get("PMEM_SMTP_PASS", "")
    to = ch["target"]
    if not host or not user or not passwd or not to:
        raise RuntimeError("mail 渠道需 smtp.host/user/pass（或 PMEM_SMTP_PASS）与 target 收件人")
    items = data_items(ch["scope"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i in items:
            z.write(BASE / i["rel"], i["rel"])
    payload = buf.getvalue()
    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = f"恒忆备份 {time.strftime('%Y-%m-%d %H:%M')}"
    msg.attach(MIMEText(f"恒忆数据备份，{len(items)} 个文件，{len(payload)/1048576:.2f} MB。", "plain", "utf-8"))
    att = MIMEApplication(payload, _subtype="zip")
    att.add_header("Content-Disposition", "attachment",
                   filename=f"evermem-backup-{time.strftime('%Y%m%d-%H%M%S')}.zip")
    msg.attach(att)
    server = smtplib.SMTP_SSL(host, port) if port == 465 else smtplib.SMTP(host, port)
    try:
        if port != 465:
            server.starttls()
        server.login(user, passwd)
        server.sendmail(user, [to], msg.as_string())
    finally:
        server.quit()
    return {"synced": len(items), "files": len(items), "bytes": len(payload), "to": to, "verified": True}

# ---------------- 加密归档包（s3 / baidu-pan 共用） ----------------

def _openssl_path() -> str:
    """定位 openssl：优先 PMEM_OPENSSL 环境变量，其次 PATH，最后 Git 常见安装位置（用 env 构造，不写死用户）。"""
    exe = os.environ.get("PMEM_OPENSSL", "").strip()
    if exe and Path(exe).exists():
        return exe
    found = shutil.which("openssl")
    if found:
        return found
    local_appdata = Path(os.environ.get("LOCALAPPDATA", "") or "C:/")
    for cand in ("C:/Program Files/Git/usr/bin/openssl.exe",
                 "C:/Program Files (x86)/Git/usr/bin/openssl.exe",
                 "C:/Program Files/Git/bin/openssl.exe",
                 str(local_appdata / "Programs" / "Git" / "usr" / "bin" / "openssl.exe")):
        if Path(cand).exists():
            return cand
    raise RuntimeError("未找到 openssl（Git for Windows 自带）。可设置 PMEM_OPENSSL 指定路径。")

def _archive_password(ch: dict) -> str:
    pw = deobscure(ch.get("archive_password") or "") or os.environ.get("PMEM_ARCHIVE_PASS", "")
    if not pw:
        raise RuntimeError("归档加密需要密码：渠道字段 archive_password 或环境变量 PMEM_ARCHIVE_PASS（≥16 位，丢失将无法解密）")
    return pw

def make_archive_package(ch: dict, items: list[dict], out_dir: Path | None = None) -> dict:
    """tar 打包 → openssl AES-256-CBC 加密 → sha256 校验，产出 .tar.aes + .sha256。

    加密在出本机前完成：云端/网盘永远只有密文。密码不落盘（除配置混淆字段/环境变量）。
    """
    pw = _archive_password(ch)
    out_dir = out_dir or Path(tempfile.mkdtemp(prefix="pmem-arch-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    plain_tar = out_dir / f".pmem-tmp-{stamp}.tar"
    enc = out_dir / f"evermem-{stamp}.tar.aes"
    try:
        with tarfile.open(plain_tar, "w") as t:
            for i in items:
                src = BASE / i["rel"]
                if src.exists():
                    t.add(src, arcname=i["rel"])
        openssl = _openssl_path()
        r = subprocess.run([openssl, "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt",
                            "-in", str(plain_tar), "-out", str(enc), "-pass", f"pass:{pw}"],
                           capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            raise RuntimeError(f"openssl 加密失败：{(r.stderr or '')[:200]}")
        sha = hashlib.sha256(enc.read_bytes()).hexdigest()
        _atomic_write(out_dir / f"{enc.name}.sha256", f"{sha}  {enc.name}\n")
        return {"package": enc.name, "bytes": enc.stat().st_size, "sha256": sha, "stamp": stamp}
    finally:
        plain_tar.unlink(missing_ok=True)

def _retain_encrypted(dirpath: Path, keep: int) -> list[str]:
    """按文件名时间戳保留最近 keep 个 .tar.aes（用于冷备目录与本地暂存清理）。"""
    removed = []
    for old in sorted(dirpath.glob("evermem-*.tar.aes"))[:-max(1, keep)]:
        old.unlink()
        removed.append(old.name)
    return removed

def run_s3(ch: dict) -> dict:
    """对象存储渠道：加密归档包直传 S3 兼容存储（OSS/COS/S3/MinIO/BOS），零依赖 SigV4。"""
    if not (ch.get("endpoint") and ch.get("access_key") and ch.get("secret_key") and ch.get("bucket")):
        raise RuntimeError("s3 渠道需 endpoint/AK/SK/bucket")
    from s3client import S3Client
    client = S3Client(ch["endpoint"], ch["access_key"], ch["secret_key"],
                      ch.get("region") or "us-east-1", ch["bucket"], ch.get("prefix") or "")
    items = data_items(ch["scope"])
    pkg = make_archive_package(ch, items)
    pkg_bytes = (BASE / pkg["package"]).read_bytes()
    day = pkg["stamp"][:8]
    client.put_object(f"{day}/{pkg['package']}", pkg_bytes)
    client.put_object(f"{day}/{pkg['package']}.sha256",
                      (BASE / f"{pkg['package']}.sha256").read_bytes())
    # 保留策略：清理云端旧包（保留 retention 份）
    all_keys = [k for k in client.list_objects() if k.endswith(".tar.aes")]
    removed = []
    for old in sorted(all_keys)[:-max(1, int(ch.get("retention", 30) or 30))]:
        client.delete_object(old, raw=True)  # list_objects 的 key 已含 prefix
        removed.append(old.split("/")[-1])
    (BASE / pkg["package"]).unlink(missing_ok=True)
    (BASE / f"{pkg['package']}.sha256").unlink(missing_ok=True)
    return {"synced": len(items), "files": len(items), "bytes": pkg["bytes"],
            "sha256": pkg["sha256"], "bucket": ch["bucket"],
            "key": f"{day}/{pkg['package']}", "verified": True, "removed": removed}

def run_baidu_pan(ch: dict) -> dict:
    """百度网盘冷备渠道（二等公民）：生成加密归档包 + 上传清单，需人工拖入网盘。不伪装成自动。"""
    out_dir = Path(ch.get("target") or "")
    if not str(out_dir).strip():
        raise RuntimeError("baidu-pan 需指定归档包生成目录（target）")
    out_dir.mkdir(parents=True, exist_ok=True)
    items = data_items(ch["scope"])
    pkg = make_archive_package(ch, items, out_dir)
    removed = _retain_encrypted(out_dir, int(ch.get("retention", 12) or 12))
    up = out_dir / "UPLOAD.md"
    up.write_text(
        "# 恒忆冷备份 · 手动上传清单\n\n"
        f"生成时间：{time.strftime('%Y-%m-%d %H:%M')}\n"
        f"加密方式：AES-256-CBC (openssl pbkdf2)，密码为创建渠道时设置，请另行安全保存\n"
        f"本包未经上传，需人工完成：\n\n"
        f"1. 登录百度网盘，进入目标文件夹（建议 evermem/archive/）\n"
        f"2. 上传：{pkg['package']} 与 {pkg['package']}.sha256\n"
        f"3. 恢复时：先校验 sha256，再 `openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000` 解密，tar 解包\n\n"
        "注意：网盘官方接口不稳定，自动化上传属违规行为且有封号风险，故本渠道刻意保持人工。\n",
        encoding="utf-8")
    return {"synced": len(items), "files": len(items), "bytes": pkg["bytes"],
            "sha256": pkg["sha256"], "package": pkg["package"],
            "upload": "需手动上传", "verified": True, "removed": removed}

def check_s3(ch: dict) -> dict:
    from s3client import S3Client
    client = S3Client(ch["endpoint"], ch["access_key"], ch["secret_key"],
                      ch.get("region") or "us-east-1", ch["bucket"], ch.get("prefix") or "")
    keys = [k for k in client.list_objects() if k.endswith(".tar.aes")]
    if not keys:
        return {"ok": False, "channel": ch["name"], "error": "云端无加密归档包", "packages": 0}
    return {"ok": True, "channel": ch["name"], "type": "s3", "packages": len(keys),
            "latest": sorted(keys)[-1].split("/")[-1]}

def check_baidu_pan(ch: dict) -> dict:
    out_dir = Path(ch.get("target") or "")
    packs = sorted(out_dir.glob("evermem-*.tar.aes")) if out_dir.exists() else []
    if not packs:
        return {"ok": False, "channel": ch["name"], "error": "无加密归档包（尚未生成）", "packages": 0}
    return {"ok": True, "channel": ch["name"], "type": "baidu-pan", "packages": len(packs),
            "latest": packs[-1].name, "pending_upload": not (out_dir / "UPLOAD.md").exists()}

def restore_archive_package(ch: dict, enc_path: Path) -> dict:
    """校验 sha256 → openssl 解密 → tar 解包到本地（覆盖同名）。"""
    pw = _archive_password(ch)
    sha_file = enc_path.with_name(enc_path.name + ".sha256")
    if sha_file.exists():
        expect = (sha_file.read_text(encoding="utf-8").strip().split()[0])
        actual = hashlib.sha256(enc_path.read_bytes()).hexdigest()
        if expect != actual:
            raise RuntimeError(f"校验失败：加密包与 sha256 不符（{enc_path.name}），请勿使用")
    dec = BASE / f".pmem-restore-{int(time.time())}.tar"
    try:
        openssl = _openssl_path()
        r = subprocess.run([openssl, "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
                            "-in", str(enc_path), "-out", str(dec), "-pass", f"pass:{pw}"],
                           capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            raise RuntimeError(f"解密失败（密码错误？）：{(r.stderr or '')[:200]}")
        base = BASE.resolve()
        with tarfile.open(dec, "r") as t:
            names = t.getnames()
            for m in t.getmembers():
                name = m.name.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    raise RuntimeError(f"归档包含越界路径，已中止恢复：{m.name}")
                if m.issym() or m.islnk():
                    raise RuntimeError(f"归档包含链接，已中止恢复：{m.name}")
                target = base / name
                if not target.is_relative_to(base):
                    raise RuntimeError(f"归档路径越界：{m.name}")
                if m.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif m.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    t.extract(m, base, set_attrs=False)
        return {"ok": True, "count": len(names), "package": enc_path.name}
    finally:
        dec.unlink(missing_ok=True)

def restore_s3(ch: dict) -> dict:
    from s3client import S3Client
    client = S3Client(ch["endpoint"], ch["access_key"], ch["secret_key"],
                      ch.get("region") or "us-east-1", ch["bucket"], ch.get("prefix") or "")
    keys = sorted([k for k in client.list_objects() if k.endswith(".tar.aes")])
    if not keys:
        return {"ok": False, "error": "云端无加密归档包"}
    data = client.get_object(keys[-1])
    tmp = BASE / keys[-1].split("/")[-1]
    tmp.write_bytes(data)
    try:
        return restore_archive_package(ch, tmp)
    finally:
        tmp.unlink(missing_ok=True)

def restore_baidu_pan(ch: dict) -> dict:
    out_dir = Path(ch.get("target") or "")
    packs = sorted(out_dir.glob("evermem-*.tar.aes"))
    if not packs:
        return {"ok": False, "error": "无加密归档包"}
    return restore_archive_package(ch, packs[-1])

def run_channel(ch: dict) -> dict:
    """按渠道类型分发执行，统一异常处理。"""
    name = ch["name"]
    try:
        if ch["type"] == "local":
            result = run_local(ch)
        elif ch["type"] == "archive":
            result = run_archive(ch)
        elif ch["type"] == "remote":
            result = run_remote(ch)
        elif ch["type"] == "mail":
            result = run_mail(ch)
        elif ch["type"] == "s3":
            result = run_s3(ch)
        elif ch["type"] == "baidu-pan":
            result = run_baidu_pan(ch)
        else:
            raise RuntimeError(f"未知渠道类型：{ch['type']}")
        result["ok"] = True
        mark_channel(name, True, verified=result.get("verified"), extra=result)
        log_line(f"OK {ch['type']} {name} → {ch['target']} | sync {result.get('synced',0)} files")
        return {"channel": name, "type": ch["type"], **result}
    except Exception as exc:  # noqa: BLE001
        mark_channel(name, False, str(exc))
        log_line(f"FAIL {ch['type']} {name} → {ch['target']} | {exc}")
        return {"channel": name, "type": ch["type"], "ok": False, "error": str(exc)[:300]}

# ---------------- 全局流程 ----------------

def discover_targets() -> list[dict]:
    """自动探测本机可作为备份目标的位置（网盘同步夹/可写磁盘），供 UI 下拉选择，无需手填路径。"""
    out = []
    seen = set()
    home = Path.home()
    cloud_dirs = ("OneDrive", "OneDrive - 个人", "坚果云", "Nutstore", "百度网盘",
                  "BaiduNetdiskWorkspace", "Dropbox", "iCloud Drive", "iCloud 云盘", "阿里云盘")
    for name in cloud_dirs:
        for root in (home, home / "Documents", Path("C:/"), Path("D:/"), Path("E:/")):
            p = root / name
            if p.is_dir() and str(p) not in seen:
                seen.add(str(p))
                out.append({"name": f"网盘同步夹：{name}", "path": str(p),
                            "writable": bool(os.access(p, os.W_OK))})
    # 剩余空间 ≥5G 的可写盘根
    for d in ("C:/", "D:/", "E:/", "F:/", "G:/", "H:/"):
        p = Path(d)
        if not p.exists() or not os.access(p, os.W_OK) or str(p) in seen:
            continue
        try:
            free = shutil.disk_usage(p).free / 2**30
        except OSError:
            continue
        if free >= 5:
            out.append({"name": f"磁盘 {d.rstrip('/:')}（剩余 {free:.0f}G）", "path": str(p), "writable": True})
    return out

def check_channel(ch: dict) -> dict:
    """校验渠道云端数据与本地清单的一致性（借鉴 rclone check：文件存在+大小）。"""
    name = ch["name"]
    if ch["type"] == "local":
        dst = Path(ch["target"])
        if not dst.is_dir():
            return {"ok": False, "channel": name, "error": f"目标目录不可用：{ch['target']}"}
        items = data_items(ch["scope"])
        missing, size_bad = [], []
        for i in items:
            p = dst / i["rel"]
            if not p.exists():
                missing.append(i["rel"])
            elif abs(p.stat().st_size - i["size"]) > 8:
                size_bad.append(i["rel"])
        return {"ok": not missing and not size_bad, "channel": name, "type": "local",
                "total": len(items), "missing": missing[:5], "missing_n": len(missing),
                "size_bad": size_bad[:5], "size_bad_n": len(size_bad)}
    if ch["type"] == "archive":
        snap_dir = Path(ch["target"]) / "snapshots"
        snaps = sorted(snap_dir.glob("evermem-*.zip")) if snap_dir.exists() else []
        if not snaps:
            return {"ok": False, "channel": name, "error": "无快照可校验", "snapshots": 0}
        bad = []
        for s in snaps:
            try:
                z = zipfile.ZipFile(s)
                badz = z.testzip()
                z.close()
                if badz:
                    bad.append(f"{s.name}:{badz}")
            except (zipfile.BadZipFile, OSError) as exc:
                bad.append(f"{s.name}:{exc}")
        return {"ok": not bad, "channel": name, "type": "archive", "snapshots": len(snaps), "bad": bad[:5]}
    if ch["type"] == "s3":
        return check_s3(ch)
    if ch["type"] == "baidu-pan":
        return check_baidu_pan(ch)
    return {"ok": False, "channel": name, "error": f"渠道 {ch['type']} 暂不支持完整性校验（local/archive/s3/baidu-pan 支持）"}

def obscure(text: str) -> str:
    """轻量密码混淆（借鉴 rclone obscure）：非明文存储，本机可还原。"""
    import base64
    key = "evermem-obf"
    data = bytes([ord(c) ^ ord(key[i % len(key)]) for i, c in enumerate(text)])
    return "ob1:" + base64.b64encode(data).decode()

def deobscure(text: str) -> str:
    if isinstance(text, str) and text.startswith("ob1:"):
        import base64
        key = "evermem-obf"
        try:
            raw = base64.b64decode(text[4:])
            return "".join(chr(b ^ ord(key[i % len(key)])) for i, b in enumerate(raw))
        except Exception:
            return text
    return text

# Provider 契约 —— 渠道字段的唯一真源（前端据此渲染向导与行编辑器，不再各自硬编码）
#
#   label/desc : 步骤 1「选择渠道类型」的展示文案
#   fields     : 字段元信息登记表。k = 落盘字段名
#                  step      —— conn(步骤2 连接参数) / policy(步骤3 加密与策略)
#                  sensitive —— 涉密：值只回传掩码，留空表示"沿用旧值"
#                  min_len   —— 最小长度（归档密码强度闸门）
#   layout     : 步骤 2 的视觉分组。一行 = 一张「字段卡」，对应设计稿 03 的
#                 Endpoint·区域 / AccessKey ID·Secret 存本机 / Bucket·前缀路径
#                 k = 主字段，companion = 同卡副字段
PROVIDERS = {
    "local": {"label": "镜像（云盘/NAS 目录）", "desc": "增量同步到本机可写目录，零依赖",
              "layout": [{"k": "target"}, {"k": "frequency_hours"}],
              "fields": [
                  {"k": "target", "label": "云端目录", "step": "conn", "required": True,
                   "placeholder": "本机云盘同步目录或 NAS 挂载路径"},
                  {"k": "frequency_hours", "label": "自动频率（小时）", "step": "policy",
                   "default": 24, "type": "number"}]},
    "archive": {"label": "快照（保留 N 份）", "desc": "全量 zip 快照到本机目录，可回溯",
                "layout": [{"k": "target"}, {"k": "retention"}, {"k": "frequency_hours"}],
                "fields": [
                    {"k": "target", "label": "归档目录", "step": "conn", "required": True,
                     "placeholder": "本机快照归档目录"},
                    {"k": "retention", "label": "保留份数", "step": "policy", "default": 7, "type": "number"},
                    {"k": "frequency_hours", "label": "自动频率（小时）", "step": "policy",
                     "default": 24, "type": "number"}]},
    "remote": {"label": "服务器（ssh/scp）", "desc": "增量到异地服务器，需本机 ssh/scp 可用",
               "layout": [{"k": "target"}, {"k": "ssh_port"}, {"k": "frequency_hours"}],
               "fields": [
                   {"k": "target", "label": "user@host:/path", "step": "conn", "required": True,
                    "placeholder": "user@host:/backup/evermem"},
                   {"k": "ssh_port", "label": "SSH 端口", "step": "policy", "default": 22, "type": "number"},
                   {"k": "frequency_hours", "label": "自动频率（小时）", "step": "policy",
                    "default": 48, "type": "number"}]},
    "mail": {"label": "邮箱（SMTP 附件）", "desc": "全量 zip 发到邮箱，需 SMTP 凭据（密码走 PMEM_SMTP_PASS）",
             "layout": [{"k": "target"}, {"k": "smtp_host", "companion": "smtp_port"},
                        {"k": "smtp_user"}, {"k": "frequency_hours"}],
             "fields": [
                 {"k": "target", "label": "收件邮箱", "step": "conn", "required": True, "placeholder": "bk@example.com"},
                 {"k": "smtp_host", "label": "SMTP 服务器", "step": "conn", "required": True,
                  "placeholder": "smtp.example.com"},
                 {"k": "smtp_port", "label": "SMTP 端口", "step": "conn", "default": 465, "type": "number"},
                 {"k": "smtp_user", "label": "SMTP 用户", "step": "conn", "required": True},
                 {"k": "frequency_hours", "label": "自动频率（小时）", "step": "policy",
                  "default": 168, "type": "number"}]},
    "s3": {"label": "对象存储（S3 兼容）", "desc": "加密归档包直传 OSS/COS/S3/MinIO/BOS；SigV4 零依赖，加密在出本机前完成",
           "layout": [{"k": "endpoint", "companion": "region"},
                      {"k": "access_key", "companion": "secret_key"},
                      {"k": "bucket", "companion": "prefix", "sep": " / "}],
           "fields": [
               {"k": "endpoint", "label": "Endpoint", "step": "conn", "required": True,
                "placeholder": "https://<region>.example.com"},
               {"k": "region", "label": "区域", "step": "conn", "default": "us-east-1",
                "placeholder": "oss-cn-hangzhou / ap-guangzhou / bj"},
               {"k": "bucket", "label": "Bucket", "step": "conn", "required": True,
                "placeholder": "evermem-backup"},
               {"k": "prefix", "label": "前缀路径", "step": "conn", "placeholder": "archive"},
               {"k": "access_key", "label": "AccessKey ID", "step": "conn", "required": True},
               {"k": "secret_key", "label": "Secret 存本机", "step": "conn",
                "required": True, "type": "password", "sensitive": True,
                "hint": "混淆后写入本机配置，不随备份上传"},
               {"k": "archive_password", "label": "归档加密密码", "step": "policy", "required": True,
                "type": "password", "sensitive": True, "min_len": 16,
                "hint": "出本机前用它加密归档包；丢失将无法解密，请自行离线备份"},
               {"k": "frequency_hours", "label": "自动频率（小时）", "step": "policy",
                "default": 24, "type": "number"},
               {"k": "retention", "label": "云端保留包数", "step": "policy", "default": 30, "type": "number"}]},
    "baidu-pan": {"label": "百度网盘（冷备 · 手动上传）", "desc": "生成加密归档包+上传清单，需人工拖入网盘；不伪装成自动",
                  "layout": [{"k": "target"}],
                  "fields": [
                      {"k": "target", "label": "归档包生成目录", "step": "conn", "required": True,
                       "placeholder": "本机冷备归档目录"},
                      {"k": "archive_password", "label": "归档加密密码", "step": "policy", "required": True,
                       "type": "password", "sensitive": True, "min_len": 16,
                       "hint": "出本机前用它加密归档包；丢失将无法解密，请自行离线备份"},
                      {"k": "frequency_hours", "label": "提醒频率（小时）", "step": "policy",
                       "default": 168, "type": "number"},
                      {"k": "retention", "label": "本地保留包数", "step": "policy", "default": 12, "type": "number"}]},
}

# 需要"留空则保留旧值"的字段：任何一次增量编辑都不应把它们清空
PRESERVE_ON_BLANK = ("secret_key", "archive_password", "smtp_pass", "endpoint", "region",
                     "bucket", "prefix", "access_key")

SENSITIVE_FIELDS = ("secret_key", "archive_password", "smtp_pass")

def mask_secret(value: str) -> str:
    """涉密字段回传前端时的掩码形式：保留可辨识前缀，长度不泄露。"""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("ob1:") or len(raw) <= 8:
        return "••••••••"
    return raw[:4] + "*" * min(12, max(4, len(raw) - 8)) + raw[-4:]

def mask_smtp_pass(value: str) -> str:
    return mask_secret(value)

def from_request(c: dict, old: dict | None = None) -> dict:
    """HTTP 请求体 → 落盘渠道对象。领域规则只有这一份实现，向导与行编辑器共用。

    两条关键规则：
      1. PRESERVE_ON_BLANK 字段留空时沿用旧值 —— 否则改一处字段会清空已配好的连接参数/密钥。
      2. 涉密字段统一在此处以 obscure 混淆后落盘，明文永远不停留在配置文件里。
    """
    old = old if isinstance(old, dict) else {}

    def _int(value, default, minimum=1):
        try:
            return max(minimum, int(value or default))
        except (TypeError, ValueError):
            return max(minimum, default)

    def _kept(key: str) -> str:
        cur = str(c.get(key) or "").strip()
        if cur:
            return cur
        prev = str(old.get(key) or "").strip()
        return deobscure(prev) if prev else ""

    scope = [s for s in (c.get("scope") or ALL_SCOPES) if s in SCOPE_GROUPS] or list(ALL_SCOPES)
    out = {
        "type": c["type"],
        "name": str(c.get("name") or c["type"]).strip() or c["type"],
        "enabled": bool(c.get("enabled", True)),
        "target": str(c.get("target") or "").strip(),
        "scope": scope,
        "frequency_hours": _int(c.get("frequency_hours"), 24),
        "note": str(c.get("note") or ""),
        "retention": _int(c.get("retention"), 7),
        "ssh_port": _int(c.get("ssh_port"), 22),
    }
    for key in PRESERVE_ON_BLANK:
        if key == "smtp_pass":
            continue
        out[key] = _kept(key)
    out["region"] = out["region"] or "us-east-1"

    req_smtp = c.get("smtp") if isinstance(c.get("smtp"), dict) else {}
    old_smtp = old.get("smtp") if isinstance(old.get("smtp"), dict) else {}
    pass_raw = str(req_smtp.get("pass") or "").strip() or deobscure(str(old_smtp.get("pass") or "").strip())
    out["smtp"] = {
        "host": str(req_smtp.get("host") or "").strip() or str(old_smtp.get("host") or "").strip(),
        "port": _int(req_smtp.get("port"), 465),
        "user": str(req_smtp.get("user") or "").strip() or str(old_smtp.get("user") or "").strip(),
    }
    if pass_raw:
        out["smtp"]["pass"] = obscure(pass_raw)

    for key in ("secret_key", "archive_password"):
        if out.get(key):
            out[key] = obscure(out[key])
    return out

def channel_projection(ch: dict, state: dict | None = None) -> dict:
    """渠道 → 前端视图投影。涉密字段只出掩码，前端不持有明文密钥。"""
    st = state or {}
    return {
        "name": ch["name"], "type": ch["type"], "enabled": ch["enabled"],
        "target": ch["target"], "scope": ch["scope"],
        "frequency_hours": ch["frequency_hours"], "note": ch["note"],
        "retention": ch.get("retention", 7),
        "ssh_port": ch.get("ssh_port", 22),
        "smtp": {k: v for k, v in (ch.get("smtp") or {}).items() if k != "pass"},
        # s3 连接参数（此前缺失：导致已配置渠道在列表页显示为空、编辑时被空值覆盖）
        "endpoint": ch.get("endpoint", ""), "region": ch.get("region", "us-east-1"),
        "bucket": ch.get("bucket", ""), "prefix": ch.get("prefix", ""),
        "access_key": ch.get("access_key", ""),
        "secret_key_set": bool(ch.get("secret_key")),
        "archive_password_set": bool(ch.get("archive_password")),
        # 运行状态
        "last": st.get("at", "-"), "ok": st.get("ok"),
        "fail_count": st.get("fail_count", 0), "last_error": st.get("last_error", ""),
        "verified": st.get("verified"),
        "last_bytes": st.get("bytes", 0), "last_files": st.get("files", 0),
        "last_package": st.get("package", ""),
    }

def test_connection(ntype: str, params: dict) -> dict:
    """测试渠道连接（只读/建目录探测，不触碰已有数据；借 rclone lsd / borgmatic validate）。"""
    try:
        if ntype in ("local", "archive"):
            dst = Path(str(params.get("target") or "").strip())
            if not dst:
                return {"ok": False, "error": "请先填写目录路径"}
            try:
                dst.mkdir(parents=True, exist_ok=True)
                return {"ok": True, "msg": f"✅ 目录可写：{dst}"}
            except OSError as exc:
                return {"ok": False, "error": f"目录不可写：{exc}"}
        if ntype == "mail":
            host = str(params.get("smtp_host") or "").strip()
            port = int(params.get("smtp_port") or 465)
            user = str(params.get("smtp_user") or "").strip()
            passwd = deobscure(str(params.get("smtp_pass") or "")) or os.environ.get("PMEM_SMTP_PASS", "")
            if not host or not user or not passwd:
                return {"ok": False, "error": "SMTP 需 host/user/密码（密码留空读 PMEM_SMTP_PASS）"}
            try:
                server = smtplib.SMTP_SSL(host, port) if port == 465 else smtplib.SMTP(host, port)
                try:
                    if port != 465:
                        server.starttls()
                    server.login(user, passwd)
                    return {"ok": True, "msg": f"✅ SMTP 登录成功：{host}"}
                finally:
                    server.quit()
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"SMTP 连接失败：{exc}"}
        if ntype == "remote":
            return {"ok": False, "error": "remote 测试需真实 ssh 环境，请保存后用「校验完整性」验证"}
        if ntype == "s3":
            from s3client import S3Client
            if not (params.get("endpoint") and params.get("access_key") and params.get("secret_key") and params.get("bucket")):
                return {"ok": False, "error": "s3 需 endpoint/AK/SK/bucket"}
            try:
                return S3Client(str(params["endpoint"]), str(params["access_key"]),
                                str(params["secret_key"]), str(params.get("region") or "us-east-1"),
                                str(params["bucket"]), str(params.get("prefix") or "")).test()
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"S3 连接失败：{exc}"}
        if ntype == "baidu-pan":
            dst = Path(str(params.get("target") or "").strip())
            if not dst:
                return {"ok": False, "error": "请填写归档包生成目录"}
            try:
                dst.mkdir(parents=True, exist_ok=True)
                return {"ok": True, "msg": f"✅ 目录可写：{dst}（该渠道为人工冷备，本测试只验证本地生成位置）"}
            except OSError as exc:
                return {"ok": False, "error": f"目录不可写：{exc}"}
        return {"ok": False, "error": f"未知后端：{ntype}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"测试异常：{exc}"}

def sync_status() -> dict:
    cfg = load_cfg()
    chans = []
    for ch in cfg["channels"]:
        st = channel_state(ch["name"])
        row = channel_projection(ch, st)
        row["due"] = _due(ch["name"], ch) if ch["enabled"] else False
        chans.append(row)
    m = _manifest()
    return {"auto": cfg["auto"], "alert_email": cfg["alert_email"],
            "channels": chans, "history": m.get("history", [])[:10],
            "manifest": (BASE / MANIFEST).exists()}

def auto_sync_if_due() -> list[dict]:
    """按频率执行所有到期 enabled 渠道；失败累计告警。"""
    cfg = load_cfg()
    if not cfg["auto"]:
        return []
    out = []
    for ch in cfg["channels"]:
        if not ch["enabled"]:
            continue
        st = channel_state(ch["name"])
        if not _due(ch["name"], ch):
            continue
        res = run_channel(ch)
        out.append(res)
        if not res["ok"] and cfg["alert_email"] and int(st.get("fail_count", 0)) + 1 >= 2:
            _send_alert(cfg, ch, res)
    return out

def _send_alert(cfg: dict, ch: dict, res: dict) -> None:
    """连续失败≥2 次发告警邮件（复用 mail 渠道或默认 SMTP）。"""
    alert = cfg["alert_email"]
    subject = f"[恒忆备份告警] {ch['name']} 连续失败"
    body = f"渠道 {ch['type']}/{ch['name']} 备份失败：{res.get('error','')}"
    mail_ch = next((c for c in cfg["channels"] if c["type"] == "mail"), None)
    try:
        if mail_ch:
            smtp = mail_ch.get("smtp") or {}
            user = smtp.get("user", "")
            passwd = deobscure(str(smtp.get("pass") or "")) or os.environ.get("PMEM_SMTP_PASS", "")
            host, port = smtp.get("host", ""), int(smtp.get("port", 465) or 465)
            if host and user and passwd:
                s = smtplib.SMTP_SSL(host, port) if port == 465 else smtplib.SMTP(host, port)
                try:
                    if port != 465:
                        s.starttls()
                    s.login(user, passwd)
                    m = MIMEMultipart()
                    m["From"], m["To"], m["Subject"] = user, alert, subject
                    m.attach(MIMEText(body, "plain", "utf-8"))
                    s.sendmail(user, [alert], m.as_string())
                finally:
                    s.quit()
        log_line(f"ALERT → {alert} | {subject}")
    except Exception as exc:  # noqa: BLE001
        log_line(f"ALERT FAIL → {alert} | {exc}")

def restore_channel(ch: dict) -> dict:
    """从指定渠道恢复数据到本地（覆盖同名）。"""
    if ch["type"] == "local":
        src = Path(ch["target"])
        if not src.is_dir():
            return {"ok": False, "error": f"目标目录不可用：{ch['target']}"}
        restored = []
        # 关键：待恢复清单不能只用本机 data_items() 枚举。
        # 本机为空（新机首迁）时本机枚举是空集，恢复会「成功」但一个文件都没拷，
        # 属于典型假成功。这里取「本机清单 ∪ 渠道根实际存在的文件」。
        rels = {i["rel"] for i in data_items(ch["scope"])}
        for name in scope_paths(ch["scope"]):
            s = src / name
            if not s.exists():
                continue
            if s.is_file():
                rels.add(name)
                continue
            for f in s.rglob("*"):
                if (f.is_file() and not f.name.startswith(".pmem-")
                    and not f.name.startswith("evermem-")
                    and not f.name.endswith(".tar.aes")
                    and not f.name.endswith(".sha256")
                    and f.name != "UPLOAD.md"):
                    rels.add(str(Path(name) / f.relative_to(s)))
        for rel in sorted(rels):
            p = src / rel
            if not p.exists():
                continue
            d = BASE / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, d)
            restored.append(rel)
        return {"ok": True, "count": len(restored), "channel": ch["name"]}
    if ch["type"] == "archive":
        snap_dir = Path(ch["target"]) / "snapshots"
        snaps = sorted(snap_dir.glob("evermem-*.zip")) if snap_dir.exists() else []
        if not snaps:
            return {"ok": False, "error": "无可用快照"}
        base = BASE.resolve()
        with zipfile.ZipFile(snaps[-1], "r") as z:
            for m in z.infolist():
                name = m.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    raise RuntimeError(f"快照包含越界路径，已中止恢复：{m.filename}")
            z.extractall(base)
        return {"ok": True, "count": len(snaps[-1].namelist()), "channel": ch["name"], "snapshot": snaps[-1].name}
    if ch["type"] == "s3":
        r = restore_s3(ch)
        return {**r, "channel": ch["name"]}
    if ch["type"] == "baidu-pan":
        r = restore_baidu_pan(ch)
        return {**r, "channel": ch["name"]}
    return {"ok": False, "error": f"渠道 {ch['type']} 不支持 restore（local/archive/s3/baidu-pan 可用）"}

# ---------------- CLI ----------------

def _find_channel(cfg: dict, name: str | None):
    if name:
        return next((c for c in cfg["channels"] if c["name"] == name), None)
    return None

def main() -> int:
    cfg = load_cfg()
    scope = None
    if "--scope" in sys.argv:
        i = sys.argv.index("--scope")
        if i + 1 < len(sys.argv):
            scope = [s.strip() for s in sys.argv[i + 1].split(",") if s.strip() in SCOPE_GROUPS] or None
    ch_name = None
    if "--channel" in sys.argv:
        i = sys.argv.index("--channel")
        if i + 1 < len(sys.argv):
            ch_name = sys.argv[i + 1]

    if not cfg["channels"]:
        print("⚠️  未配置备份渠道。编辑 pmem_backup.json（见 docs/BACKUP-DESIGN.md）或 Web「数据备份」页设置。")
        return 1

    if "--restore" in sys.argv:
        ch = _find_channel(cfg, ch_name) or (cfg["channels"][0] if len(cfg["channels"]) == 1 else None)
        if not ch:
            print("需用 --channel 指定要恢复的渠道。")
            return 1
        r = restore_channel(ch)
        print(f"恢复：{r.get('channel', '-')} {r.get('count', 0)} 个文件（覆盖同名）" +
              (f"（快照 {r.get('snapshot')}）" if r.get("snapshot") else "") +
              ("；建议 mem.py reindex" if r.get("ok") else f" ❌ {r.get('error','')}"))
        return 0 if r.get("ok") else 1

    if "--auto" in sys.argv:
        results = auto_sync_if_due()
        for r in results:
            flag = "✅" if r["ok"] else "❌"
            print(f"{flag} [{r['type']}/{r['channel']}] → {r.get('target','')} | {r.get('error', '') if not r['ok'] else 'OK'}")
        print(f"本次到期执行 {len(results)} 个渠道")
        return 0

    if "--dry-run" in sys.argv:
        for ch in cfg["channels"]:
            items = data_items(scope or ch["scope"])
            print(f"[{ch['type']}/{ch['name']}] → {ch['target']} | 范围 {','.join(ch['scope'])} | "
                  f"{len(items)} 文件 / {total_size(items)/1048576:.2f} MB | 频率 {ch['frequency_hours']}h | "
                  f"{'开' if ch['enabled'] else '关'}")
        return 0

    if "status" in sys.argv:
        st = sync_status()
        print(f"自动备份：{'开' if st['auto'] else '关'} | 告警邮箱：{st['alert_email'] or '-'}")
        for c in st["channels"]:
            flag = "●" if c["enabled"] else "○"
            print(f"{flag} [{c['type']}/{c['name']}] {c['target'] or '(未设)'} | 上次 {c['last']} | "
                  f"状态 {('OK' if c['ok'] else ('FAIL×'+str(c['fail_count']) if c['fail_count'] else '-'))}"
                  + (f" | 错误：{c['last_error'][:60]}" if c['last_error'] else "")
                  + (" | 已到期" if c["due"] else ""))
        if st["history"]:
            print("最近记录：")
            for h in st["history"][:5]:
                print(f"  · {h['at']} [{h['channel']}] {'OK' if h['ok'] else 'FAIL'} 同步 {h['synced']} 文件")
        return 0

    if "check" in sys.argv:
        targets = [ch for ch in cfg["channels"] if (not ch_name or ch["name"] == ch_name)]
        if ch_name and not targets:
            print(f"未找到渠道：{ch_name}")
            return 1
        for ch in targets:
            r = check_channel(ch)
            if r.get("ok"):
                print(f"✅ [{ch['type']}/{ch['name']}] 一致性校验通过"
                      + (f"（{r.get('total', r.get('snapshots'))} 项）" if r.get("total") or r.get("snapshots") else ""))
            else:
                print(f"❌ [{ch['type']}/{ch['name']}] {r.get('error', '校验失败')}"
                      + (f" 缺失{r.get('missing_n', 0)}/大小异常{r.get('size_bad_n', 0)}" if r.get("missing_n") else ""))
        return 0

    # 执行（--channel 指定或全部 enabled）
    targets = [ch for ch in cfg["channels"] if (not ch_name or ch["name"] == ch_name)]
    if ch_name and not targets:
        print(f"未找到渠道：{ch_name}")
        return 1
    for ch in targets:
        if ch_name or ch["enabled"]:
            if scope:
                ch = dict(ch, scope=scope)  # 命令行 --scope 覆盖渠道自身范围
            res = run_channel(ch)
            flag = "✅" if res["ok"] else "❌"
            print(f"{flag} [{ch['type']}/{ch['name']}] → {ch['target']} | 同步 {res.get('synced',0)} 跳过 "
                  f"{res.get('skipped',0)} | 校验 {('通过' if res.get('verified') else ('未做' if res.get('verified') is None else '缺失'))}"
                  + (f" | {res['error']}" if not res["ok"] else ""))
    return 0

if __name__ == "__main__":
    sys.exit(main())
