# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# 恒忆 Evermem · 全面功能检查清单（正常 + 边界/异常）
# 逐项验证：可调用、无报错、结果完整、异常正确处理
#

import json
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]  # 项目根（scripts/ 的上一级）
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
import mem  # noqa: E402
PY = r"C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SYS = r"C:/Python314/python.exe"

RESULTS = []  # (功能, 状态, 说明)

def check(name, ok, note=""):
    RESULTS.append((name, ok, note))
    print(f"[{'OK ' if ok else 'FAIL'}] {name}  {note[:70]}")

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
ok, out, ms = run([PY, "scripts/ingest.py", "list", "F:/机房搬迁"])
check("list（正常目录）", ok)
ok, out, ms = run([PY, "scripts/ingest.py", "list", "F:/不存在的目录xyz"])
check("list（不存在目录→不崩溃）", ok)
ok, out, ms = run([PY, "scripts/ingest.py", "extract", "F:/机房搬迁", "--out-dir", str(BASE / "tmp_chk"), "--show-failed"])
check("extract（正常，含失败统计）", ok and "成功" in out)

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
def api(path, method="GET", body=None):
    c = _hc.HTTPConnection("127.0.0.1", 8765, timeout=15)
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
st, body = api("/api/doesnotexist")
check("GET 未知路径→404", st == 404)
st, body = api("/api/note", "POST", {"title": ""})
check("POST /api/note（空标题→400）", st == 400)
st, body = api("/api/note", "POST", {"title": "边界测试笔记", "body": "x"})
check("POST /api/note（正常新建）", st == 200 and "staged" in body)
if st == 200:
    nid = None
    try:
        nid = json.loads(body).get("id")
    except (ValueError, TypeError):
        pass
    if nid:
        # 清理测试残留，避免污染正式库（Web 新建的笔记是 staged 测试笔记）
        test_path = BASE / "notes" / "lessons" / f"web-{nid}.md"
        if test_path.exists():
            test_path.unlink()
            mem.build_index()

print()
print("六、前端与数据健康")
ok, out, ms = run([PY, "scripts/frontend_smoke.py"])
check("前端静态契约冒烟（元素/函数/路由）", ok)
ok, out, ms = run(["C:/Program Files/nodejs/node.exe", "--check", "web/index.js"])
check("index.js 语法", ok)
ok, out, ms = run([PY, "-m", "py_compile", "web/server.py", "web/launcher.py", "evermem_mcp.py", "mem.py", "scripts/ingest.py", "harvest.py", "scripts/knowledge_scan.py"])
check("全部 Python 语法", ok)

print()
print("=" * 72)
fails = [r for r in RESULTS if not r[1]]
print(f"总检查 {len(RESULTS)} 项 | 通过 {len(RESULTS) - len(fails)} | 失败 {len(fails)}")
for f in fails:
    print(f"  ✗ {f[0]}: {f[2]}")
