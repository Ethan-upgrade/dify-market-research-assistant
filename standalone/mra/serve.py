"""本地服务：把 CLI 的能力暴露成 HTTP，方便 Dify / 飞书 / 其他系统调用。

    python -m mra.serve --port 8765
    # 设了 MRA_TOKEN 就要求 Authorization: Bearer <token>

接口
----
GET  /health
     → {"ok": true, "version": "3.10.0"}

POST /check
     {"markdown": "报告全文"}
     → {"ok": bool, "problems": [...], "metrics": {...}}

POST /verify
     {"markdown": "...", "links": true, "trace": false, "fetcher": "auto"}
     → {"check": {...}, "links": {...}|null, "trace": {...}|null}

POST /research                  ← 异步：立刻返回 job_id，避免 HTTP 超时
     {"query": "调研 XX 市场", "market": "中国大陆", "depth": "3", ...}
     → 202 {"job_id": "…", "status": "queued", "poll": "/jobs/…"}

GET  /jobs/<job_id>
     → {"status": "queued|running|done|failed", "result": {...}|null, "error": "…"}

DELETE /jobs/<job_id>           清理

典型接法（Dify 工作流）：
1) Answer 节点前加 HTTP Request → POST /check，用返回 ok 走条件分支；
2) 若要整条调研都在外部跑，用 POST /research + 轮询 /jobs/<id>（Dify 的 HTTP 节点默认超时扛不住 3 分钟）。

注意：容器里的 127.0.0.1 指向容器自己，Dify 用 host.docker.internal。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .checks import check_report

MAX_BODY = 8 * 1024 * 1024
JOB_TTL = 3600
MAX_JOBS = 100

_JOBS = {}
_LOCK = threading.Lock()


# ------------------------------------------------------------------ 任务
def _run_research(payload: dict) -> dict:
    """真正跑调研（会被放到线程里；测试可直接 monkeypatch 这个函数）。"""
    from .config import RuntimeConfig, Scope
    from .llm import LLM
    from .pipeline import Pipeline
    from .search import build_backend

    query = (payload.get("query") or "").strip()
    if not query:
        raise ValueError("缺少 query 字段")

    cfg = RuntimeConfig.from_env()
    if payload.get("search"):
        cfg.search_backend = payload["search"]
    if payload.get("fixture"):
        cfg.fixture_path = payload["fixture"]

    scope = Scope(
        market=payload.get("market") or "不限（全球为主）",
        industry=payload.get("industry") or "不限",
        purpose=payload.get("purpose") or "竞品分析",
        time_range=payload.get("time_range") or "近三年",
        source_pref=payload.get("source_pref") or "不限",
        depth=str(payload.get("depth") or "3"),
    )
    llm = LLM(cfg.base_url, cfg.api_key, cfg.model, cfg.temperature, cfg.max_tokens, cfg.timeout)
    pipe = Pipeline(llm, build_backend(cfg), scope, verbose=False,
                    normalize_citations=not payload.get("no_normalize", False))
    rep = pipe.run(query)
    return {
        "markdown": rep.markdown,
        "unclear": rep.unclear,
        "rounds": rep.rounds_used,
        "sources": rep.n_sources,
        "cited": rep.n_cited,
        "chars": len(rep.markdown),
        "check": check_report(rep.markdown) if not rep.unclear else None,
    }


def _prune_jobs() -> None:
    now = time.time()
    with _LOCK:
        for jid in [k for k, v in _JOBS.items() if now - v["created"] > JOB_TTL]:
            _JOBS.pop(jid, None)
        while len(_JOBS) > MAX_JOBS:
            oldest = min(_JOBS, key=lambda k: _JOBS[k]["created"])
            _JOBS.pop(oldest, None)


def _start_job(payload: dict) -> str:
    _prune_jobs()
    jid = uuid.uuid4().hex[:12]
    with _LOCK:
        _JOBS[jid] = {"status": "queued", "created": time.time(), "result": None, "error": ""}

    def worker():
        with _LOCK:
            _JOBS[jid]["status"] = "running"
        try:
            res = _run_research(payload)
            with _LOCK:
                _JOBS[jid].update(status="done", result=res)
        except Exception as e:                       # 任何异常都要落进 job 状态
            with _LOCK:
                _JOBS[jid].update(status="failed", error=str(e)[:300])

    threading.Thread(target=worker, daemon=True).start()
    return jid


# ------------------------------------------------------------------ 处理
def _payload_check(data: dict) -> dict:
    md = data.get("markdown") or ""
    if not isinstance(md, str) or not md.strip():
        raise ValueError("缺少 markdown 字段")
    return check_report(
        md,
        min_chars=int(data.get("min_chars") or 3000),
        min_cited_ratio=float(data.get("min_cited_ratio") or 0.6),
        min_chapters=int(data.get("min_chapters") or 7),
        max_marks_per_100=float(data.get("max_density") or 6.0),
    )


def _payload_verify(data: dict) -> dict:
    md = data.get("markdown") or ""
    if not isinstance(md, str) or not md.strip():
        raise ValueError("缺少 markdown 字段")
    out = {"check": check_report(md)}
    if data.get("links"):
        from .verify import check as link_check
        out["links"] = {k: v for k, v in link_check(md, fetcher=data.get("fetcher", "auto")).items() if k != "rows"}
    else:
        out["links"] = None
    if data.get("trace"):
        from .trace import check as trace_check
        out["trace"] = {k: v for k, v in trace_check(md, fetcher=data.get("fetcher", "auto")).items() if k != "rows"}
    else:
        out["trace"] = None
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "mra/" + __version__

    def _auth_ok(self) -> bool:
        token = os.environ.get("MRA_TOKEN", "").strip()
        if not token:
            return True
        return self.headers.get("Authorization", "") == "Bearer " + token

    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):
        path = self.path.rstrip("/")
        if not self._auth_ok():
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        if path in ("/health", ""):
            self._send(200, {"ok": True, "version": __version__})
            return
        if path.startswith("/jobs/"):
            jid = path.split("/jobs/", 1)[1]
            with _LOCK:
                job = dict(_JOBS.get(jid) or {})
            if not job:
                self._send(404, {"ok": False, "error": "job not found"})
                return
            self._send(200, {"ok": True, "job_id": jid, **job})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_DELETE(self):
        path = self.path.rstrip("/")
        if not self._auth_ok():
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        if path.startswith("/jobs/"):
            jid = path.split("/jobs/", 1)[1]
            with _LOCK:
                existed = _JOBS.pop(jid, None) is not None
            self._send(200 if existed else 404, {"ok": existed})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = self.path.rstrip("/")
        if not self._auth_ok():
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._send(400, {"ok": False, "error": "body 为空或过大"})
            return
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as e:
            self._send(400, {"ok": False, "error": "JSON 解析失败: %s" % e})
            return

        try:
            if path == "/check":
                self._send(200, _payload_check(data))
            elif path == "/verify":
                self._send(200, _payload_verify(data))
            elif path == "/research":
                jid = _start_job(data)
                self._send(202, {"ok": True, "job_id": jid, "status": "queued", "poll": "/jobs/" + jid})
            else:
                self._send(404, {"ok": False, "error": "not found"})
        except ValueError as e:
            self._send(400, {"ok": False, "error": str(e)})
        except Exception as e:                       # 兜底，别让服务挂
            self._send(500, {"ok": False, "error": str(e)[:300]})


def main(argv=None) -> int:
    try:                       # Windows 控制台默认非 UTF-8，中文输出会直接抛 UnicodeEncodeError
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(prog="mra.serve", description="报告体检 / 调研 HTTP 服务")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"mra {__version__} serving on http://{args.host}:{args.port}  (Ctrl+C 退出)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    return 0


if __name__ == "__main__":
    sys.exit(main())
