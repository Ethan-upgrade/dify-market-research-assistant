"""检索后端：Tavily（真联网）与 fixture（离线回放）。

Dify 版本里这一步是 HTTP Request 节点，请求体等价于这里的 `_tavily_payload()`。
换成别的搜索服务只要实现 `search(query) -> dict` 返回同样结构即可。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class SearchError(RuntimeError):
    pass


def _tavily_payload(api_key: str, query: str, max_results: int, depth: str) -> dict:
    """与 DSL 中「⑤ 检索 A / ⑥ 检索 B」节点请求体逐字段对齐。"""
    return {
        "api_key": api_key,
        "query": query,
        "search_depth": depth,
        "topic": "general",
        "max_results": max_results,
        "include_answer": True,
        "include_raw_content": False,
    }


class TavilyBackend:
    endpoint = "https://api.tavily.com/search"

    def __init__(self, api_key: str, max_results: int = 6, depth: str = "advanced",
                 timeout: int = 60, retries: int = 2):
        if not api_key:
            raise SearchError("缺少 TAVILY_API_KEY（也可用 --search fixture 离线跑）")
        self.api_key = api_key
        self.max_results = max_results
        self.depth = depth
        self.timeout = timeout
        self.retries = retries
        self.calls = 0

    def search(self, query: str) -> dict:
        payload = _tavily_payload(self.api_key, query, self.max_results, self.depth)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last = None
        for attempt in range(1, self.retries + 1):
            req = urllib.request.Request(
                self.endpoint, data=data,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    self.calls += 1
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", "replace")[:300]
                except Exception:
                    pass
                last = SearchError(f"Tavily HTTP {e.code}: {body}")
                if e.code == 401:
                    raise SearchError("Tavily 返回 401：Key 无效或已失效") from e
                if e.code == 429:
                    raise SearchError("Tavily 返回 429：额度用尽（免费 1000 credits/月）") from e
                if 400 <= e.code < 500:
                    raise last
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = SearchError(f"Tavily 网络错误: {e}")
            if attempt < self.retries:
                import time
                time.sleep(2 * attempt)
        raise last or SearchError("Tavily 未知错误")


class FixtureBackend:
    """离线检索：从 JSON 语料里按关键词打分返回，用于测试与演示。

    语料格式：{"docs": [{"title","url","published_date","content","tags":[]}]}
    """

    def __init__(self, path: str, max_results: int = 6):
        self.path = path
        self.max_results = max_results
        self.calls = 0
        if not os.path.isfile(path):
            raise SearchError(f"fixture 文件不存在: {path}")
        with open(path, encoding="utf-8") as f:
            self.docs = (json.load(f) or {}).get("docs", [])
        self._used = set()

    @staticmethod
    def _tokens(text: str) -> set:
        import re
        text = (text or "").lower()
        words = set(re.findall(r"[a-z0-9]{2,}", text))
        cjk = re.findall(r"[\u4e00-\u9fff]", text)
        words |= set(cjk)
        words |= {text[i:i + 2] for i in range(len(text) - 1) if "\u4e00" <= text[i] <= "\u9fff"}
        return words

    def search(self, query: str) -> dict:
        self.calls += 1
        q = self._tokens(query)
        scored = []
        for d in self.docs:
            hay = " ".join([d.get("title", ""), d.get("content", ""), " ".join(d.get("tags") or [])])
            dt = self._tokens(hay)
            score = len(q & dt)
            if score:
                scored.append((score, d))
        scored.sort(key=lambda x: (-x[0], x[1].get("url", "")))

        results = []
        for _, d in scored[: self.max_results]:
            results.append({
                "title": d.get("title", ""),
                "url": d.get("url", ""),
                "published_date": d.get("published_date", ""),
                "content": d.get("content", ""),
                "score": 0.5,
            })
        # 离线语料没有「引擎摘要」这一层，返回空串，让来源表只列真实文档
        return {"answer": "", "results": results, "query": query, "offline": True}


def build_backend(cfg) -> object:
    if cfg.search_backend == "fixture":
        if not cfg.fixture_path:
            raise SearchError("fixture 模式需要 --fixture 指定语料文件")
        return FixtureBackend(cfg.fixture_path, max_results=cfg.max_results)
    return TavilyBackend(cfg.tavily_key, max_results=cfg.max_results, depth=cfg.search_depth)
