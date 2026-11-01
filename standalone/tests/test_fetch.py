"""抓取层测试（mra.fetch）——引擎链、降级、归因。

    python tests/test_fetch.py
"""

import os
import sys

os.environ.setdefault("MRA_FETCH_TTL", "0")   # 测试不读生产缓存
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mra import fetch  # noqa: E402


def ok(engine="x"):
    return {"ok": True, "status": 200, "text": "正文", "engine": engine, "reason": ""}


def err(status=0, reason="boom", engine="x"):
    return {"ok": False, "status": status, "text": "", "engine": engine, "reason": reason}


class TestChain(unittest.TestCase):
    def test_falls_through_to_next_engine(self):
        calls = []

        def fake(name, result):
            def fn(url, timeout):
                calls.append(name)
                return result
            return fn

        with mock.patch.dict(fetch._ENGINES, {
            "urllib": fake("urllib", err(403, "HTTP 403")),
            "curl_cffi": fake("curl_cffi", ok()),
        }, clear=True), mock.patch.object(fetch, "AUTO_CHAIN", ["urllib", "curl_cffi"]):
            r = fetch.fetch_text("https://x/1")
        self.assertTrue(r["ok"])
        self.assertEqual(r["engine"], "curl_cffi")
        self.assertEqual(calls, ["urllib", "curl_cffi"])

    def test_404_stops_chain(self):
        calls = []

        def fake(name, result):
            def fn(url, timeout):
                calls.append(name)
                return result
            return fn

        with mock.patch.dict(fetch._ENGINES, {
            "urllib": fake("urllib", err(404, "HTTP 404")),
            "curl_cffi": fake("curl_cffi", ok()),
        }, clear=True), mock.patch.object(fetch, "AUTO_CHAIN", ["urllib", "curl_cffi"]):
            r = fetch.fetch_text("https://x/404")
        self.assertFalse(r["ok"])
        self.assertEqual(calls, ["urllib"])

    def test_block_code_wins_over_not_installed(self):
        with mock.patch.dict(fetch._ENGINES, {
            "urllib": lambda u, t: err(403, "HTTP 403"),
            "curl_cffi": lambda u, t: err(0, "未安装"),
            "firecrawl": lambda u, t: err(0, "未配置 Key"),
        }, clear=True), mock.patch.object(fetch, "AUTO_CHAIN",
                                          ["urllib", "curl_cffi", "firecrawl"]):
            r = fetch.fetch_text("https://x/2")
        self.assertEqual(r["status"], 403)
        self.assertIn("403", r["reason"])

    def test_explicit_fetcher_only(self):
        calls = []
        with mock.patch.dict(fetch._ENGINES, {
            "urllib": lambda u, t: calls.append("urllib") or err(403),
            "curl_cffi": lambda u, t: calls.append("curl_cffi") or ok(),
        }, clear=True):
            r = fetch.fetch_text("https://x/3", fetcher="urllib")
        self.assertFalse(r["ok"])
        self.assertEqual(calls, ["urllib"])


class TestPdf(unittest.TestCase):
    def test_is_pdf(self):
        self.assertTrue(fetch.is_pdf("https://a/x.pdf"))
        self.assertTrue(fetch.is_pdf("https://a/x.pdf?token=1"))
        self.assertFalse(fetch.is_pdf("https://a/x.html"))

    def test_pdf_text_extraction(self):
        try:
            import pymupdf
        except Exception:
            self.skipTest("未安装 pymupdf")
        d = pymupdf.open()
        pg = d.new_page()
        pg.insert_text((72, 72), "Market size 58.3 billion CNY in 2024")
        blob = d.tobytes()
        d.close()
        r = fetch._pdf_text(blob)
        self.assertTrue(r["ok"], r["reason"])
        self.assertIn("58.3", r["text"])
        self.assertEqual(r["engine"], "pymupdf")

    def test_pdf_playwright_delegates_to_http(self):
        with mock.patch.object(fetch, "_via_urllib",
                               return_value={"ok": True, "status": 200, "text": "pdf text",
                                             "engine": "pymupdf(pdf)", "reason": ""}) as m:
            r = fetch._via_playwright("https://a/x.pdf", 10)
        m.assert_called_once()
        self.assertTrue(r["ok"])


class TestStripHtml(unittest.TestCase):
    def test_removes_scripts_and_tags(self):
        raw = "<html><script>var a=1</script><body><h1>标题</h1><p>正文 58.3 亿元</p></body></html>"
        txt = fetch.strip_html(raw)
        self.assertIn("标题", txt)
        self.assertIn("58.3 亿元", txt)
        self.assertNotIn("var a", txt)


class TestCache(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self._old = {k: os.environ.get(k) for k in ("MRA_CACHE_DIR", "MRA_FETCH_TTL")}
        os.environ["MRA_CACHE_DIR"] = self.tmp
        os.environ["MRA_FETCH_TTL"] = "3600"

    def tearDown(self):
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_second_call_hits_cache(self):
        calls = []

        def fake(u, t):
            calls.append(u)
            return ok()

        with mock.patch.dict(fetch._ENGINES, {"urllib": fake}, clear=True), \
             mock.patch.object(fetch, "AUTO_CHAIN", ["urllib"]):
            r1 = fetch.fetch_text("https://x/cache-1")
            r2 = fetch.fetch_text("https://x/cache-1")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("cache", r1["engine"])
        self.assertIn("cache", r2["engine"])

    def test_ttl_zero_disables(self):
        calls = []

        def fake(u, t):
            calls.append(u)
            return ok()

        os.environ["MRA_FETCH_TTL"] = "0"
        with mock.patch.dict(fetch._ENGINES, {"urllib": fake}, clear=True), \
             mock.patch.object(fetch, "AUTO_CHAIN", ["urllib"]):
            fetch.fetch_text("https://x/cache-2")
            fetch.fetch_text("https://x/cache-2")
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
