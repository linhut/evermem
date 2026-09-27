---
id: 20260925-2250-dab4e14c
type: lesson
status: staged
title: [候选] Bash 失败后成功：Bash:ls "<path>"
tags: [自动收割, 待验证]
env: win32
created: 2026-09-25
---

工具：Bash
命令签名：Bash:ls "<path>"
首次命令：ls "C:/Users/Administrator/Documents/个人知识库/.workbuddy"

失败次数：1
失败输出片段：
```
Command: ls "C:/Users/Administrator/Documents/个人知识库/.workbuddy"
Stdout: (empty)
Stderr: ls: cannot access 'C:/Users/Administrator/Documents/个人知识库/.workbuddy': No such file or directory

Exit Code: 2
Signal: (none)
```

随后成功命令：
```
ls "C:/Users/Administrator/Documents/个人知识库"
```

成功输出片段：
```
Command: ls "C:/Users/Administrator/Documents/个人知识库"
Stdout: reports

Stderr: (empty)
Exit Code: 0
Signal: (none)
```

来源会话：2b295ff5-2e2b-499b-8d3d-1d9c14c90fb7
来源 callId：chatcmpl-tool-fa6d4c3588118d1a
