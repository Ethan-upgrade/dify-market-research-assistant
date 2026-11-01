"""HTTP 服务测试（mra.serve）：起一个随机端口的真服务，走一遍网络。

    python tests/test_serve.py
"""

import json
import os
import sys
import threading
import unittest
import urllib.error
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
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

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


class TestAsyncResearch(ServerCase):
    """POST /research 异步任务：不阻塞、可轮询、失败有错误信息。"""

    def test_research_job_done(self):
        import time
        from unittest import mock

        def fake(payload):
            time.sleep(0.15)
            return {"markdown": "# 报告", "chars": 4, "check": {"ok": True}}

        with mock.patch.object(serve, "_run_research", side_effect=fake):
            code, body = self._post("/research", {"query": "调研胶囊咖啡"})
            self.assertEqual(code, 202)
            jid = body["job_id"]
            self.assertTrue(jid)
            for _ in range(40):
                c, j = self._get("/jobs/" + jid)
                if j["status"] in ("done", "failed"):
                    break
                time.sleep(0.05)
        self.assertEqual(c, 200)
        self.assertEqual(j["status"], "done", j)
        self.assertEqual(j["result"]["markdown"], "# 报告")

    def test_research_job_failed(self):
        import time
        from unittest import mock

        with mock.patch.object(serve, "_run_research", side_effect=RuntimeError("模型超时")):
            code, body = self._post("/research", {"query": "x"})
            jid = body["job_id"]
            for _ in range(40):
                c, j = self._get("/jobs/" + jid)
                if j["status"] == "failed":
                    break
                time.sleep(0.05)
        self.assertEqual(j["status"], "failed")
        self.assertIn("模型超时", j["error"])

    def test_job_not_found(self):
        code, body = self._get("/jobs/nonexistent")
        self.assertEqual(code, 404)

    def test_delete_job(self):
        from unittest import mock
        with mock.patch.object(serve, "_run_research", return_value={"markdown": "x"}):
            _, body = self._post("/research", {"query": "x"})
        jid = body["job_id"]
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/jobs/{jid}", method="DELETE")
        with urllib.request.urlopen(req, timeout=10) as r:
            self.assertEqual(r.status, 200)
        code, _ = self._get("/jobs/" + jid)
        self.assertEqual(code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
