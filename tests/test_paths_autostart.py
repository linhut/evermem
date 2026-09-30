#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

"""数据根目录与自启动能力的回归测试。

背景（真实踩坑）：
    以前 mem.py 按 PMEM_HOME 解析数据目录，server.py / backup.py / memimport.py /
    harvest.py 各自按 __file__ 推导。源码态代码与数据同目录，问题被掩盖；
    PyInstaller 单文件冻结态下 __file__ 落在临时解包目录，于是核心检索、界面配置、
    导入、备份恢复各指一个目录。全项目必须只认 paths.data_root()。

    自启动同理：浏览器模式没有系统自启权限，接口必须如实报 unsupported，
    否则前端开关点了没反应，属于典型假成功。

运行：python tests/test_paths_autostart.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import paths  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail and not ok else ''}")
    if not ok:
        FAILS.append(name)


class TestDataRoot(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pmem-paths-"))
        self.code = self.tmp / "code"
        self.data = self.tmp / "data"
        self.code.mkdir()
        self.data.mkdir()
        self._orig_code = paths.code_root
        self._orig_env = os.environ.get("PMEM_HOME")
        paths.code_root = lambda: self.code

    def tearDown(self):
        paths.code_root = self._orig_code
        if self._orig_env is None:
            os.environ.pop("PMEM_HOME", None)
        else:
            os.environ["PMEM_HOME"] = self._orig_env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_env_wins(self):
        print("\n一、环境变量优先级最高")
        (self.code / "pmem_config.json").write_text(
            json.dumps({"home": str(self.data)}), encoding="utf-8")
        os.environ["PMEM_HOME"] = str(self.tmp / "env")
        (self.tmp / "env").mkdir()
        check("PMEM_HOME 覆盖配置文件", paths.data_root().resolve() == (self.tmp / "env").resolve(),
              str(paths.data_root()))

    def test_config_home_used_when_env_absent(self):
        print("二、环境变量为空时用持久化配置的 home")
        os.environ.pop("PMEM_HOME", None)
        (self.code / "pmem_config.json").write_text(
            json.dumps({"home": str(self.data)}), encoding="utf-8")
        check("读取配置 home", paths.data_root().resolve() == self.data.resolve(), str(paths.data_root()))

    def test_config_file_location(self):
        print("三、配置文件写入位置恒为数据目录（界面与引擎共写同一处）")
        os.environ["PMEM_HOME"] = str(self.data)
        check("config_file 在数据目录", paths.config_file() == self.data / "pmem_config.json",
              str(paths.config_file()))

    def test_search_paths_include_data_root(self):
        print("四、读取顺序含数据目录与代码目录（兼容旧配置位置）")
        os.environ["PMEM_HOME"] = str(self.data)
        found = [str(p) for p in paths.config_search_paths()]
        check("首选项为数据目录", found[0] == str(self.data / "pmem_config.json"), str(found))
        check("兼容代码目录旧配置", str(self.code / "pmem_config.json") in found, str(found))

    def test_frozen_default_is_exe_dir_not_cwd(self):
        print("五、冻结态默认数据目录为可执行文件同级目录（不能用 cwd）")
        os.environ.pop("PMEM_HOME", None)
        orig_frozen = getattr(sys, "frozen", False)
        orig_exe = sys.executable
        try:
            sys.frozen = True
            sys.executable = str(self.data / "evergem.exe")
            got = paths._default_data_root()
            check("冻结态取 exe 同级目录", got.resolve() == self.data.resolve(), str(got))
        finally:
            if orig_frozen is False:
                try:
                    del sys.frozen
                except AttributeError:
                    pass
            else:
                sys.frozen = orig_frozen
            sys.executable = orig_exe


class TestAutostartApi(unittest.TestCase):
    def test_unsupported_outside_desktop_shell(self):
        print("\n六、非桌面壳运行时自启动必须报 unsupported")
        os.environ.pop("PMEM_DESKTOP", None)
        sys.path.insert(0, str(ROOT / "web"))
        try:
            import server  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            check("server 可导入", False, str(exc))
            return
        info = server._autostart_info()
        check("supported=False", info.get("supported") is False, str(info))
        check("给出原因", bool(info.get("reason")), str(info))

    def test_desktop_flag_gate(self):
        print("七、PMEM_DESKTOP 非 1 时不导入桌面模块")
        os.environ["PMEM_DESKTOP"] = "0"
        sys.path.insert(0, str(ROOT / "web"))
        import server  # noqa: PLC0415
        check("不导入 desktop", server._import_desktop_module() is None)
        os.environ.pop("PMEM_DESKTOP", None)

    def test_platform_branches_exist(self):
        print("八、跨平台自启动各平台分支存在（macOS 走 LaunchAgents，不是 XDG）")
        src = (ROOT / "desktop.py").read_text(encoding="utf-8")
        check("macOS 写 LaunchAgents plist", "Library\" / \"LaunchAgents" in src.replace('"', '"'))
        check("Linux 写 XDG autostart", ".config\" / \"autostart" in src.replace('"', '"'))
        check("未知平台抛错而非静默", "不支持开机自启" in src)


if __name__ == "__main__":
    unittest.main(verbosity=0, exit=False)
    print(f"\n失败 {len(FAILS)} 项" + (f"：{FAILS}" if FAILS else ""))
    sys.exit(1 if FAILS else 0)
