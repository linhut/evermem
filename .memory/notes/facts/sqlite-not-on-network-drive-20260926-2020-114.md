---
id: 20260926-2020-114
type: fact
status: active
title: SQLite 不能放网络盘 NAS 与 SMB NFS
tags: [sqlite, nas, 存储, 架构, 工具]
env: 通用
hot: true
created: 2026-09-26
---

SQLite 数据库**不能放在网络文件系统上**（NFS、SMB/CIFS、Azure Files、GlusterFS、CephFS、网络 PVC、对象存储 FUSE 挂载）。这是 SQLite 官方不支持的场景，不是性能建议。

原因：SQLite 依赖 POSIX fcntl() 建议锁，该机制在 NFS 上不可靠；WAL 模式用的 mmap 共享内存文件（-shm）部分 NFS 版本根本不支持。后果不是变慢，而是**数据库损坏**（典型报错 database disk image is malformed）。

真实案例：Open WebUI 文档要求"不是本地 SSD/NVMe 就改用 PostgreSQL"；opencode 用户在 NFS 家目录开两个会话即损坏数据库；Navidrome 维护者建议"数据库放本地 SSD，每天备份到 NFS"。

fsync 延迟对比：本地 NVMe 约 100 微秒，NFS 50–500 毫秒甚至数秒。异步驱动下大量并发 fsync 会瞬间打满连接池。

**正确做法**：数据库放本地磁盘，需要网络存储时只做定期备份。对应到本项目——索引必须本地，NAS 只放原始文档，笔记走 Git 同步而非网络共享。
