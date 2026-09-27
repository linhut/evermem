#!/usr/bin/env python3
# pmem backup v3 - 恒忆多渠道数据备份（零依赖 + 可选 ssh/scp、smtplib）
#
# Copyright (c) 2026 Jose-AI
# https://www.linhut.cn
# SPDX-License-Identifier: MIT
#
# 规格见 docs/BACKUP-DESIGN.md。要点：
#   - 本地数据 = 唯一事实源，所有渠道为副本，方向默认 upload（单向，无跨渠道冲突）
#   - 渠道：local(增量镜像) / archive(全量快照保留N份) / remote(ssh/scp 增量镜像) / mail(SMTP 附件)
#   - 每渠道独立频率、失败记录、连续失败告警（邮件可选）
#   - 数据与代码分离：数据只经本系统进出，不进 Git/GitHub
#
# 配置 pmem_backup.json：
#   {"auto": true, "alert_email": "me@x.com", "channels": [
#      {"type":"local","name":"坚果云","enabled":true,"target":"D:/坚果云/evermem-backup",
#       "scope":["notes","events","index","meta"],"frequency_hours":24},
#      {"type":"archive","name":"本机快照","enabled":true,"target":"F:/evermem-snapshots","retention":7},
#      {"type":"remote","name":"服务器","enabled":false,"target":"user@host:/backup/evermem","ssh_port":22},
#      {"type":"mail","name":"邮箱","enabled":false,"target":"bk@x.com",
#       "smtp":{"host":"smtp.x.com","port":465,"user":"me@x.com","pass":"***"}}]}
# 旧格式 {target,note,scope,auto,interval_hours} 自动迁移为单 local 渠道。
#
# 用法：status / --dry-run / [--channel name] / --restore [--channel name] / [--scope n,e]

from __future__ import annotations

import io
import json
import os
import shutil
import smtplib
import subprocess
import sys
import time
import zipfile
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / "pmem_backup.json"
MANIFEST = ".pmem-backup-last.json"
LOG_FILE = "backup.log"
AUTO_CHECK_SECONDS = 300
CHANNEL_TYPES = ("local", "archive", "remote", "mail")

SCOPE_GROUPS = {
    "notes": ["notes"],
    "events": ["events"],
    "index": ["index.json"],
    "meta": ["harvest_state.json", "corpus_spaces.json", "kb.json", "knowledge-base.md", "pmem_config.json"],
}
ALL_SCOPES = list(SCOPE_GROUPS)


# ---------------- 配置 ----------------

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
        })
    return {"auto": auto, "alert_email": alert, "channels": out}


def save_cfg(cfg: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------- 数据收集与校验 ----------------

def scope_paths(scope: list[str] | None = None) -> list[str]:
    out = []
    for s in (scope or ALL_SCOPES):
        out += SCOPE_GROUPS.get(s, [])
    return out


def data_items(scope: list[str] | None = None) -> list[dict]:
    items = []
    for name in scope_paths(scope):
        p = BASE / name
        if p.exists():
            collect(p, name, items)
    return items


def collect(src: Path, rel: str, items: list[dict]) -> None:
    if src.is_file():
        st = src.stat()
        items.append({"rel": rel, "mtime": st.st_mtime, "size": st.st_size})
    else:
        for f in sorted(src.rglob("*")):
            if f.is_file() and not f.name.startswith(".pmem-"):
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
    (BASE / MANIFEST).write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


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
    state_p.write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
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
    tmp_state.write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
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
    passwd = smtp.get("pass") or os.environ.get("PMEM_SMTP_PASS", "")
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

def sync_status() -> dict:
    cfg = load_cfg()
    chans = []
    for ch in cfg["channels"]:
        st = channel_state(ch["name"])
        chans.append({
            "name": ch["name"], "type": ch["type"], "enabled": ch["enabled"],
            "target": ch["target"], "scope": ch["scope"],
            "frequency_hours": ch["frequency_hours"], "note": ch["note"],
            "retention": ch.get("retention", 7),
            "last": st.get("at", "-"), "ok": st.get("ok"),
            "fail_count": st.get("fail_count", 0), "last_error": st.get("last_error", ""),
            "verified": st.get("verified"), "due": _due(ch["name"], ch) if ch["enabled"] else False,
        })
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
            passwd = smtp.get("pass") or os.environ.get("PMEM_SMTP_PASS", "")
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
        for i in data_items(ch["scope"]):
            p = src / i["rel"]
            if not p.exists():
                continue
            d = BASE / i["rel"]
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, d)
            restored.append(i["rel"])
        return {"ok": True, "count": len(restored), "channel": ch["name"]}
    if ch["type"] == "archive":
        snap_dir = Path(ch["target"]) / "snapshots"
        snaps = sorted(snap_dir.glob("evermem-*.zip")) if snap_dir.exists() else []
        if not snaps:
            return {"ok": False, "error": "无可用快照"}
        with zipfile.ZipFile(snaps[-1], "r") as z:
            z.extractall(BASE)
        return {"ok": True, "count": len(snaps[-1].namelist()), "channel": ch["name"], "snapshot": snaps[-1].name}
    return {"ok": False, "error": f"渠道 {ch['type']} 不支持 restore（local/archive 可用）"}


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

    if "--dry-run" in sys.argv:
        for ch in cfg["channels"]:
            items = data_items(ch["scope"])
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

    # 执行（--channel 指定或全部 enabled）
    targets = [ch for ch in cfg["channels"] if (not ch_name or ch["name"] == ch_name)]
    if ch_name and not targets:
        print(f"未找到渠道：{ch_name}")
        return 1
    for ch in targets:
        if ch_name or ch["enabled"]:
            res = run_channel(ch)
            flag = "✅" if res["ok"] else "❌"
            print(f"{flag} [{ch['type']}/{ch['name']}] → {ch['target']} | 同步 {res.get('synced',0)} 跳过 "
                  f"{res.get('skipped',0)} | 校验 {('通过' if res.get('verified') else ('未做' if res.get('verified') is None else '缺失'))}"
                  + (f" | {res['error']}" if not res["ok"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())