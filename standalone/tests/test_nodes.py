"""节点层单测：不联网、不调模型，直接验证从 DSL 搬过来的逻辑。

    python -m unittest discover -s standalone/tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mra import nodes  # noqa: E402
from mra.config import Scope  # noqa: E402


BRIEF = """<!--READY-->
调研主题：胶囊咖啡在中国市场的竞争格局
所属行业：消费品/快消
目标市场：中国大陆
目标客群：一二线城市白领
调研目的：新品立项
时间范围：近三年
核心问题：
1. 市场规模与增速
2. 竞争格局与份额
3. 价格带与渠道
4. 主要风险
建议数据来源：券商研报 / 电商数据
初始检索式1：中国 胶囊咖啡 市场规模 增速 2024
初始检索式2：胶囊咖啡 竞争格局 市场份额 主要厂商
待确认：无"""


class TestScope(unittest.TestCase):
    def test_defaults_and_rounds(self):
        s = Scope()
        self.assertEqual(s.rounds(), 3)
        self.assertEqual(s.geo, "全球")
        self.assertIn("【检索口径】", s.search_scope())
        self.assertIn("【报告口径】", s.report_scope())

    def test_depth_clamp(self):
        self.assertEqual(Scope(depth="9").rounds(), 4)
        self.assertEqual(Scope(depth="1").rounds(), 2)
        self.assertEqual(Scope(depth="abc").rounds(), 3)

    def test_geo_override(self):
        s = Scope(market="中国大陆")
        self.assertEqual(s.geo, "中国大陆")
        self.assertIn("中国大陆", s.search_scope())

    def test_source_hint(self):
        s = Scope(source_pref="优先券商研报/咨询报告")
        self.assertIn("券商研报", s.search_scope())
        self.assertIn("优先采用券商研报", s.report_scope())


class TestBrief(unittest.TestCase):
    def test_ready(self):
        b = nodes.clean_brief(BRIEF)
        self.assertEqual(b["ready"], "yes")
        self.assertNotIn("<!--READY-->", b["text"])
        self.assertIn("调研主题：", b["text"])

    def test_clarify(self):
        b = nodes.clean_brief("<!--CLARIFY-->\n请问你要调研哪个行业？A 咖啡 B 茶饮")
        self.assertEqual(b["clarify"], "yes")
        self.assertIn("哪个行业", b["question"])

    def test_seed_from_brief(self):
        seed = nodes.seed_queries(BRIEF, "胶囊咖啡", "中国大陆")
        self.assertEqual(seed["q1"], "中国 胶囊咖啡 市场规模 增速 2024")
        self.assertIn("竞争格局", seed["q2"])
        self.assertNotEqual(seed["q1"], seed["q2"])

    def test_seed_fallback(self):
        seed = nodes.seed_queries("没有任何检索式的简报", "胶囊咖啡", "全球")
        self.assertIn("市场规模", seed["q1"])
        self.assertIn("竞争格局", seed["q2"])


class TestPickRound(unittest.TestCase):
    def test_first_round(self):
        p = nodes.pick_round("", "", "q1", "q2", "", 3)
        self.assertEqual(p["round"], 1)
        self.assertEqual(p["rounds_left"], 3)
        self.assertEqual(p["is_last"], "no")

    def test_last_round(self):
        knowledge = "=== 第 1 轮 ===\nx\n\n=== 第 2 轮 ===\ny"
        p = nodes.pick_round("", "", "q1", "q2", knowledge, 3)
        self.assertEqual(p["round"], 3)
        self.assertEqual(p["rounds_left"], 1)
        self.assertEqual(p["is_last"], "yes")


class TestPack(unittest.TestCase):
    def test_numbering_and_dedupe(self):
        a = {"answer": "A 摘要", "results": [
            {"title": "T1", "url": "https://x/1", "content": "c1", "published_date": "2025-01-01"},
            {"title": "T2", "url": "https://x/2", "content": "c2"},
        ]}
        b = {"answer": "", "results": [
            {"title": "T2 dup", "url": "https://x/2", "content": "c2b"},
            {"title": "T3", "url": "https://x/3", "content": "c3"},
        ]}
        p1 = nodes.pack_results(a, b, "", round_no=1)
        self.assertEqual(p1["total_count"], 4)   # 1 摘要 + 3 网址
        self.assertEqual(p1["new_count"], 4)
        self.assertIn("[1] Tavily 引擎摘要", p1["numbered"])
        self.assertIn("[2] T1", p1["numbered"])
        self.assertIn("[4] T3", p1["numbered"])
        self.assertIn("2 | T1 | https://x/1", p1["registry"])

        # 第二轮同样两个 URL 不重复编号；但每轮的引擎摘要内容不同，按设计各占一个新编号
        p2 = nodes.pack_results(a, b, p1["registry"], round_no=2)
        self.assertEqual(p2["new_count"], 1)          # 只有 A 摘要算新增
        self.assertEqual(p2["total_count"], 5)
        url_rows = [ln for ln in p2["registry"].split("\n") if "https://" in ln]
        self.assertEqual(len(url_rows), 3)            # URL 行没有重复

    def test_pipe_in_title_sanitized(self):
        a = {"results": [{"title": "a|b", "url": "https://x/9", "content": "c"}]}
        p = nodes.pack_results(a, {}, "")
        self.assertNotIn("a|b", p["registry"])
        self.assertIn("a｜b", p["registry"])

    def test_kb_injected_only_first_round(self):
        p1 = nodes.pack_results({}, {}, "", kb="[K1] 旧报告片段", kb_registry="K1 | 旧报告 | kb://1 | ", round_no=1)
        self.assertIn("内部知识库", p1["numbered"])
        self.assertIn("K1", p1["registry"])
        p2 = nodes.pack_results({}, {}, p1["registry"], kb="[K1] 旧报告片段", kb_registry="K1 | 旧报告 | kb://1 | ", round_no=2)
        self.assertNotIn("内部知识库", p2["numbered"])


class TestParseAnalyze(unittest.TestCase):
    def test_queries_extracted(self):
        text = ("【本轮新增要点】\n- 规模 58 亿（来源 [1]）\n【覆盖度】\n缺：渠道\n"
                "【下一轮检索式】\nQUERY1: 胶囊咖啡 渠道 电商占比\nQUERY2: 胶囊咖啡 线下 体验店")
        r = nodes.parse_analyze(text, "", "1 | t | u | ", 2, "胶囊咖啡")
        self.assertEqual(r["q1"], "胶囊咖啡 渠道 电商占比")
        self.assertEqual(r["q2"], "胶囊咖啡 线下 体验店")
        self.assertEqual(r["done"], "no")
        self.assertIn("=== 第 1 轮 ===", r["knowledge"])
        self.assertNotIn("下一轮检索式", r["knowledge"])

    def test_done(self):
        r = nodes.parse_analyze("DONE", "", "1 | t | u | ", 1, "x")
        self.assertEqual(r["done"], "yes")

    def test_no_new_sources_stops(self):
        r = nodes.parse_analyze("【本轮新增要点】\n- x\nQUERY1: aaa\nQUERY2: bbb",
                                "", "", 0, "x")
        self.assertEqual(r["done"], "yes")

    def test_offtopic_when_no_registry(self):
        r = nodes.parse_analyze("【本轮新增要点】\n- 本轮材料与主题无关", "", "", 0, "x")
        self.assertEqual(r["offtopic"], "yes")

    def test_pads_queries(self):
        r = nodes.parse_analyze("【本轮新增要点】\n- x", "", "1 | t | u | ", 1, "胶囊咖啡")
        self.assertTrue(r["q1"] and r["q2"])
        self.assertNotEqual(r["q1"], r["q2"])


class TestSources(unittest.TestCase):
    def test_unused_detection(self):
        knowledge = "=== 第 1 轮 ===\n- 规模 58 亿（来源 [1]）"
        registry = "1 | T1 | https://x/1 | 2025-01-01\n2 | T2 | https://x/2 | "
        s = nodes.summarize_sources(knowledge, registry)
        self.assertEqual(s["n_sources"], 2)
        self.assertIn("[2]", s["unused"])
        self.assertNotIn("[1]", s["unused"])
        self.assertIn("1. T1（2025-01-01） — https://x/1", s["source_list"])

    def test_empty_materials_message(self):
        s = nodes.summarize_sources("", "")
        self.assertIn("没有取得可用来源", s["source_list"])
        self.assertIn("没有返回任何材料", s["materials"])


class TestCiteTable(unittest.TestCase):
    SOURCES = "K1. 旧报告（2024） — kb://1\n1. T1（2025-01-01） — https://x/1\n2. T2 — https://x/2\n3. T3 — https://x/3"

    def test_uses_citation_list_and_drops_it(self):
        text = "正文 [1] 数据 [2]。\n引用清单：1, K1, 2"
        r = nodes.build_cited_table(text, self.SOURCES)
        self.assertNotIn("引用清单", r["body"])
        self.assertEqual(r["n_cited"], 3)
        # K 在前，数字按升序
        self.assertTrue(r["cited_list"].startswith("K1."))
        self.assertLess(r["cited_list"].index("1. T1"), r["cited_list"].index("2. T2"))

    def test_fallback_to_body(self):
        r = nodes.build_cited_table("正文 [3] 只有这一条", self.SOURCES)
        self.assertEqual(r["n_cited"], 1)
        self.assertIn("T3", r["cited_list"])

    def test_dropped_count(self):
        r = nodes.build_cited_table("正文 [1]\n引用清单：1", self.SOURCES)
        self.assertEqual(r["dropped"], 3)

    def test_strips_html_comment(self):
        r = nodes.build_cited_table("正文 [1]<!--READY-->", self.SOURCES)
        self.assertNotIn("<!--", r["body"])


class TestSourceOrder(unittest.TestCase):
    """来源表排序：知识库 → 真实网页 → 引擎摘要垫底。"""

    def test_engine_summaries_last(self):
        sources = (
            "K1. 旧报告 — kb://1\n"
            "1. Tavily 引擎摘要（检索式A） — Tavily answer 字段\n"
            "2. 真实来源A — https://a/2\n"
            "3. Tavily 引擎摘要（检索式B） — Tavily answer 字段\n"
            "4. 真实来源B — https://a/4"
        )
        body = "结论[1][2][3][4][K1]"
        r = nodes.build_cited_table(body, sources)
        lines = r["cited_list"].split("\n")
        self.assertTrue(lines[0].startswith("K1."))
        self.assertIn("真实来源A", lines[1])
        self.assertIn("真实来源B", lines[2])
        self.assertIn("引擎摘要", lines[3])
        self.assertIn("引擎摘要", lines[4])


if __name__ == "__main__":
    unittest.main(verbosity=2)
