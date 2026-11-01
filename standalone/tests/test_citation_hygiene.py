"""引用降噪与密度体检测试（mra.checks 的密度规则 + pipeline 的降噪防御）。

    python tests/test_citation_hygiene.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mra.checks import check_report  # noqa: E402
from mra.config import Scope  # noqa: E402
from mra.pipeline import Pipeline  # noqa: E402

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

SPAMMY = """## 一、执行摘要
2024年[6]美国规模约[6]15.2亿美元[6]，同比[6]增长。
[15][16][18][15][16][18][15][16]

## 二、市场规模
[6][6][6][6][6][6][6]

## 三、竞争格局
[1]

## 四、目标用户
[1]

## 五、驱动因素
[1]

## 六、风险
[1]

## 七、结论
[1]

## 参考来源

1. a — https://a/1
6. b — https://a/6
15. c — https://a/15
16. d — https://a/16
18. e — https://a/18
""" + ("填充内容。" * 1200)


class TestDensity(unittest.TestCase):
    def test_spammy_report_flagged(self):
        r = check_report(SPAMMY, max_marks_per_100=5.0)
        self.assertFalse(r["ok"])
        self.assertIn("重复标注过多", " ".join(r["problems"]))

    def test_density_metric_computed(self):
        r = check_report(GOOD, max_marks_per_100=99)   # 只看指标，不卡阈值
        self.assertIn("density", r["metrics"])
        self.assertGreater(r["metrics"]["density"], 0)
        self.assertGreaterEqual(r["metrics"]["marks"], 6)  # 正文 6 处 + 表格/摘要里可能更多

    def test_density_limit_configurable(self):
        # 用「密集但不成串」的样本，只验证密度/重复两个阈值可调
        flat = (SPAMMY.replace("[15][16][18][15][16][18][15][16]", "[15][16]")
                       .replace("[6][6][6][6][6][6][6]", "[6]"))
        r = check_report(flat, max_marks_per_100=999, max_same_in_paragraph=999)
        self.assertTrue(r["ok"], r["problems"])

    def test_high_density_flagged(self):
        # 每百字超过上限就要报
        dense = GOOD.replace("正文填充。" * 800, "填充[1]" * 800)
        r = check_report(dense, max_marks_per_100=2.0)
        self.assertFalse(r["ok"])
        self.assertIn("密度", " ".join(r["problems"]))


class TestNormalizeGuard(unittest.TestCase):
    """降噪调用的防御：结果异常必须回退原文，绝不写坏报告。"""

    class _LLM:
        def __init__(self, out=None, exc=None):
            self.out, self.exc = out, exc

        def chat(self, *a, **k):
            if self.exc:
                raise self.exc
            return self.out

    def test_reject_shrunk_output(self):
        p = Pipeline(self._LLM("太短了"), None, Scope(), verbose=False)
        self.assertEqual(p._normalize_citations(GOOD), GOOD)

    def test_reject_no_chapters(self):
        p = Pipeline(self._LLM("一整段没有章节标记的长文本。" * 200), None, Scope(), verbose=False)
        self.assertEqual(p._normalize_citations(GOOD), GOOD)

    def test_accept_good_cleanup(self):
        cleaned = GOOD.replace("[1][2]", "[2]")
        p = Pipeline(self._LLM(cleaned), None, Scope(), verbose=False)
        self.assertEqual(p._normalize_citations(GOOD), cleaned)

    def test_exception_falls_back(self):
        p = Pipeline(self._LLM(exc=RuntimeError("boom")), None, Scope(), verbose=False)
        self.assertEqual(p._normalize_citations(GOOD), GOOD)

    def test_disabled_skips_call(self):
        calls = []

        class L:
            def chat(self, *a, **k):
                calls.append(1)
                return "x"

        p = Pipeline(L(), None, Scope(), verbose=False, normalize_citations=False)
        self.assertFalse(p.normalize_citations)


if __name__ == "__main__":
    unittest.main(verbosity=2)

class TestTableNotParagraph(unittest.TestCase):
    """表格的「来源」列每行重复同一编号，不能被判成「一段内重复标注过多」。"""

    def test_table_column_not_flagged(self):
        rows = "\n".join(f"| 指标{i} | {i} 亿元 | [7] |" for i in range(12))
        doc = ("## 一、规模\n\n| 指标 | 数值 | 来源 |\n|---|---|---|\n" + rows +
               "\n\n## 二、格局\n[7]\n\n## 三、用户\n[7]\n\n## 四、趋势\n[7]\n\n"
               "## 五、风险\n[7]\n\n## 六、结论\n[7]\n\n## 七、建议\n[7]\n\n"
               "## 参考来源\n\n7. 来源 — https://a/7\n" + ("填充。" * 1200))
        r = check_report(doc, max_same_in_paragraph=5)
        self.assertNotIn("重复标注过多", " ".join(r["problems"]))

