# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# 恒忆 Evermem · 全面功能检查清单（正常 + 边界/异常）
# 逐项验证：可调用、无报错、结果完整、异常正确处理
#

import json
import os as _os
import shutil as _shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]  # 项目根（scripts/ 的上一级）
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
import paths as Paths  # noqa: E402 - 数据目录唯一入口（隔离检查用数据根，勿用代码根）
# 解释器与测试目录走环境变量，勿写死用户机器路径（发布约定）：
#   PMEM_SYS_PY     指定解释器（缺省用运行本脚本的 python）
#   PMEM_TEST_DIR   指向含可提取文档的样本目录（缺省跳过 extract 用例）
import os as _os
PY = _os.environ.get("PMEM_SYS_PY", "") or sys.executable
SYS = _os.environ.get("PMEM_SYS_PY", "") or sys.executable
# node 语法检查用 PATH 探测（原写死 C:/Program Files/nodejs/node.exe，macOS/Linux 直接不可用）
_NODE = _os.environ.get("PMEM_NODE", "") or _shutil.which("node") or ""
SAMPLE_DIR = Path(_os.environ.get("PMEM_TEST_DIR", "")) if _os.environ.get("PMEM_TEST_DIR") else None

RESULTS = []  # (功能, 状态, 说明)

def check(name, ok, note=""):
    RESULTS.append((name, ok, note))
    print(f"[{'OK ' if ok else 'FAIL'}] {name}  {note[:70]}")


_SUMMARY_PRINTED = False


def report_summary(reason: str = "") -> None:
    """打印汇总（幂等）。

    用 atexit 兜底的理由：本脚本是平铺脚本，任何一处抛异常都会让**后段检查与汇总行
    整体不执行**——输出的前半部分看着全 OK，实际第六节（前端冒烟、语法检查）根本没跑，
    典型的假成功。所以异常退出时也必须出汇总，并明确标注"中断"。
    """
    global _SUMMARY_PRINTED
    if _SUMMARY_PRINTED:
        return
    _SUMMARY_PRINTED = True
    fails = [r for r in RESULTS if not r[1]]
    print()
    print("=" * 72)
    if reason:
        print(f"⚠ 检查中断：{reason}")
    print(f"总检查 {len(RESULTS)} 项 | 通过 {len(RESULTS) - len(fails)} | 失败 {len(fails)}")
    for f in fails:
        print(f"  ✗ {f[0]}: {f[2]}")


def _exit_report() -> None:
    report_summary("脚本提前退出，上方报错为准；后段检查未执行")


import atexit as _atexit  # noqa: E402

_atexit.register(_exit_report)


def run(cmd, timeout=300, cwd=None):
    t0 = time.perf_counter()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="ignore", timeout=timeout, cwd=cwd or str(BASE))
        return r.returncode == 0, (r.stdout or "") + (r.stderr or ""), (time.perf_counter() - t0) * 1000
    except Exception as e:
        return False, str(e), (time.perf_counter() - t0) * 1000

print("=" * 72)
print("一、核心引擎（mem.py）—— 正常 + 边界")
ok, out, ms = run([PY, "mem.py", "stats"])
check("stats（正常）", ok and "笔记" in out, f"{ms:.0f}ms")
ok, out, ms = run([PY, "mem.py", "recall", "融合通信", "--limit", "2"])
check("recall（正常命中）", ok and "命中" in out)
ok, out, ms = run([PY, "mem.py", "recall", "完全不存在的词xyzabc123", "--limit", "2"])
check("recall（不存在→无命中，不误召）", ok and "无命中" in out, f"{ms:.0f}ms")
ok, out, ms = run([PY, "mem.py", "recall", "", "--limit", "2"])
check("recall（空查询）", ok and ("无命中" in out or "命中 0" in out or "参数" in out))
ok, out, ms = run([PY, "mem.py", "show", "20260927-0245-134"])
check("show（存在 id）", ok and "可提取性地地图" in out)
ok, out, ms = run([PY, "mem.py", "show", "not-exist-id"])
check("show（不存在 id→明确报错）", not ok or "未找到" in out)
ok, out, ms = run([PY, "mem.py", "hot", "--limit", "20"])
check("hot（正常 20 条预算内）", ok and ("共" in out or "- " in out))
ok, out, ms = run([PY, "mem.py", "hot", "--limit", "20", "--auto-fill", "--tokens", "200"])
check("hot（token 预算截断）", ok and "预算" in out)
ok, out, ms = run([PY, "mem.py", "reindex"])
check("reindex（幂等重建）", ok and "条" in out)

