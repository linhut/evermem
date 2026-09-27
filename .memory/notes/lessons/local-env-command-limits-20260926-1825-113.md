---
id: 20260926-1825-113
type: lesson
status: active
title: 本机命令执行的两条环境限制
tags: [环境, 沙箱, 安全策略, 命令]
env: win32
created: 2026-09-26
---

一、回收站接口不可用。`Add-Type` 编译 .NET 与 COM 对象实例化都被安全策略拦截，所以无法走"删除到回收站"。要删除文件只能直接删，**必须先备份再二次确认**。

二、命令行里包含长段中文会被沙箱拦截，报错形如 `sandbox-center cmd decisionRecord missing actual resource subject`。短命令带中文路径没问题，但把大段中文正文当 shell 参数就会失败。绕行办法：改用文件写入工具先建文件，再让脚本读文件处理。

适用范围：WorkBuddy 桌面端 + Git Bash。写脚本或批量处理中文内容时优先走文件，不要拼长命令。
