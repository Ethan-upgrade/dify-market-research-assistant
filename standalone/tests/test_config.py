"""`.env` 加载测试：验证「文件里读得到、shell 里优先级更高、缺文件不崩」。

    python tests/test_config.py
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mra.config import RuntimeConfig, load_env_file  # noqa: E402

WATCHED = ["MRA_BASE_URL", "MRA_API_KEY", "MRA_MODEL", "TAVILY_API_KEY", "MRA_SEARCH_BACKEND"]


class TestDotEnv(unittest.TestCase):
    def setUp(self):
        # 测试只认「当前目录的 .env」，否则会读到仓库根真实存在的 .env
        self._patcher = mock.patch("mra.config._env_candidates", lambda: [Path.cwd() / ".env"])
        self._patcher.start()
        self._backup = {k: os.environ[k] for k in WATCHED if k in os.environ}
        for k in WATCHED:
            os.environ.pop(k, None)
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        self._patcher.stop()
        os.chdir(self._cwd)
        self._tmp.cleanup()
        for k in WATCHED:
            os.environ.pop(k, None)
        os.environ.update(self._backup)

    def _write(self, text):
        Path(".env").write_text(text, encoding="utf-8")

    def test_loads_values(self):
        self._write("MRA_BASE_URL=http://127.0.0.1:9999/v1\nMRA_MODEL=test-model\n# 注释行\n\n")
        path = load_env_file()
        self.assertTrue(path.endswith(".env"))
        cfg = RuntimeConfig.from_env()
        self.assertEqual(cfg.base_url, "http://127.0.0.1:9999/v1")
        self.assertEqual(cfg.model, "test-model")

    def test_shell_env_wins(self):
        self._write("MRA_MODEL=from-file\n")
        os.environ["MRA_MODEL"] = "from-shell"
        cfg = RuntimeConfig.from_env()
        self.assertEqual(cfg.model, "from-shell")

    def test_quoted_values_stripped(self):
        self._write('MRA_API_KEY="sk-quoted"\nTAVILY_API_KEY=\'tvly-quoted\'\n')
        cfg = RuntimeConfig.from_env()
        self.assertEqual(cfg.api_key, "sk-quoted")
        self.assertEqual(cfg.tavily_key, "tvly-quoted")

    def test_missing_file_ok(self):
        self.assertEqual(load_env_file(), "")
        cfg = RuntimeConfig.from_env()
        self.assertEqual(cfg.model, "deepseek-chat")     # 回落到默认值
        self.assertEqual(cfg.search_backend, "tavily")

    def test_inline_comment_not_eaten(self):
        # 值里带 # 但不在引号里，只按第一个 = 切分，不做注释剥离
        self._write("MRA_MODEL=model#withhash\n")
        cfg = RuntimeConfig.from_env()
        self.assertEqual(cfg.model, "model#withhash")


if __name__ == "__main__":
    unittest.main(verbosity=2)
