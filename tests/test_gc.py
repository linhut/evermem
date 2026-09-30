#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 回归测试：GC T3 冷存批次选择（防止"冷存最新、保留最老"的方向回归）
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mem


class GcT3BatchTest(unittest.TestCase):
    def _rows(self, n, oldest_days=400, now=None):
        """构造 n 条归档行：第 i 条 created 距 now 为 oldest_days - i 天（i 越大越新）。"""
        import time
        now = now or time.time()
        rows = []
        for i in range(n):
            created = time.strftime("%Y-%m-%d", time.localtime(now - (oldest_days - i) * 86400))
            p = Path(tempfile.gettempdir()) / f"cand-fake-{i}.md"
            rows.append((p, {"created": created}))
        return rows

    def test_batch_is_oldest_not_newest(self):
        """冷存的必须是最老的一批；保留的必须是最新 keep_n 条。"""
        import time
        now = time.time()
        rows = self._rows(10, oldest_days=400, now=now)
        batch = mem.gc_t3_batch(rows, keep_n=3, trig_size=False, now=now)
        kept = [r for r in rows if r not in batch]
        # 断言：冷存批次的最大年龄 ≥ 保留集的最大年龄（即冷存更老）
        batch_oldest = min(mem.gc_file_age_days(p, now) for p, _ in batch)
        kept_newest = max(mem.gc_file_age_days(p, now) for p, _ in kept)
        self.assertGreaterEqual(batch_oldest, kept_newest,
                                "冷存批次应比保留集更老；若反了说明切片方向又写反")
        self.assertEqual(len(batch), 7)
        self.assertEqual(len(kept), 3)

    def test_trig_size_cold_stores_oldest_quarter(self):
        """仅容量触发且条数不足时，冷存最老 1/4。"""
        import time
        now = time.time()
        rows = self._rows(8, oldest_days=300, now=now)
        batch = mem.gc_t3_batch(rows, keep_n=8, trig_size=True, now=now)
        self.assertGreater(len(batch), 0)
        # 冷存的应比剩余的最老
        kept = [r for r in rows if r not in batch]
        if kept:
            batch_oldest = min(mem.gc_file_age_days(p, now) for p, _ in batch)
            kept_newest = max(mem.gc_file_age_days(p, now) for p, _ in kept)
            self.assertGreaterEqual(batch_oldest, kept_newest)

    def test_keep_all_when_under_limit(self):
        import time
        now = time.time()
        rows = self._rows(5, oldest_days=200, now=now)
        batch = mem.gc_t3_batch(rows, keep_n=10, trig_size=False, now=now)
        self.assertEqual(batch, [])


if __name__ == "__main__":
    unittest.main()
