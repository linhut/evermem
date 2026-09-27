---
id: 20260925-2250-108
type: lesson
status: active
title: 会话收割器的四个调优陷阱
tags: [自动收割, harvest, 调优, 经验]
env: win32
created: 2026-09-25
---

从会话 jsonl 自动挖试错模式时踩过的坑，按踩坑顺序记：

一、arguments 可能是 JSON 字符串而不是对象。直接取 arguments.command 会拿到 None，若退化成返回整个字符串，签名就会变成一整段 JSON，完全不可读。必须先尝试 json.loads 再取字段。

二、用"输出里含 error 字样"判定失败，噪声极大。第一版采到 57 条"失败"，绝大多数是 WebFetch 抓回来的网页正文里恰好有 error 一词。改成只认执行状态加严格报错行（command not found、permission denied、traceback、sandbox-center、program blocked 等，且只看输出前 12 行）后降到 10 条。

三、门槛调高会漏掉真信号。要求同一签名失败两次时，候选变成 0 组——因为真实踩坑常常是"失败一次就换方法"，不是同一条命令反复失败。所以候选条件应是"同签名多次失败"或"命中高价值错误指纹（即使只失败一次）"，而不是单一门槛。

四、命令签名必须归一化到结构层。路径、数字、UUID、长度超过 24 的引号内字符串都要掩码，否则每条命令都独一无二，永远聚合不出模式。

结论：候选一律写 status=staged，绝不直接进 active。自动收割的定位是"把可疑信号挑给人看"，不是"精确判定失败"。
