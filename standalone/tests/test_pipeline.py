"""编排层测试：用桩替掉 LLM 与检索，离线验证整条链路。

覆盖：正常成稿、追问分支、跑题拦截、轮数上限、引用表裁剪。
不联网、不需要 Key，可进 CI。

    python tests/test_pipeline.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mra.config import Scope  # noqa: E402
from mra.pipeline import Pipeline  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "corpus.json")

BRIEF_OK = """<!--READY-->
调研主题：胶囊咖啡在中国市场的竞争格局
所属行业：消费品/快消
目标市场：中国大陆
目标客群：一二线城市白领
调研目的：新品立项
时间范围：近三年
核心问题：
1. 市场规模与增速
2. 竞争格局与份额
初始检索式1：中国 胶囊咖啡 市场规模 增速
初始检索式2：中国 胶囊咖啡 竞争格局 市场份额
待确认：无"""

ANALYZE_MORE = """【本轮新增要点】
- 2024 年市场规模约 58 亿元（来源 [1]）
- Nespresso 高端家用份额约 34%（来源 [2]）
【覆盖度】
缺：渠道结构
【下一轮检索式】
QUERY1: 胶囊咖啡 渠道 电商 占比
QUERY2: 胶囊咖啡 线下 体验店 转化"""

ANALYZE_DONE = """【本轮新增要点】
- 渠道以电商为主，占比约 52%（来源 [3]）
【覆盖度】
够：可以成稿
【下一轮检索式】
DONE"""

REPORT_OK = """## 一、执行摘要
市场规模约 58 亿元[1]，高端家用 Nespresso 份额约 34%[2]，电商渠道为主[3]。

## 二、市场规模与增长
…[1]

## 三、竞争格局
…[2]

## 四、目标用户与需求洞察
…[1][2]

## 五、驱动因素与趋势
…[3]

## 六、风险与不确定性
材料未覆盖，待核实。

## 七、结论与行动建议
P0：补齐渠道数据[3]。

