"""报告体检规则测试（mra.checks）。

    python tests/test_checks.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mra.checks import check_report, parse_report  # noqa: E402

GOOD = """## 一、执行摘要
规模 58 亿元[1]，增速 18%[2]。

## 二、市场规模与增长
[1]

## 三、竞争格局
[2]

## 四、目标用户与需求洞察
[1][2]

## 五、驱动因素与趋势
[2]

## 六、风险与不确定性
材料未覆盖，待核实[1]。

## 七、结论与行动建议
P0 补齐数据[1]。

## 参考来源

1. 来源一（2025） — https://a.example/1
2. 来源二（2025） — https://a.example/2
""" + ("正文填充。" * 800)


class TestParse(unittest.TestCase):
    def test_split_and_counts(self):
        p = parse_report(GOOD)
        self.assertEqual(p["web"], [1, 2])
        self.assertEqual(p["cited_web"], {1, 2})
        self.assertEqual(len(p["chapters"]), 7)

    def test_kb_numbers(self):
        doc = GOOD.replace("## 参考来源\n", "## 参考来源\n\nK1. 旧报告 — kb://1\n")
        doc = doc.replace("规模 58 亿元[1]", "规模 58 亿元[1][K1]")
        p = parse_report(doc)
        self.assertEqual(p["kb"], [1])
        self.assertEqual(p["cited_kb"], {1})


class TestCheck(unittest.TestCase):
    def test_good_report_passes(self):
        r = check_report(GOOD)
        self.assertTrue(r["ok"], r["problems"])
        self.assertEqual(r["metrics"]["ratio"], 1.0)
        self.assertEqual(r["metrics"]["web"], 2)

    def test_dangling_reference(self):
        bad = GOOD.replace("增速 18%[2]", "增速 18%[7]")
        r = check_report(bad)
        self.assertFalse(r["ok"])
        self.assertTrue(any("悬空引用" in p for p in r["problems"]))

    def test_fabricated_mark(self):
        bad = GOOD.replace("规模 58 亿元[1]", "规模 58 亿元[搜索A]")
        r = check_report(bad)
        self.assertFalse(r["ok"])
        self.assertTrue(any("自造引用标注" in p for p in r["problems"]))

    def test_marker_leak(self):
        bad = GOOD + "\n引用清单：1, 2"
        r = check_report(bad)
        self.assertFalse(r["ok"])
        self.assertTrue(any("泄漏" in p for p in r["problems"]))

    def test_too_short(self):
        r = check_report("## 一、执行摘要\n一句话。", min_chars=3000)
        self.assertFalse(r["ok"])
        self.assertTrue(any("过短" in p for p in r["problems"]))

    def test_missing_sources_section(self):
        bad = GOOD.split("## 参考来源")[0] + ("填充。" * 1200)
        r = check_report(bad)
        self.assertFalse(r["ok"])
        self.assertTrue(any("参考来源" in p for p in r["problems"]))

    def test_low_citation_ratio(self):
        # 来源表 4 条，正文只引 1 条 → 25% < 60%
        doc = GOOD.replace(
            "1. 来源一（2025） — https://a.example/1",
            "1. 来源一（2025） — https://a.example/1\n2. 二 — https://a/2\n3. 三 — https://a/3\n4. 四 — https://a/4")
        doc = doc.replace("[2]", "[1]")
        r = check_report(doc)
        self.assertFalse(r["ok"])
        self.assertTrue(any("利用率" in p for p in r["problems"]))

    def test_thresholds_configurable(self):
        short = "## 一、x\n[1]\n## 参考来源\n\n1. a — https://a"
        self.assertFalse(check_report(short)["ok"])
        self.assertTrue(check_report(short, min_chars=1, min_chapters=1)["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
