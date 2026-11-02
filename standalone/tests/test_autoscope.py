"""智能范围推断测试（mra.autoscope）。

    python tests/test_autoscope.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mra import autoscope  # noqa: E402


class TestGuess(unittest.TestCase):
    def test_german_query(self):
        g = autoscope.guess("德语学习周期、学习方法与未来应用前景，尤其以职业为导向")
        self.assertEqual(g["industry"], "教育")
        self.assertEqual(g["purpose"], "行业概览")

    def test_pet_food(self):
        g = autoscope.guess("调研一下国内宠物烘焙粮市场，看看能不能做")
        self.assertEqual(g["industry"], "消费品/快消")
        self.assertEqual(g["market"], "中国大陆")

    def test_energy_north_america(self):
        g = autoscope.guess("北美家用储能还有机会吗，想投")
        self.assertEqual(g["industry"], "新能源/汽车")
        self.assertEqual(g["market"], "北美")

    def test_channel_and_region(self):
        g = autoscope.guess("东南亚跨境电商的支付渠道怎么打")
        self.assertEqual(g["market"], "东南亚")
        self.assertEqual(g["purpose"], "渠道策略")

    def test_time_hint(self):
        g = autoscope.guess("看看近五年国内咖啡市场")
        self.assertEqual(g["time_range"], "近五年")

    def test_no_hint_returns_empty(self):
        self.assertEqual(autoscope.guess("帮我看看这个"), {})


class _StubLLM:
    def __init__(self, out):
        self.out = out

    def chat(self, *a, **k):
        return self.out


class TestInfer(unittest.TestCase):
    def test_parses_json(self):
        out = '{"market":"北美","industry":"教育","purpose":"市场进入","time_range":"近三年","depth":"4"}'
        r = autoscope.infer("q", _StubLLM(out))
        self.assertEqual(r["market"], "北美")
        self.assertEqual(r["industry"], "教育")
        self.assertEqual(r["depth"], "4")

    def test_ignores_invalid_values(self):
        out = '{"market":"火星","industry":"教育","purpose":"随便"}'
        r = autoscope.infer("q", _StubLLM(out))
        self.assertNotIn("market", r)
        self.assertEqual(r["industry"], "教育")

    def test_garbage_returns_empty(self):
        self.assertEqual(autoscope.infer("q", _StubLLM("我觉得是教育行业")), {})

    def test_llm_error_returns_empty(self):
        class Boom:
            def chat(self, *a, **k):
                raise RuntimeError("x")
        self.assertEqual(autoscope.infer("q", Boom()), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
