#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归测试：全新（空）数据根下索引与统计不能崩。

真实事故：v0.2.5 的 CI 冒烟日志里出现 `/api/stats Error: HTTP 500`。
排查下来是 mem.load_index() 里 `max(p.stat().st_mtime for p in NOTES.rglob("*.md"))`
在笔记目录为空时抛 `ValueError: max() iterable argument is empty`。
影响面很大——**任何新用户第一次打开程序**，统计诊断就是 500。
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mem  # noqa: E402


class EmptyDataRootTest(unittest.TestCase):
    """空数据根：索引齐全但不该抛异常。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pmem-empty-"))
        self.notes = self.tmp / "notes"
        self.index = self.tmp / "index.json"
        self._orig = (mem.NOTES, mem.INDEX_PATH)
        mem.NOTES = self.notes
        mem.INDEX_PATH = self.index
        # 目录存在但没有任何 .md：这正是"刚装好、还没记任何东西"的状态
        self.notes.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        mem.NOTES, mem.INDEX_PATH = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_index_empty_notes_dir(self):
        """空笔记目录：不能抛 ValueError，且索引结构完整。"""
        idx = mem.load_index(force=False)
        self.assertEqual(idx.get("doc_count"), 0)
        self.assertEqual(idx.get("docs"), {})
        self.assertIn("built_at", idx)

    def test_load_index_missing_notes_dir(self):
        """连笔记目录都不存在（极端情况）也要能建出空索引。"""
        shutil.rmtree(self.notes, ignore_errors=True)
        idx = mem.load_index(force=False)
        self.assertEqual(idx.get("doc_count"), 0)

    def test_existing_index_is_reused_when_no_notes(self):
        """已存在的索引在没有任何笔记时不应被判定为"过期需重建"。"""
        mem.build_index()
        mtime_before = self.index.stat().st_mtime_ns
        idx = mem.load_index(force=False)
        self.assertEqual(idx.get("doc_count"), 0)
        # 没有笔记 → mtime 不该变（重建会写盘，mtime 会变）
        self.assertEqual(self.index.stat().st_mtime_ns, mtime_before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
