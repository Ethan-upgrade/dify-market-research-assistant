"""流程编排 —— 复刻 DSL v3 的 26 个节点。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime

from . import nodes, prompts
from .config import Scope


@dataclass
class Report:
    markdown: str
    query: str
    scope: Scope
    rounds_used: int = 0
    n_sources: int = 0
    n_cited: int = 0
    unclear: bool = False
    clarify_question: str = ""
    meta: dict = field(default_factory=dict)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


class Pipeline:
    def __init__(self, llm, backend, scope: Scope, verbose: bool = True, normalize_citations: bool = True):
        self.llm = llm
        self.backend = backend
        self.scope = scope
        self.verbose = verbose
        self.normalize_citations = normalize_citations
        self._t0 = time.time()

    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"[{time.time() - self._t0:5.1f}s] {msg}", flush=True)

    # ---------------------------------------------------------- ① 需求解析
    def plan(self, query: str, clarify_round: int = 0) -> dict:
        self.log("① 调研需求解析")
        raw = self.llm.chat(
            prompts.BRIEF_SYSTEM,
            prompts.brief_user(query, self.scope.search_scope(), clarify_round),
            temperature=0.3, max_tokens=4096,
        )
        brief = nodes.clean_brief(raw)
        return brief

    # ---------------------------------------------------------- ③ 递归检索
    def research(self, query: str, brief: str) -> dict:
        scope = self.scope
        max_rounds = scope.rounds()
        seed = nodes.seed_queries(brief, query, scope.geo)
        self.log(f"② 初始检索式：{seed['q1']} ／ {seed['q2']}")

        knowledge, registry = "", ""
        cur_q1, cur_q2 = "", ""
        offtopic = "no"
        round_no = 0

        for round_no in range(1, max_rounds + 1):
            pick = nodes.pick_round(cur_q1, cur_q2, seed["q1"], seed["q2"], knowledge, max_rounds)
            self.log(f"③ 第 {pick['round']}/{max_rounds} 轮检索：{pick['q1']} ／ {pick['q2']}")

            raw_a = self.backend.search(pick["q1"] + " 行业数据 报告")
            raw_b = self.backend.search(pick["q2"] + " 行业数据 报告")
            self.log(f"   ⑤⑥ 检索完成：A {len(raw_a.get('results') or [])} 条 / B {len(raw_b.get('results') or [])} 条")

            packed = nodes.pack_results(raw_a, raw_b, registry, round_no=pick["round"])
            registry = packed["registry"]
            self.log(f"   ⑦ 去重编号后累计来源 {packed['total_count']} 条（本轮新增 {packed['new_count']}）")

            analysis = self.llm.chat(
                prompts.ANALYZE_SYSTEM,
                prompts.analyze_user(pick["round"], max_rounds, pick["rounds_left"],
                                     pick["q1"], pick["q2"], scope.search_scope(),
                                     brief, knowledge, packed["numbered"]),
                temperature=0.3, max_tokens=16384,
            )
            parsed = nodes.parse_analyze(analysis, knowledge, registry,
                                         packed["new_count"], query)
            knowledge = parsed["knowledge"]
            cur_q1, cur_q2 = parsed["q1"], parsed["q2"]
            offtopic = parsed["offtopic"]
            self.log(f"   ⑧⑨ 覆盖度：{'已足够' if parsed['done'] == 'yes' else '继续补搜'}")

            if parsed["done"] == "yes":
                break

        return {"knowledge": knowledge, "registry": registry,
                "rounds": round_no, "offtopic": offtopic}

    # ------------------------------------------------------------ ⑫ 写报告
    def write(self, query: str, brief: str, knowledge: str, registry: str) -> dict:
        src = nodes.summarize_sources(knowledge, registry)
        self.log(f"⑪ 汇总材料：{src['n_sources']} 条来源（知识库 {src['n_kb']} 条）")
        self.log("⑫ 撰写调研报告")
        body = self.llm.chat(
            prompts.REPORT_SYSTEM,
            prompts.report_user(self.scope.report_scope(), brief, query,
                                src["materials"], src["source_list"],
                                src["unused"], src["n_sources"], src["n_kb"]),
            temperature=0.7, max_tokens=16384,
        )
        if getattr(self, "normalize_citations", True):
            body = self._normalize_citations(body)
        cited = nodes.build_cited_table(body, src["source_list"])
        self.log(f"⑫ᵇ 正文引用 {cited['n_cited']} 条来源，剔除未引用 {cited['dropped']} 条")
        return {"body": cited["body"], "cited_list": cited["cited_list"],
                "n_cited": cited["n_cited"], "n_sources": src["n_sources"]}

    # -------------------------------------------------------------- 全流程
    def run(self, query: str) -> Report:
        brief = self.plan(query)
        if brief["ready"] != "yes":
            self.log("② 信息不足：返回追问")
            return Report(markdown=brief["question"], query=query, scope=self.scope,
                          unclear=True, clarify_question=brief["question"])

        res = self.research(query, brief["text"])
        if res["offtopic"] == "yes":
            msg = ("检索回来的材料与主题无关，无法形成可信报告。\n\n"
                   "请确认调研对象是否写清楚（例：Nespresso 胶囊咖啡在中国市场的竞争格局），"
                   "或放宽「调研范围」的数据源偏好后重试。")
            return Report(markdown=msg, query=query, scope=self.scope,
                          rounds_used=res["rounds"], unclear=True, clarify_question=msg)

        out = self.write(query, brief["text"], res["knowledge"], res["registry"])
        md = self._compose(query, out)
        return Report(
            markdown=md, query=query, scope=self.scope,
            rounds_used=res["rounds"], n_sources=out["n_sources"], n_cited=out["n_cited"],
            meta={"本文字数": len(out["body"]), "模型调用": self.llm.calls,
                  "tokens": self.llm.tokens, "检索次数": getattr(self.backend, "calls", 0)},
        )

    def _normalize_citations(self, body: str) -> str:
        """第二次过模型，只做引用降噪（合并同句重复标注）。失败则原样返回。"""
        before = body.count("[")
        try:
            cleaned = self.llm.chat(
                prompts.CITE_NORMALIZE,
                body + "\n\n（以上是待清理的正文，请输出清理后的正文）",
                temperature=0.0, max_tokens=16384,
            )
        except Exception as e:                      # 降噪失败不能影响主流程
            self.log(f"⑫ᵃ 引用降噪失败，保留原文：{e}")
            return body
        # 防御①：结构必须还在（章节、长度不许缩水 40% 以上）
        if "## " not in cleaned or len(cleaned) < len(body) * 0.6:
            self.log("⑫ᵃ 引用降噪结果异常，保留原文")
            return body

        # 防御②：优先看「表格来源列是否还有出处」，比长度更硬的指标
        from .checks import count_blank_source_rows
        blank_before, blank_after = count_blank_source_rows(body), count_blank_source_rows(cleaned)
        if blank_after > blank_before:
            self.log(f"⑫ᵃ 降噪把表格来源列削空了（{blank_before} → {blank_after}），保留原文")
            return body

        # 防御③：来源编号不许丢太多（丢了就是伪造出处）
        from .checks import parse_report
        lost = set(parse_report(body)["cited_web"]) - set(parse_report(cleaned)["cited_web"])
        if len(lost) > max(2, len(parse_report(body)["cited_web"]) // 3):
            self.log(f"⑫ᵃ 降噪丢了来源编号 {sorted(lost)}，保留原文")
            return body

        after = cleaned.count("[")
        self.log(f"⑫ᵃ 引用降噪：[{before} → {after} 处标注")
        return cleaned

    def _compose(self, query: str, out: dict) -> str:
        head = (
            f"> **调研主题**：{query}  \n"
            f"> **调研范围**：{self.scope.summary()}  \n"
            f"> **生成时间**：{_now()}　**来源**：{out['n_sources']} 条（正文引用 {out['n_cited']} 条）\n\n"
            "---\n\n"
        )
        return (head + out["body"] + "\n\n---\n\n## 参考来源\n\n" + out["cited_list"] + "\n")