print()
print("二、收割（harvest.py）")
ok, out, ms = run([PY, "harvest.py", "scan", "--days", "1", "--dry-run"])
check("scan（dry-run 不落盘）", ok and "dry-run" in out, f"{ms:.0f}ms")
ok, out, ms = run([PY, "harvest.py", "signals", "--days", "1"])
check("signals（统计）", ok and "执行记录" in out)

print()
print("三、提取（scripts/ingest.py）")
ok, out, ms = run([PY, "scripts/ingest.py", "list", str(BASE)])
check("list（正常目录）", ok)
ok, out, ms = run([PY, "scripts/ingest.py", "list", str(BASE / "tmp_chk" / "不存在目录xyz")])
check("list（不存在目录→不崩溃）", ok)
if SAMPLE_DIR:
    ok, out, ms = run([PY, "scripts/ingest.py", "extract", str(SAMPLE_DIR), "--out-dir", str(BASE / "tmp_chk"), "--show-failed"])
    check("extract（正常，含失败统计）", ok and "成功" in out)
else:
    print("[SKIP] extract（未设置 PMEM_TEST_DIR 指向真实文档目录，跳过）")
    check("extract（SKIP）", True, "PMEM_TEST_DIR 未设置")

print()
print("四、MCP 桥（evermem_mcp.py）—— 正常 + 边界")
def mcp(tools_calls):
    lines = ['{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}',
             '{"jsonrpc":"2.0","method":"notifications/initialized"}']
    for i, tc in enumerate(tools_calls, 2):
        lines.append(json.dumps({"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": tc}))
    r = subprocess.run([PY, "evermem_mcp.py"], input="\n".join(lines) + "\n",
                       capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=120, cwd=str(BASE))
    return r.stdout
out = mcp([
    {"name": "mem_read", "arguments": {"query": "融合通信"}},
    {"name": "mem_hot", "arguments": {}},
    {"name": "mem_read", "arguments": {}},                          # 缺必填 query
    {"name": "not_exist", "arguments": {}},                         # 未知工具
    {"name": "mem_record", "arguments": {"title": ""}},             # 空标题
])
import collections as _c
id2res = {}
for line in out.splitlines():
    try:
        d = json.loads(line)
        if d.get("id") in (2, 3, 4) and "result" in d:
            txt = d["result"].get("content", [{}])[0].get("text", "")
            id2res[d["id"]] = json.loads(txt) if txt.startswith("{") else txt
    except (json.JSONDecodeError, ValueError):
        continue
check("mcp mem_read 正常", id2res.get(2, {}).get("hits") is not None and len(id2res.get(2, {}).get("hits", [])) > 0)
check("mcp mem_hot 正常", id2res.get(3, {}).get("count", 0) >= 19)
check("mcp 缺必填→明确错误", id2res.get(4, {}).get("error") is not None)
check("mcp 未知工具→错误码", "-32601" in out)
check("mcp 空标题→错误", "title 必填" in out)

print()
print("五、Web API —— 正常 + 边界")
import http.client as _hc
import os as _os2, time as _time2
# 自启本地 server（先起再测，结束自动关闭）：避免"未起服务→14 项假失败"。
# 端口必须**动态取空闲端口**：写死 8765 时若桌面端/绿色版已在运行，我们的子进程 bind 失败，
# 后续用例会静默打到"别人的实例"上——测的就不是本次代码，而是假成功。
# 两个实例分工：LIVE 打正式数据根（只跑读用例）；ISO 打隔离数据根（跑写用例）。
import socket as _socket


