# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# 前端静态契约冒烟：三类交叉验证，无浏览器依赖，可并入 check_all。
# 防住"悬空元素引用 / 内联函数缺失 / API 路由缺失"三类白页级 bug。
#
#   python frontend_smoke.py        # 运行并输出 PASS/FAIL
#   python frontend_smoke.py --list # 仅列出问题

import re
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
FAILS = []
# 前端已按模块拆分，检查需覆盖全部脚本，否则新模块的悬空引用会溜过
JS_FILES = sorted(WEB.glob("*.js"))
ALL_JS = "\n".join(f.read_text(encoding="utf-8") for f in JS_FILES)

def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail and not ok else ''}")
    if not ok:
        FAILS.append(name)

def main() -> int:
    js = ALL_JS
    html = (WEB / "index.html").read_text(encoding="utf-8")
    srv = (WEB / "server.py").read_text(encoding="utf-8")
    print(f"  扫描脚本：{', '.join(f.name for f in JS_FILES)}\n")

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

    print("四、事件委托契约（data-bk 动作必须在 dispatch 里有分支，否则点击静默失效）")
    emitted = set(re.findall(r'data-bk="([a-z-]+)"', js + html))
    handled = set(re.findall(r"case '([a-z-]+)':", js))
    dangling = emitted - handled
    check("点击动作均有处理分支", not dangling, f"无分支: {sorted(dangling)}")

    print("五、跨模块符号（channel.js 依赖 index.js 的全局工具是否仍存在）")
    util = set(re.findall(r"\b(toast|askConfirm|esc|post|apiOr|skeleton|emptyState|withBusy)\s*\(", js))
    util_declared = declared | const_arrow | {"toast", "askConfirm", "esc", "post", "apiOr", "skeleton", "emptyState", "withBusy"}
    missing_util = util - util_declared
    check("跨模块工具均可访问", not missing_util, f"缺: {sorted(missing_util)}")

    print(f"\n共 5 项，通过 {5 - len(FAILS)}，失败 {len(FAILS)}")
    return 1 if FAILS and "--list" not in sys.argv else 0

if __name__ == "__main__":
    sys.exit(main())
