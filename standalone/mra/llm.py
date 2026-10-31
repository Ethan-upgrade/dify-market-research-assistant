"""极简 OpenAI 兼容 chat 客户端（只用标准库 urllib）。

支持 DeepSeek / OpenAI / 通义 / 智谱 / Ollama / vLLM / 本机网关等一切
提供 /chat/completions 的服务。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, base_url: str, api_key: str, model: str,
                 temperature: float = 0.7, max_tokens: int = 16384,
                 timeout: int = 180, retries: int = 3, verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.retries = retries
        self.verbose = verbose
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    # ------------------------------------------------------------ 内部
    def _post(self, payload: dict) -> dict:
        url = self.base_url + "/chat/completions"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key

        last = None
        for attempt in range(1, self.retries + 1):
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", "replace")[:400]
                except Exception:
                    pass
                last = LLMError(f"HTTP {e.code}: {body}")
                # 4xx 里只有 429 值得重试
                if e.code != 429 and 400 <= e.code < 500:
                    raise last
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = LLMError(f"网络错误: {e}")
            if attempt < self.retries:
                time.sleep(min(8, 1.5 * attempt))
        raise last or LLMError("未知错误")

    # ------------------------------------------------------------ 对外
    def chat(self, system: str, user: str, temperature: float | None = None,
             max_tokens: int | None = None) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        data = self._post(payload)
        self.calls += 1
        usage = data.get("usage") or {}
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"响应结构异常: {json.dumps(data, ensure_ascii=False)[:400]}") from e
        return (content or "").strip()

    @property
    def tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens
