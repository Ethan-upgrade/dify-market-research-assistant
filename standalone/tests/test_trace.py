"""数字溯源测试（mra.trace）——用桩替换网络。

    python tests/test_trace.py
"""

import os
import sys

os.environ.setdefault("MRA_FETCH_TTL", "0")   # 测试不读生产缓存
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mra import trace  # noqa: E402

REPORT = """## 一、市场规模

| 指标 | 数值 | 年份 | 来源 |
|---|---|---|---|
| 市场规模 | 58.3 亿元 | 2024 | [1] |
| 增速 | 18.4% | 2024 | [2] |
| 装机 | 1,640 MWh（同比 +7%） | 2023 | [1] |

## 参考来源

1. 甲报告 — https://a.example/1
2. 乙报告 — https://b.example/2
"""


class TestNumbers(unittest.TestCase):
    def test_skips_years(self):
        self.assertEqual(trace.numbers_in("2024 年规模 58.3 亿元"), ["58.3"])

    def test_keeps_decimals_and_commas(self):
        self.assertEqual(trace.numbers_in("1,640 MWh"), ["1640"])

    def test_skips_zero_and_small(self):
        # 单个 0 不参与比对
        self.assertNotIn("0", trace.numbers_in("增长 0%"))

    def test_tolerance(self):
        pages = {58.3, 18.4, 1640.0}
        self.assertTrue(trace.hit("58.30", pages))
        self.assertTrue(trace.hit("1640", pages))
        self.assertFalse(trace.hit("99", pages))


class TestTables(unittest.TestCase):
    def test_parses_header_and_rows(self):
        tbs = trace.tables(REPORT)
        self.assertEqual(len(tbs), 1)
        self.assertEqual(tbs[0]["header"][0], "指标")
        self.assertEqual(len(tbs[0]["rows"]), 3)

    def test_extract_claims_maps_source(self):
        claims = trace.extract_claims(REPORT)
        self.assertEqual(len(claims), 3)
        by_row = {c["row"]: c for c in claims}
        self.assertEqual(by_row["市场规模"]["cite"], "1")
        self.assertIn("58.3", by_row["市场规模"]["numbers"])
        self.assertEqual(by_row["增速"]["cite"], "2")

    def test_ignores_table_without_source_column(self):
        md = "| 指标 | 数值 |\n|---|---|\n| x | 1 |\n"
        self.assertEqual(trace.extract_claims(md), [])


class TestCheck(unittest.TestCase):
    def test_all_verified(self):
        pages = {58.3: True}
        with mock.patch.object(trace, "fetch_text", side_effect=lambda u, t=15, f="auto": {
                "ok": True, "reason": "", "text": "市场规模 58.3 亿元，增速 18.4%，装机 1,640 MWh 同比 7%"}):
            res = trace.check(REPORT)
        self.assertEqual(res["not_found"], 0)
        self.assertEqual(res["verified"], 3)
        self.assertEqual(res["ratio"], 1.0)

    def test_missing_number_flagged(self):
        with mock.patch.object(trace, "fetch_text", side_effect=lambda u, t=15, f="auto": {
                "ok": True, "reason": "", "text": "市场规模 58.3 亿元"}):
            res = trace.check(REPORT)
        self.assertGreater(res["not_found"], 0)
        self.assertLess(res["ratio"], 1.0)

    def test_unreachable(self):
        with mock.patch.object(trace, "fetch_text", side_effect=lambda u, t=15, f="auto": {
                "ok": False, "reason": "HTTP 403", "text": ""}):
            res = trace.check(REPORT)
        self.assertEqual(res["unreachable"], 3)
        self.assertEqual(res["ratio"], 0.0)

    def test_pdf_reason(self):
        with mock.patch.object(trace, "fetch_text", side_effect=lambda u, t=15, f="auto": {
                "ok": False, "reason": "PDF 无法直接比对", "text": ""}):
            res = trace.check(REPORT)
        self.assertTrue(all("PDF" in r["reason"] for r in res["rows"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