def _free_port() -> int:
    """向系统要一个当前空闲的本地端口，避免与已在运行的实例抢端口。"""
    s = _socket.socket()
    s.bind(("127.0.0.1", 0))
    p = int(s.getsockname()[1])
    s.close()
    return p


def _isolated_home() -> Path:
    """检查用的临时数据根——**写用例一律打在这里，绝不碰正式库**。

    位置选在正式数据根的**上一级**，三个理由：
      ① 与数据根同卷：临时目录被重定向到网络盘时 os.replace 会失败（reindex 直接报错）；
      ② 在数据根之外：不会被「扫描根」当成知识空间扫到；
      ③ 与 notes/ 无关：留残留也只是个临时目录，污染不到正式记忆库。
    路径固定复用（不带 pid），因为本脚本**不做删除清理**——见文件末尾说明。
    """
    try:
        p = Path(str(Paths.data_root())).parent / "_pmem_check_tmp"
        p.mkdir(parents=True, exist_ok=True)
        return p
    except OSError:
        import tempfile as _tf
        return Path(_tf.mkdtemp(prefix="pmem-check-"))


_PORT = _free_port()
_PORT_ISO = _free_port()
_ISO_HOME = _isolated_home()
_srv = subprocess.Popen([PY, "web/server.py"], cwd=str(BASE),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        env={**_os2.environ, "PMEM_NO_AUTO_HARVEST": "1",
                             "PMEM_WEB_PORT": str(_PORT)})
_srv_iso = subprocess.Popen(
    [PY, "web/server.py"], cwd=str(BASE),
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    env={**_os2.environ, "PMEM_NO_AUTO_HARVEST": "1",
         "PMEM_HOME": str(_ISO_HOME), "PMEM_WEB_PORT": str(_PORT_ISO)})


def _srv_ready(port: int) -> bool:
    """就绪判定必须是"真实请求 /api/health 成功"：
    纯 TCP 探测可能在 handler 进入服务循环前就通过（HTTPServer 构造即 bind+listen），
    导致紧随其后的第一个 API 请求（health）连接被拒——时序性假失败。
    """
    try:
        c = _hc.HTTPConnection("127.0.0.1", port, timeout=2)
        c.request("GET", "/api/health")
        r = c.getresponse()
        body = r.read(200).decode("utf-8", "ignore")
        c.close()
        return r.status == 200 and "ok" in body
    except Exception:
        try:
            c.close()
        except Exception:
            pass
        return False


def _wait_ready(port: int) -> bool:
    for _ in range(60):  # 最多等 15 秒（F 盘/杀软慢时留足余量）
        if _srv_ready(port):
            return True
        _time2.sleep(0.25)
    return False


check("自启 server 就绪（本次进程的实例，端口 %d）" % _PORT, _wait_ready(_PORT))
check("隔离 server 就绪（写用例专用，端口 %d）" % _PORT_ISO, _wait_ready(_PORT_ISO))
def api(path, method="GET", body=None, port: int = _PORT):
    c = _hc.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        if method == "POST":
            c.request("POST", path, body=json.dumps(body) if body else "{}",
                      headers={"Content-Type": "application/json"})
        else:
            c.request("GET", path)
        r = c.getresponse()
        data = r.read(20000).decode("utf-8", "ignore")
        return r.status, data
    except Exception as e:
        return 0, str(e)
    finally:
        c.close()
