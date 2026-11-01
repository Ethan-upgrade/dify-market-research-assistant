"""本地服务：把 CLI 的体检能力暴露成 HTTP，方便 Dify / 飞书 / 其他系统调用。

    python -m mra.serve --port 8765
    # 设了 MRA_TOKEN 就要求 Authorization: Bearer <token>

接口
----
GET  /health
     → {"ok": true, "version": "3.9.0"}

POST /check
     {"markdown": "报告全文"}
     → {"ok": bool, "problems": [...], "metrics": {...}}

POST /verify
     {"markdown": "...", "links": true, "trace": false, "fetcher": "auto"}
     → {"check": {...}, "links": {...}|null, "trace": {...}|null}

典型接法（Dify 工作流）：Answer 节点之前加一个 HTTP Request 节点，
POST 到 http://host.docker.internal:8765/check，body 里塞上一步的报告文本；
返回的 ok 可以走条件分支——不合格就转人工，不再直接吐给用户。

注意：容器里的 127.0.0.1 指向容器自己，Dify 用 host.docker.internal。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .checks import check_report

MAX_BODY = 8 * 1024 * 1024


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
        if self.path.rstrip("/") in ("/health", ""):
            self._send(200, {"ok": True, "version": __version__})
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
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
            if self.path.rstrip("/") == "/check":
                self._send(200, _payload_check(data))
            elif self.path.rstrip("/") == "/verify":
                self._send(200, _payload_verify(data))
            else:
                self._send(404, {"ok": False, "error": "not found"})
        except ValueError as e:
            self._send(400, {"ok": False, "error": str(e)})
        except Exception as e:                       # 兜底，别让服务挂
            self._send(500, {"ok": False, "error": str(e)[:300]})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mra.serve", description="报告体检 HTTP 服务")
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
