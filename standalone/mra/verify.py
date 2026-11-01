"""来源链接体检：把报告里每条来源真的抓一遍，标出死链/被墙/正常。

    python -m mra.verify report.md
    python -m mra.verify report.md --json --workers 8 --timeout 15

为什么要它：`check_report()` 只能校验「报告内部自洽」（编号对得上、来源表齐全），
但来源 URL 本身可能 404、域名失效、或站点反爬。交付前跑一遍，才知道哪些引用能点开。

退出码：0 = 没有死链（被反爬拦不算死链）；1 = 存在死链。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .checks import parse_report

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

SRC_LINE = re.compile(r"^(K?\d+)\.\s+(.*?)\s+—\s+(https?://\S+)\s*$")


def parse_sources(markdown: str) -> list:
    p = parse_report(markdown)
    out = []
    for ln in p["source_block"].split("\n"):
        m = SRC_LINE.match(ln.strip())
        if m:
            out.append({"num": m.group(1), "title": m.group(2), "url": m.group(3)})
    return out


def fetch(url: str, timeout: int = 12) -> dict:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            size = len(r.read(65536))
            return {"status": r.status, "size": size, "verdict": "ok", "error": ""}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 405, 412, 429):
            return {"status": e.code, "size": 0, "verdict": "blocked", "error": f"HTTP {e.code}"}
        return {"status": e.code, "size": 0, "verdict": "dead", "error": f"HTTP {e.code}"}
    except Exception as e:                      # DNS / 超时 / TLS
        return {"status": 0, "size": 0, "verdict": "dead", "error": str(e)[:80]}


def check(markdown: str, timeout: int = 12, workers: int = 6) -> dict:
    srcs = parse_sources(markdown)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        results = list(ex.map(lambda s: fetch(s["url"], timeout), srcs))
    rows = []
    for s, r in zip(srcs, results):
        rows.append({**s, **r})
    ok = sum(1 for r in rows if r["verdict"] == "ok")
    blocked = sum(1 for r in rows if r["verdict"] == "blocked")
    dead = sum(1 for r in rows if r["verdict"] == "dead")
    return {"total": len(rows), "ok": ok, "blocked": blocked, "dead": dead, "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mra.verify", description="报告来源链接体检")
    ap.add_argument("report", help="报告 Markdown 路径")
    ap.add_argument("--timeout", type=int, default=12)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    with open(args.report, encoding="utf-8") as f:
        md = f.read()

    res = check(md, args.timeout, args.workers)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        icon = {"ok": "OK ", "blocked": "BOT", "dead": "DEAD"}
        for r in res["rows"]:
            print(f"[{r['num']:>3}] {icon[r['verdict']]} {r['status']:>3} {r['url'][:78]}")
            if r["verdict"] == "dead":
                print(f"       └ {r['error']}")
        print(f"\n合计 {res['total']} 条：正常 {res['ok']}，反爬拦截 {res['blocked']}，死链 {res['dead']}")
    return 0 if res["dead"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
