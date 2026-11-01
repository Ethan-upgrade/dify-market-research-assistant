"""编号连续化测试（mra.tidy.renumber_citations）。

    python tests/test_renumber.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mra import tidy  # noqa: E402

SRC = """1. A — https://a/1
3. C — https://a/3
18. R — https://a/18"""


class TestRenumber(unittest.TestCase):
    def test_gaps_closed(self):
        body, src = tidy.renumber_citations("正文[1][3][18]。", SRC)
        self.assertEqual(body, "正文[1][2][3]。")
        self.assertIn("1. A", src)
        self.assertIn("2. C", src)
        self.assertIn("3. R", src)

    def test_multi_digit_not_partially_replaced(self):
        # [18] 不能被当成 [1] + 8，也不能把 [8] 误改
        body, _ = tidy.renumber_citations("甲[18] 乙[3]", SRC)
        self.assertEqual(body, "甲[3] 乙[2]")

    def test_kb_rows_kept(self):
        src = "K1. 旧报告 — kb://1\n2. B — https://a/2\n5. E — https://a/5"
        body, out = tidy.renumber_citations("内部[K1]，外部[2][5]", src)
        self.assertIn("[K1]", body)
        self.assertEqual(body.replace("[K1]", ""), "内部，外部[1][2]")
        self.assertTrue(out.startswith("K1."))

    def test_idempotent(self):
        once = tidy.renumber_citations("x[1][2][3]", SRC)
        twice = tidy.renumber_citations(*once)
        self.assertEqual(once, twice)

    def test_row_order_preserved_not_old_number_order(self):
        # 调用方已把引擎摘要排到最后：旧编号 1 / 18 / 5，新编号必须按行序 1 / 2 / 3
        src = "1. A — https://a\n18. R — https://r\n5. 引擎摘要 — Tavily answer 字段"
        body, out = tidy.renumber_citations("正文[1][18][5]", src)
        self.assertEqual(body, "正文[1][2][3]")
        lines = out.split("\n")
        self.assertTrue(lines[-1].startswith("3. 引擎摘要"))

    def test_no_sources_noop(self):
        body, src = tidy.renumber_citations("没有来源[1]", "")
        self.assertEqual(body, "没有来源[1]")
        self.assertEqual(src, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
