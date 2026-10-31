"""检索后端契约测试：用桩替换 urlopen，验证请求体与 Tavily API 逐字段对齐。"""

import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mra import search  # noqa: E402


class FakeResp:
    def __init__(self, payload: dict):
        self._buf = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestTavilyContract(unittest.TestCase):
    def test_payload_fields(self):
        p = search._tavily_payload("k", "中国 胶囊咖啡", 6, "advanced")
        self.assertEqual(set(p), {
            "api_key", "query", "search_depth", "topic",
            "max_results", "include_answer", "include_raw_content",
        })
        self.assertEqual(p["search_depth"], "advanced")
        self.assertEqual(p["max_results"], 6)
        self.assertTrue(p["include_answer"])
        self.assertFalse(p["include_raw_content"])
        self.assertEqual(p["topic"], "general")

    def test_endpoint_and_body_sent(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            captured["ctype"] = req.headers.get("Content-type")
            return FakeResp({"answer": "ok", "results": [{"url": "https://x/1", "title": "t"}]})

        be = search.TavilyBackend("test-key-123", max_results=6, depth="advanced")
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            out = be.search("中国 胶囊咖啡 市场规模")

        self.assertEqual(captured["url"], "https://api.tavily.com/search")
        self.assertEqual(captured["body"]["api_key"], "test-key-123")
        self.assertEqual(captured["body"]["query"], "中国 胶囊咖啡 市场规模")
        self.assertEqual(captured["ctype"], "application/json")
        self.assertEqual(out["answer"], "ok")
        self.assertEqual(be.calls, 1)

    def test_missing_key_raises(self):
        with self.assertRaises(search.SearchError):
            search.TavilyBackend("")

    def test_401_maps_to_clear_error(self):
        import urllib.error

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"bad key"))

        be = search.TavilyBackend("k", retries=1)
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(search.SearchError) as ctx:
                be.search("q")
        self.assertIn("401", str(ctx.exception))


class TestFixtureBackend(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "corpus.json")

    def test_returns_relevant_docs(self):
        be = search.FixtureBackend(self.path, max_results=3)
        out = be.search("胶囊咖啡 市场规模 增速")
        self.assertGreater(len(out["results"]), 0)
        self.assertLessEqual(len(out["results"]), 3)
        self.assertTrue(out["offline"])
        self.assertIn("capsule-market-size", out["results"][0]["url"])

    def test_shape_matches_tavily(self):
        be = search.FixtureBackend(self.path)
        out = be.search("竞争格局 市场份额")
        for r in out["results"]:
            self.assertEqual(set(r), {"title", "url", "published_date", "content", "score"})

    def test_missing_file(self):
        with self.assertRaises(search.SearchError):
            search.FixtureBackend("no/such/file.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
