"""HTTP 服务测试（mra.serve）：起一个随机端口的真服务，走一遍网络。

    python tests/test_serve.py
"""

import json
import os
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mra import serve  # noqa: E402

GOOD = (
    "## 一、执行摘要\n规模 58 亿元[1]。\n\n"
    "## 二、市场规模\n[1]\n\n"
    "## 三、竞争格局\n[1]\n\n"
    "## 四、目标用户\n[1]\n" + "正文填充。" * 800 + "\n\n"
    "## 五、驱动因素\n[1]\n\n"
    "## 六、风险\n[1]\n\n"
    "## 七、结论\n[1]\n\n"
    "## 参考来源\n\n1. 来源 — https://a.example/1\n"
)


class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, json.loads(r.read().decode())

    def _post(self, path, obj):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())


class TestServe(ServerCase):
    def test_health(self):
        code, body = self._get("/health")
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertIn("version", body)

    def test_check_ok(self):
        code, body = self._post("/check", {"markdown": GOOD})
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"], body["problems"])
        self.assertEqual(body["metrics"]["web"], 1)

    def test_check_bad_markdown(self):
        code, body = self._post("/check", {"markdown": ""})
        self.assertEqual(code, 400)
        self.assertFalse(body["ok"])

    def test_unknown_path(self):
        code, body = self._post("/nope", {})
        self.assertEqual(code, 404)

    def test_auth_required_when_token_set(self):
        os.environ["MRA_TOKEN"] = "secret"
        try:
            code, body = self._post("/check", {"markdown": GOOD})
            self.assertEqual(code, 401)
        finally:
            os.environ.pop("MRA_TOKEN", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
