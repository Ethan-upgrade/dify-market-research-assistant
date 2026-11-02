"""选项归一化测试（mra.aliases）：用户写简体中文/英文也能落到合法枚举。

    python tests/test_aliases.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mra.aliases import normalize, MARKET_ALIASES, INDUSTRY_ALIASES, PURPOSE_ALIASES, TIME_ALIASES
from mra.config import (MARKET_OPTIONS, INDUSTRY_OPTIONS, PURPOSE_OPTIONS, TIME_OPTIONS, Scope)  # noqa: E402


def mkt(v):
    return normalize(v, MARKET_OPTIONS, MARKET_ALIASES, "地区")


class TestMarket(unittest.TestCase):
    def test_global(self):
        self.assertEqual(mkt("全球"), "不限（全球为主）")
        self.assertEqual(mkt("global"), "不限（全球为主）")

    def test_china(self):
        self.assertEqual(mkt("中国"), "中国大陆")
        self.assertEqual(mkt("中国大陆"), "中国大陆")

    def test_north_america(self):
        self.assertEqual(mkt("北美"), "北美")
        self.assertEqual(mkt("美国"), "北美")

    def test_exact_enum_passthrough(self):
        for opt in MARKET_OPTIONS:
            self.assertEqual(mkt(opt), opt)

    def test_unknown_raises(self):
        with self.assertRaises(ValueError) as ctx:
            mkt("火星")
        self.assertIn("不认识", str(ctx.exception))


class TestOthers(unittest.TestCase):
    def test_industry_education(self):
        self.assertEqual(normalize("教育", INDUSTRY_OPTIONS, INDUSTRY_ALIASES, "行业"), "教育")

    def test_purpose_all_to_overview(self):
        self.assertEqual(normalize("全部", PURPOSE_OPTIONS, PURPOSE_ALIASES, "目的"), "行业概览")
        self.assertEqual(normalize("综合", PURPOSE_OPTIONS, PURPOSE_ALIASES, "目的"), "行业概览")

    def test_time_shortcuts(self):
        self.assertEqual(normalize("3年", TIME_OPTIONS, TIME_ALIASES, "时间"), "近三年")
        self.assertEqual(normalize("近十年", TIME_OPTIONS, TIME_ALIASES, "时间"), "近十年")

    def test_empty_uses_first(self):
        self.assertEqual(mkt(""), MARKET_OPTIONS[0])


class TestScopeIntegration(unittest.TestCase):
    def test_scope_normalizes(self):
        s = Scope(market="全球", industry="教育", purpose="全部", time_range="3年")
        self.assertEqual(s.market, "不限（全球为主）")
        self.assertEqual(s.industry, "教育")
        self.assertEqual(s.purpose, "行业概览")
        self.assertEqual(s.time_range, "近三年")

    def test_scope_keeps_valid(self):
        s = Scope(market="北美", industry="科技", purpose="投资尽调")
        self.assertEqual(s.market, "北美")
        self.assertEqual(s.industry, "科技/软件/SaaS")
        self.assertEqual(s.purpose, "投资尽调")


if __name__ == "__main__":
    unittest.main(verbosity=2)