引用清单：1, 2, 3"""


class StubLLM:
    """按顺序回放预设回答，记录调用次数。"""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        self.tokens = 0

    def chat(self, system, user, temperature=None, max_tokens=None):
        self.calls += 1
        self.tokens += 100
        if not self.replies:
            return "DONE"
        return self.replies.pop(0)


class StubBackend:
    def __init__(self, results_per_query=1, answer=""):
        self.calls = 0
        self.answer = answer
        self.results_per_query = results_per_query

    def search(self, query):
        import hashlib
        self.calls += 1
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:6]
        results = [
            {"title": "来源 " + h + "-" + str(i), "url": "https://ex.com/" + h + "/" + str(i),
             "published_date": "2025-0" + str((i % 9) + 1) + "-01",
             "content": "关于 " + query + " 的示例内容 " + str(i)}
            for i in range(self.results_per_query)
        ]
        return {"answer": self.answer, "results": results}


class TestPipeline(unittest.TestCase):
    def test_normal_report(self):
        llm = StubLLM([BRIEF_OK, ANALYZE_DONE, REPORT_OK])
        # 每次检索返回 2 条，两轮共 2 次检索 → 来源表至少有 [1][2][3]
        pipe = Pipeline(llm, StubBackend(results_per_query=2), Scope(market="中国大陆", depth="2"), verbose=False)
        r = pipe.run("调研胶囊咖啡在中国市场的竞争格局")

        self.assertFalse(r.unclear)
        self.assertEqual(r.rounds_used, 1)
        self.assertIn("## 参考来源", r.markdown)
        self.assertNotIn("引用清单", r.markdown)
        self.assertIn("[1]", r.markdown)
        self.assertEqual(r.n_cited, 3)
        self.assertGreater(r.n_sources, 0)
        self.assertIn("调研范围", r.markdown)

    def test_clarify_branch(self):
        llm = StubLLM(["<!--CLARIFY-->\n请问你要调研哪个行业？（A 咖啡 / B 茶饮）"])
        pipe = Pipeline(llm, StubBackend(), Scope(), verbose=False)
        r = pipe.run("帮我做个调研")

        self.assertTrue(r.unclear)
        self.assertIn("哪个行业", r.markdown)
        self.assertEqual(llm.calls, 1)          # 只调了一次模型就返回
        self.assertEqual(r.rounds_used, 0)

    def test_offtopic_interception(self):
        llm = StubLLM([BRIEF_OK, "【本轮新增要点】\n- 本轮材料与主题无关"])
        pipe = Pipeline(llm, StubBackend(results_per_query=0), Scope(depth="2"), verbose=False)
        r = pipe.run("调研一个根本不存在的主题")

        self.assertTrue(r.unclear)
        self.assertIn("无法形成可信报告", r.markdown)

    def test_depth_cap_respected(self):
        # 模型永远说「继续」，但轮数必须被 depth 卡住
        llm = StubLLM([BRIEF_OK] + [ANALYZE_MORE] * 10 + [REPORT_OK])
        pipe = Pipeline(llm, StubBackend(), Scope(depth="3"), verbose=False)
        r = pipe.run("调研胶囊咖啡市场")
        self.assertEqual(r.rounds_used, 3)

    def test_citation_table_drops_uncited(self):
        # 报告只引 [1]，来源表里 [2][3] 应被剔除
        report = REPORT_OK.replace("引用清单：1, 2, 3", "引用清单：1")
        llm = StubLLM([BRIEF_OK, ANALYZE_DONE, report])
        pipe = Pipeline(llm, StubBackend(results_per_query=2), Scope(depth="2"), verbose=False)
        r = pipe.run("调研胶囊咖啡市场")
        self.assertTrue(r.n_cited < r.n_sources)

    def test_engine_summary_numbered(self):
        # Tavily answer 也要占编号，且出现在来源表里
        llm = StubLLM([BRIEF_OK, ANALYZE_DONE, REPORT_OK])
        pipe = Pipeline(llm, StubBackend(answer="引擎摘要示例"), Scope(depth="2"), verbose=False)
        r = pipe.run("调研胶囊咖啡市场")
        self.assertIn("Tavily 引擎摘要", r.markdown)

    def test_meta_reported(self):
        llm = StubLLM([BRIEF_OK, ANALYZE_DONE, REPORT_OK])
        pipe = Pipeline(llm, StubBackend(), Scope(depth="2"), verbose=False)
        r = pipe.run("调研胶囊咖啡市场")
        self.assertGreater(r.meta["本文字数"], 100)
        self.assertGreaterEqual(r.meta["模型调用"], 3)


class TestFixtureCorpus(unittest.TestCase):
    """真实离线语料 + 桩模型，验证 fixture 后端与编排能拼起来。"""

    def test_fixture_end_to_end(self):
        from mra.search import FixtureBackend
        llm = StubLLM([BRIEF_OK, ANALYZE_DONE, REPORT_OK])
        pipe = Pipeline(llm, FixtureBackend(FIXTURE, max_results=3), Scope(depth="2"), verbose=False)
        r = pipe.run("胶囊咖啡 市场规模 竞争格局")
        self.assertFalse(r.unclear)
        self.assertIn("example.com", r.markdown)


class TestOptimizations(unittest.TestCase):
    """3.8：并行检索 + 按需降噪。"""

    def test_normalize_skipped_when_density_ok(self):
        long_ok = REPORT_OK.replace("## 三、竞争格局\n…[2]",
                                    "## 三、竞争格局\n" + "竞争格局分析。" * 150 + "[2]")
        llm = StubLLM([BRIEF_OK, ANALYZE_DONE, long_ok])
        pipe = Pipeline(llm, StubBackend(results_per_query=2), Scope(depth="2"), verbose=False)
        r = pipe.run("调研胶囊咖啡市场")
        self.assertEqual(llm.calls, 3)          # brief + analyze + report，没有降噪调用
        self.assertIn("## 参考来源", r.markdown)


class TestHygienePredicate(unittest.TestCase):
    def test_low_density_ok(self):
        body = ("## 一、x\n" + "正文内容。" * 300 + "[1]")
        self.assertTrue(Pipeline._citation_hygiene_ok(body))

    def test_high_density_not_ok(self):
        body = "## 一、x\n" + "[1]" * 200
        self.assertFalse(Pipeline._citation_hygiene_ok(body))

    def test_long_run_not_ok(self):
        body = "## 一、x\n" + "正文。" * 500 + "[1][2][3][4]"
        self.assertFalse(Pipeline._citation_hygiene_ok(body))

    def test_normalize_runs_when_dense(self):
        dense = REPORT_OK.replace("市场规模约 58 亿元[1]", "58 亿元[1][1][1][1][1]")
        llm = StubLLM([BRIEF_OK, ANALYZE_DONE, dense, "## 一、x\n" + "填充。" * 2000])
        pipe = Pipeline(llm, StubBackend(results_per_query=2), Scope(depth="2"), verbose=False)
        pipe.run("调研胶囊咖啡市场")
        self.assertGreaterEqual(llm.calls, 4)   # 触发了降噪

    def test_searches_run_in_parallel(self):
        import time

        class SlowBackend(StubBackend):
            def search(self, query):
                time.sleep(0.12)
                return super().search(query)

        llm = StubLLM([BRIEF_OK, ANALYZE_DONE, REPORT_OK])
        pipe = Pipeline(llm, SlowBackend(), Scope(depth="2"), verbose=False)
        t0 = time.time()
        pipe.run("调研胶囊咖啡市场")
        # 串行至少 0.24s，并行约 0.12s
        self.assertLess(time.time() - t0, 0.22)


if __name__ == "__main__":
    unittest.main(verbosity=2)
