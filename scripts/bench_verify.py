# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# 恒忆 Evermem 工具验收 + 性能基准
# 逐个调用全部工具，输出：功能结果 + 耗时（冷启动=新进程，热调用=进程内）

import subprocess
import sys
import time
from pathlib import Path

BASE = Path(r"C:/Users/Administrator/Documents/<工作区>/.memory")
PY = r"C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SYS = r"python"

RESULTS = []

def run(name, cmd, timeout=300, note=""):
    t0 = time.perf_counter()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="ignore", timeout=timeout, cwd=str(BASE))
        ok = r.returncode == 0
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        ms = (time.perf_counter() - t0) * 1000
    except Exception as exc:  # noqa: BLE001
        ok, out, err, ms = False, "", str(exc), (time.perf_counter() - t0) * 1000
    RESULTS.append((name, ok, ms, out.splitlines()[0] if out else (err or "无输出")))
    print(f"[{'OK ' if ok else 'FAIL'}] {name}  {ms:7.0f} ms  | {note}")
    if not ok:
        print(f"      ↳ {err[:200]}")

print("=" * 70)
print("一、核心引擎（CLI）")
run("mem.py stats", [PY, "mem.py", "stats"])
run("mem.py recall", [PY, "mem.py", "recall", "融合通信", "--limit", "2"])
run("mem.py hot(同步预览)", [PY, "mem.py", "hot", "--limit", "5"])
run("mem.py reindex", [PY, "mem.py", "reindex"])
run("harvest signals", [PY, "harvest.py", "signals", "--days", "1"])
run("ingest list", [PY, "ingest.py", "list", "F:/机房搬迁"])

print()
print("二、MCP 注入桥（stdio 四工具）")
t0 = time.perf_counter()
mcp_script = (
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}\n'
    '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
    '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
    '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"mem_read","arguments":{"query":"机房 搬迁"}}}\n'
    '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"mem_hot","arguments":{}}}\n'
)
r = subprocess.run([PY, "evermem_mcp.py"], input=mcp_script, capture_output=True,
                   text=True, encoding="utf-8", errors="ignore", timeout=120, cwd=str(BASE))
ms = (time.perf_counter() - t0) * 1000
lines = [l for l in r.stdout.splitlines() if l.strip()]
tools_ok = any('mem_read' in l for l in lines)
read_ok = any('机房' in l for l in lines)
hot_ok = any('hot' in l and '20' in l for l in lines)
ok = r.returncode == 0 and tools_ok and read_ok and hot_ok
RESULTS.append(("evermem_mcp.py", ok, ms, f"tools/list+read+hot 全通" if ok else "异常"))
print(f"[{'OK ' if ok else 'FAIL'}] evermem_mcp.py  {ms:7.0f} ms  | 工具:{tools_ok} read命中:{read_ok} hot:{hot_ok}")

print()
print("三、Web 界面（13 API 抽查 + 耗时）")
import http.client
t0 = time.perf_counter()
c = http.client.HTTPConnection("127.0.0.1", 8765, timeout=5)
try:
    c.request("GET", "/api/health")
    h = c.getresponse()
    health_ok = h.status == 200
    c.close()
except Exception as exc:  # noqa: BLE001
    health_ok = False
ms = (time.perf_counter() - t0) * 1000
RESULTS.append(("web/server(8765)", health_ok, ms, "health" if health_ok else "未运行"))
print(f"[{'OK ' if health_ok else 'FAIL'}] web/server  {ms:7.0f} ms  | health")

if health_ok:
    import json as _j
    from urllib.parse import quote as _q
    for path in ["/api/notes", "/api/search?q=" + _q("公文") + "&limit=2", "/api/hot", "/api/stats",
                 "/api/spaces", "/api/hosts", "/api/blocks?space=" + _q("某指挥中心")]:
        t0 = time.perf_counter()
        c = http.client.HTTPConnection("127.0.0.1", 8765, timeout=10)
        try:
            c.request("GET", path)
            rp = c.getresponse()
            body = rp.read(200).decode("utf-8", "ignore")
            ok = rp.status == 200
            c.close()
        except Exception as exc:  # noqa: BLE001
            ok, body = False, str(exc)
        ms = (time.perf_counter() - t0) * 1000
        RESULTS.append(("web " + path, ok, ms, ""))
        print(f"[{'OK ' if ok else 'FAIL'}] {path}  {ms:6.0f} ms")

print()
print("四、回归测试")
run("tests/test_recall.py", [PY, "tests/test_recall.py"])

print()
print("=" * 70)
print("汇总：")
fails = [x for x in RESULTS if not x[1]]
print(f"  共 {len(RESULTS)} 项，通过 {len(RESULTS)-len(fails)}，失败 {len(fails)}")
for f in fails:
    print(f"  ✗ {f[0]}: {f[3]}")
