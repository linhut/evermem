# -*- coding: utf-8 -*-
# 前端静态契约冒烟：三类交叉验证，无浏览器依赖，可并入 check_all。
# 防住"悬空元素引用 / 内联函数缺失 / API 路由缺失"三类白页级 bug。
#
#   python frontend_smoke.py        # 运行并输出 PASS/FAIL
#   python frontend_smoke.py --list # 仅列出问题

import re
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web"
FAILS = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail and not ok else ''}")
    if not ok:
        FAILS.append(name)


def main() -> int:
    js = (WEB / "index.js").read_text(encoding="utf-8")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    srv = (WEB / "server.py").read_text(encoding="utf-8")

    print("一、元素引用交叉验证（JS 引用的 #id 是否都有定义）")
    refs = set(re.findall(r"\$\(['\"]#([A-Za-z0-9_-]+)['\"]\)", js))
    refs |= set(re.findall(r"getElementById\(['\"]([A-Za-z0-9_-]+)['\"]\)", js))
    defined = set(re.findall(r'id="([A-Za-z0-9_-]+)"', html))
    defined |= set(re.findall(r'id="([A-Za-z0-9_-]+)"', js))
    missing = refs - defined
    check("无悬空元素引用", not missing, f"缺: {sorted(missing)}")

    print("二、内联 onclick 函数全局性（const 箭头函数被内联调用会 ReferenceError）")
    calls = set(re.findall(r'onclick="([A-Za-z_][A-Za-z0-9_]*)\(', js + html))
    declared = set(re.findall(r"(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", js))
    const_arrow = set(re.findall(r"const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\(", js))
    bad = (calls & const_arrow) | (calls - declared - const_arrow)
    check("内联函数均可访问", not bad, f"问题: {sorted(bad)}")

    print("三、API 路径契约（前端请求 vs 后端路由）")
    paths = set(re.findall(r"fetch\(['\"](\/api\/[A-Za-z0-9_\/-]+)", js))
    paths |= set(re.findall(r"post\(['\"](\/api\/[A-Za-z0-9_\/-]+)", js))
    routes = set(re.findall(r'p == "(\/api\/[A-Za-z0-9_\/-]+)"', srv))
    routes |= set(re.findall(r'p\.startswith\("(\/api\/[A-Za-z0-9_\/-]+)"', srv))
    missing_api = {p for p in paths if p not in routes and not any(p.startswith(r) for r in routes)}
    check("API 路径均有路由", not missing_api, f"缺路由: {sorted(missing_api)}")

    print(f"\n共 3 项，通过 {3 - len(FAILS)}，失败 {len(FAILS)}")
    return 1 if FAILS and "--list" not in sys.argv else 0


if __name__ == "__main__":
    sys.exit(main())