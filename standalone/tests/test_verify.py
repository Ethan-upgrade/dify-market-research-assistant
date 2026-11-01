"""链接体检测试（mra.verify）——用桩替换网络，只验证解析与判定。

    python tests/test_verify.py
"""

import os
import sys

os.environ.setdefault("MRA_FETCH_TTL", "0")   # 测试不读生产缓存
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mra import verify  # noqa: E402

REPORT = """## 一、执行摘要
规模 58 亿元[1]。

## 参考来源

1. 正常站 — https://ok.example/a
2. 反爬站 — https://bot.example/b
3. 死链 — https://dead.example/c
K1. 内部报告 — kb://1
"""


class TestParseSources(unittest.TestCase):
    def test_extracts_only_http(self):
        srcs = verify.parse_sources(REPORT)
        self.assertEqual([s["num"] for s in srcs], ["1", "2", "3"])
        self.assertEqual(srcs[0]["url"], "https://ok.example/a")
        self.assertEqual(srcs[1]["title"], "反爬站")

    def test_empty_report(self):
        self.assertEqual(verify.parse_sources("没有来源表"), [])


class TestVerdict(unittest.TestCase):
    def _fake(self, code=None, exc=None):
        if exc:
            return mock.patch("urllib.request.urlopen", side_effect=exc)
        resp = mock.MagicMock()
        resp.status = code
        resp.read.return_value = b"x" * 100
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda *a: False
        return mock.patch("urllib.request.urlopen", return_value=resp)

    def test_ok(self):
        with self._fake(200):
            r = verify.fetch("https://x/1")
        self.assertEqual(r["verdict"], "ok")

    def test_403_is_blocked_not_dead(self):
        import urllib.error
        err = urllib.error.HTTPError("https://x", 403, "Forbidden", {}, None)
        with self._fake(exc=err):
            r = verify.fetch("https://x/2")
        self.assertEqual(r["verdict"], "blocked")

    def test_404_is_dead(self):
        import urllib.error
        err = urllib.error.HTTPError("https://x", 404, "Not Found", {}, None)
        with self._fake(exc=err):
            r = verify.fetch("https://x/3")
        self.assertEqual(r["verdict"], "dead")

    def test_dns_error_is_dead(self):
        with self._fake(exc=OSError("[Errno 11001] getaddrinfo failed")):
            r = verify.fetch("https://x/4")
        self.assertEqual(r["verdict"], "dead")


class TestCheckAggregate(unittest.TestCase):
    def test_counts(self):
        verdicts = {
            "https://ok.example/a": {"status": 200, "size": 1, "verdict": "ok", "error": ""},
            "https://bot.example/b": {"status": 403, "size": 0, "verdict": "blocked", "error": "HTTP 403"},
            "https://dead.example/c": {"status": 0, "size": 0, "verdict": "dead", "error": "DNS"},
        }
        with mock.patch.object(verify, "fetch", side_effect=lambda u, t=12, f="auto": verdicts[u]):
            res = verify.check(REPORT)
        self.assertEqual((res["total"], res["ok"], res["blocked"], res["dead"]), (3, 1, 1, 1))

    def test_exit_code_semantics(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(REPORT)
            path = f.name
        try:
            with mock.patch.object(verify, "fetch", side_effect=lambda u, t=12, f="auto": {
                    "status": 200, "size": 1, "verdict": "ok", "error": ""}):
                self.assertEqual(verify.main([path]), 0)
            with mock.patch.object(verify, "fetch", side_effect=lambda u, t=12, f="auto": {
                    "status": 0, "size": 0, "verdict": "dead", "error": "boom"}):
                self.assertEqual(verify.main([path]), 1)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
