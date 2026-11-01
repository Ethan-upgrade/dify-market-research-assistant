"""确定性引用整理测试（mra.tidy）。

这些规则不依赖模型，必须百分百可预测——所以每一条都单独锁死。

    python tests/test_tidy.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mra import tidy  # noqa: E402


class TestCollapseRuns(unittest.TestCase):
    def test_three_or_more_collapsed(self):
        self.assertEqual(tidy.collapse_citation_runs("规模[1][2][3]"), "规模[1][2]")

    def test_dedupes_within_run(self):
        self.assertEqual(tidy.collapse_citation_runs("[15][16][18][15][16]"), "[15][16]")

    def test_two_left_alone(self):
        self.assertEqual(tidy.collapse_citation_runs("[3][5]"), "[3][5]")

    def test_single_left_alone(self):
        self.assertEqual(tidy.collapse_citation_runs("[7]"), "[7]")

    def test_multiple_runs(self):
        got = tidy.collapse_citation_runs("[1][2][3] 中间文字 [4][5][6][7]")
        self.assertEqual(got, "[1][2] 中间文字 [4][5]")

    def test_kb_citations(self):
        self.assertEqual(tidy.collapse_citation_runs("[K1][K2][K3]"), "[K1][K2]")

    def test_no_citation_untouched(self):
        s = "没有引用的一段话，还有 [待核实] 这种方括号。"
        self.assertEqual(tidy.collapse_citation_runs(s), s)


class TestTableCells(unittest.TestCase):
    def test_strips_cell_citations_when_source_column_filled(self):
        doc = "| 指标 | 数值 | 来源 |\n|---|---|---|\n| 规模 | 58[3]亿元[3] | [3] |"
        out = tidy.strip_table_cell_citations(doc)
        self.assertIn("| 规模 | 58亿元 | [3] |", out)

    def test_keeps_source_column(self):
        doc = "| 指标 | 数值 | 来源 |\n|---|---|---|\n| x | 1[4] | [4][5] |"
        out = tidy.strip_table_cell_citations(doc)
        self.assertIn("[4][5]", out)
        self.assertIn("| x | 1 |", out)

    def test_no_source_column_untouched(self):
        doc = "| 指标 | 数值 |\n|---|---|\n| x | 1[4] |"
        self.assertEqual(tidy.strip_table_cell_citations(doc), doc)

    def test_empty_source_column_untouched_by_tidy(self):
        # 来源列空着 → 不动单元格（交给体检报告问题，不擅自删出处）
        doc = "| 指标 | 数值 | 来源 |\n|---|---|---|\n| x | 1[4] |  |"
        self.assertEqual(tidy.strip_table_cell_citations(doc), doc)

    def test_non_table_text_untouched(self):
        doc = "正文里 58 亿元[3]，表格之外不动。"
        self.assertEqual(tidy.strip_table_cell_citations(doc), doc)


class TestTidy(unittest.TestCase):
    def test_combined(self):
        doc = ("## 一、规模\n"
               "规模 58 亿元[3][4][5]。\n\n"
               "| 指标 | 数值 | 来源 |\n|---|---|---|\n| 规模 | 58[3]亿元 | [3] |\n\n"
               "## 参考来源\n\n3. a — https://a/3\n4. b — https://a/4\n5. c — https://a/5")
        out = tidy.tidy(doc)
        self.assertIn("规模 58 亿元[3][4]。", out)
        self.assertIn("| 规模 | 58亿元 | [3] |", out)

    def test_idempotent(self):
        doc = "规模[1][2][3] 和 | a | 1[4] | [4] |"
        once = tidy.tidy(doc)
        self.assertEqual(tidy.tidy(once), once)


if __name__ == "__main__":
    unittest.main(verbosity=2)
