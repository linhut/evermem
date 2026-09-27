---
id: 20260926-1825-111
type: lesson
status: active
title: 跑 gongwen-skill 必须用系统 Python 而非托管 Python
tags: [公文, python, 工具, 命令]
env: win32
created: 2026-09-26
---

调用 gongwen-skill 生成公文时，运行解释器必须用 `C:/Python314/python.exe`。

用托管的 `C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe` 会报 ModuleNotFoundError，因为它没有装 python-docx 与 pydantic，而 gongwen-skill 依赖这两个包。`python -m gongwen` 这种写法在该解释器下必然失败。

症状：命令看起来没写错，但一执行就报缺少 python-docx 或 pydantic。此时不要去改命令或重装，直接换解释器即可。

适用范围：Windows，gongwen-skill v1.12.x。其他需要 docx 处理的脚本同理，先确认解释器里有没有 python-docx。
