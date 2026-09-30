# -*- mode: python ; coding: utf-8 -*-
# 恒忆 Evermem 桌面壳 PyInstaller spec（与 .github/workflows/build.yml 等价）。
# 本地使用：pyinstaller Evermem.spec

import sys

a = Analysis(
    ['desktop.py'],
    pathex=['web'],
    binaries=[],
    # VERSION 与 scripts/ 必须随包分发：冻结态下 CODE_ROOT 指向临时解包目录，
    # 版本显示、文档导入（scripts/ingest.py）、收割/热层同步都以子进程方式引用这些资源。
    datas=[('web', 'web'), ('templates', 'templates'), ('VERSION', '.'), ('scripts', 'scripts')],
    hiddenimports=['paths'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

icon = None
if sys.platform == 'win32':
    icon = 'assets/icon.ico'
elif sys.platform == 'darwin':
    icon = 'assets/icon.icns'

version_file = 'assets/version_info.txt' if sys.platform == 'win32' else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Evermem',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
    version=version_file,
)
