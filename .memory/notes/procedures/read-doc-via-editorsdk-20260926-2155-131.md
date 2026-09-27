---
id: 20260926-2155-131
type: procedure
status: active
title: 用 WorkBuddy editor_sdk 读取 .doc 老格式文档
tags: [doc, 提取, editor-sdk, 工具]
env: win32
hot: true
created: 2026-09-26
---

读取 .doc 老格式（olefile 提取乱码）的正规流程——用 WorkBuddy 内置编辑器通道，不装 LibreOffice。

## 背景

`.doc` 快速保存文档的文本定位不可靠，olefile 方案提取是乱码（is_clean_text 会拦截导致"提取失败"）。本机没装 LibreOffice。实际验证：**WorkBuddy 自带的 tencent-local-office-edit（editor_sdk）能完整读取 .doc**。

## 流程

```bash
SK="C:/Program Files/WorkBuddy/resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/skills/tencent-local-office-edit"
python3 "$SK/edsdk.py" list doc                        # 1. 验证工具可用
python3 "$SK/edsdk.py" call open_file file_path='<绝对路径>.doc'   # 2. 后台打开，file_id=路径本身
python3 "$SK/edsdk.py" call doc_get_table_info file_id='<路径>' idx=0   # 3. 读表格完整文本
python3 "$SK/edsdk.py" call close_file file_id='<路径>'              # 4. 释放后台实例
```

## 关键细节（踩过的坑）

- **doc_resolve_document_structure 的 text_preview 会截断**（即使传 text_preview_length=200 也只给约 10 字预览），拿不到完整单元格文本；**doc_get_table_info 返回完整 text 字段**——读内容必须用它
- open_file 后台模式（无用户预览）时 `file_id` 就是 `file_path` 字符串本身
- 表格定位三选一（table_id > idx > table_locate），idx=0 即可命中首个表格
- 批量场景：循环 open → read → close；写脚本用 subprocess 调 edsdk.py（中文路径在 Python 内部无 shell 转义问题）
- 每份 .doc 打开约 1-3 秒，10 份批量 <1 分钟

## 批量脚本参考

`C:/Users/Administrator/Documents/个人知识库/.memory/batch_read_docs.py`：循环读取指定目录所有 .doc，提取表格非空单元格按行输出。

## 适用范围与边界

- 适用：WorkBuddy 环境下的 .doc/.wps 老格式读取、表格类文档内容提取
- 其他格式别用它：.docx 用 python-docx、.pdf 用 pypdf、.xlsx 用 openpyxl（系统 Python C:/Python314 均有）
- 该通道是编辑型接口，读大文档注意分页/预览限制；核心内容用 doc_get_table_info

## 提炼工作流配套

从 F 盘文档提炼项目经验的完整链路：ingest.py 批量提取（docx/xlsx/pdf/md）→ 读块 → 对 .doc 走本流程 → 提炼 procedure 笔记（带 source 指针）→ reindex → hot 进热层。