st, body = api("/api/health")
check("GET /api/health", st == 200 and "ok" in body)
st, body = api("/api/notes")
check("GET /api/notes", st == 200 and "notes" in body)
st, body = api("/api/search?q=%E5%85%AC%E6%96%87")
check("GET /api/search（中文）", st == 200 and "hits" in body)
st, body = api("/api/search?q=zzznotexist")
check("GET /api/search（无命中）", st == 200 and '"hits": []' in body)
st, body = api("/api/hot")
check("GET /api/hot", st == 200 and "hot" in body)
st, body = api("/api/stats")
check("GET /api/stats", st == 200 and "total" in body)
st, body = api("/api/spaces")
check("GET /api/spaces（缓存命中）", st == 200 and "spaces" in body)
st, body = api("/api/hosts")
check("GET /api/hosts", st == 200 and "hosts" in body)
st, body = api("/api/mcpsetup")
check("GET /api/mcpsetup", st == 200 and "targets" in body)
st, body = api("/api/note?id=20260927-0245-134")
check("GET /api/note（存在，含 origin）", st == 200 and '"origin"' in body)
st, body = api("/api/note?id=bad")
check("GET /api/note（不存在→404）", st == 404)
st, body = api("/api/version")
check("GET /api/version（版本号随 VERSION 文件）", st == 200 and '"version"' in body)
st, body = api("/api/update/sources")
check("GET /api/update/sources（离线返回源配置）",
      st == 200 and '"config"' in body and '"platform"' in body)
st, body = api("/api/doesnotexist")
check("GET 未知路径→404", st == 404)
# 写用例打在**隔离实例**（PMEM_HOME=临时数据根）上，正式库零写入、零清理依赖。
# 旧实现在正式库里建笔记再用 unlink 删除：本机 safe-delete 守卫会拦住 unlink，
# 脚本在此处抛异常 → 后段检查不跑、汇总行不打印、测试笔记永久留在正式库（假成功）。
st, body = api("/api/note", "POST", {"title": ""}, port=_PORT_ISO)
check("POST /api/note（空标题→400）", st == 400)
st, body = api("/api/note", "POST", {"title": "边界测试笔记", "body": "x"}, port=_PORT_ISO)
check("POST /api/note（正常新建）", st == 200 and "staged" in body)
_nid = ""
try:
    _nid = str(json.loads(body).get("id") or "")
except (ValueError, TypeError):
    pass
# 反向断言（回归守卫）：必须**真的写成功**（拿到 id）且只落在隔离数据根。
# 不要写成"没拿到 id 就算通过"——那样断言是空的，等于没测（假成功）。
_live_leak = (Path(str(Paths.data_root())) / "notes" / "lessons" / f"web-{_nid}.md").exists() if _nid else False
check("测试笔记未污染正式库（且写入成功）", bool(_nid) and not _live_leak,
      f"id={_nid}" if _nid else "未取到 id：写入未成功，断言无效")
# 关闭自启 server（terminate 幂等；子进程若已自行退出也无害）
for _p in (_srv, _srv_iso):
    try:
        _p.terminate()
    except Exception:
        pass
# 这里**不做任何删除清理**：本机 safe-delete 守卫会在删除动作上写账本失败并直接终止进程
# （无 traceback、退出码非零）。一旦在脚本中途触发，后段检查与汇总行会整体不执行 = 假成功。
# 隔离数据根固定复用、且位于正式库之外，留一点残留的代价远小于被中途 kill。
print(f"[信息] 隔离数据根（位于正式库之外，可随时手动删除）：{_ISO_HOME}")

print()
print("六、前端与数据健康")
ok, out, ms = run([PY, "scripts/frontend_smoke.py"])
check("前端静态契约冒烟（元素/函数/路由）", ok)
if _NODE:
    ok, out, ms = run([_NODE, "--check", "web/index.js"])
    check("index.js 语法", ok)
else:
    check("index.js 语法（跳过：PATH 无 node）", True)
ok, out, ms = run([PY, "-m", "py_compile", "web/server.py", "evermem_mcp.py",
                   "mem.py", "update.py", "paths.py", "recipes.py", "backup.py", "harvest.py",
                   "memimport.py", "s3client.py", "desktop.py", "scripts/ingest.py",
                   "scripts/knowledge_scan.py", "scripts/gen_update_manifest.py", "scripts/make_icon.py",
                   "scripts/scan_spaces.py", "scripts/check_all.py", "scripts/frontend_smoke.py"])
check("全部 Python 语法", ok)

report_summary()
# 失败必须给非零退出码：否则调用方（脚本 / CI）拿到 exit 0，又是一次假成功
sys.exit(1 if any(not r[1] for r in RESULTS) else 0)
