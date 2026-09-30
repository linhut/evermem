#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# paths - 恒忆「代码目录 / 数据目录」唯一解析入口
#
# 为什么单独一个模块：
#   以前 mem.py 按 PMEM_HOME 解析数据目录，而 server.py / backup.py / memimport.py /
#   harvest.py 各自按 __file__ 推导。源码态代码与数据同目录，问题被掩盖；
#   PyInstaller 单文件冻结态下 __file__ 落在临时解包目录，于是出现
#   「核心检索读 A 目录、界面配置写 B 目录、导入写 C 目录、备份恢复写 D 目录」的分裂。
#   全项目必须只认本文件，别处不得再用 __file__ 推导数据位置。
#
# 优先级：环境变量 > 持久化配置 > 可移植默认目录
#   · PMEM_HOME                显式指定，最高优先级
#   · <数据目录>/pmem_config.json 的 home 字段（界面「数据位置」写入，跨会话一致）
#   · 冻结态：可执行文件同级目录（可移植：exe 与数据放一起即可）
#     源码态：本文件所在目录
#
# 代码目录（code_root）只用于定位模板、脚本与前端资源；冻结态下可能是临时解包目录，
# 绝不能作为用户数据或配置的写入位置。

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CONFIG_NAME = "pmem_config.json"


def code_root() -> Path:
    """代码目录：模板 / 脚本 / 前端资源所在处（冻结态可能是临时解包目录）。"""
    return Path(__file__).resolve().parent


def _default_data_root() -> Path:
    """可移植默认数据目录：打包产物用 exe 同级目录，源码用代码目录。

    不用 cwd —— 双击 exe、开机自启、从资源管理器启动时 cwd 各不相同，
    用 cwd 会让同一份数据在不同启动方式下落到不同位置。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return code_root()


def config_search_paths() -> list[Path]:
    """配置文件读取顺序：数据目录优先，其次代码目录（兼容旧版本写在代码目录的配置）。"""
    roots: list[Path] = []
    env = os.environ.get("PMEM_HOME", "").strip()
    if env:
        roots.append(Path(env).expanduser())
    roots.append(_default_data_root())
    legacy = code_root()
    if legacy not in roots:
        roots.append(legacy)
    out: list[Path] = []
    for r in roots:
        p = r / CONFIG_NAME
        if p not in out:
            out.append(p)
    return out


def config_file() -> Path:
    """配置文件写入位置：恒为数据目录下的 pmem_config.json（界面与引擎共写同一处）。"""
    return data_root() / CONFIG_NAME


def load_config() -> dict:
    """读取持久化配置（找不到或坏了返回空字典，不抛异常）。"""
    for p in config_search_paths():
        try:
            cfg = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, ValueError):
            continue
        if isinstance(cfg, dict):
            return cfg
    return {}


def data_root() -> Path:
    """数据目录：全项目唯一入口。"""
    env = os.environ.get("PMEM_HOME", "").strip()
    if env:
        try:
            return Path(env).expanduser().resolve()
        except (OSError, RuntimeError):
            pass
    home = str(load_config().get("home") or "").strip()
    if home:
        try:
            return Path(home).expanduser().resolve()
        except (OSError, RuntimeError):
            pass
    return _default_data_root()
