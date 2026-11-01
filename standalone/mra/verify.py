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
from .fetch import fetch_text as _fetch_text

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


def fetch(url: str, timeout: int = 12, fetcher: str = "auto") -> dict:
    r = _fetch_text(url, timeout, fetcher)
    if r["ok"]:
        return {"status": r["status"], "size": len(r["text"]), "verdict": "ok",
                "error": "", "engine": r["engine"]}
    code = r["status"]
    if "PDF" in (r["reason"] or ""):
        verdict = "pdf"
    else:
        verdict = "blocked" if code in (401, 403, 405, 412, 429) else "dead"
    return {"status": code, "size": 0, "verdict": verdict,
            "error": r["reason"], "engine": r["engine"]}


def check(markdown: str, timeout: int = 12, workers: int = 6, fetcher: str = "auto") -> dict:
    srcs = parse_sources(markdown)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        results = list(ex.map(lambda s: fetch(s["url"], timeout, fetcher), srcs))
    rows = []
    for s, r in zip(srcs, results):
        rows.append({**s, **r})
    ok = sum(1 for r in rows if r["verdict"] == "ok")
    blocked = sum(1 for r in rows if r["verdict"] == "blocked")
    dead = sum(1 for r in rows if r["verdict"] == "dead")
    pdf = sum(1 for r in rows if r["verdict"] == "pdf")
    return {"total": len(rows), "ok": ok, "blocked": blocked, "dead": dead,
            "pdf": pdf, "rows": rows}


def main(argv=None) -> int:
    try:                       # Windows 控制台默认非 UTF-8，中文输出会直接抛 UnicodeEncodeError
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(prog="mra.verify", description="报告来源链接体检")
    ap.add_argument("report", help="报告 Markdown 路径")
    ap.add_argument("--timeout", type=int, default=12)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--fetcher", default="auto",
                   choices=["auto", "urllib", "curl_cffi", "playwright", "firecrawl"])
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    with open(args.report, encoding="utf-8") as f:
        md = f.read()

    res = check(md, args.timeout, args.workers, args.fetcher)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        icon = {"ok": "OK ", "blocked": "BOT", "dead": "DEAD", "pdf": "PDF"}
        for r in res["rows"]:
            print(f"[{r['num']:>3}] {icon[r['verdict']]} {r['status']:>3} {r.get('engine',''):<10} {r['url'][:66]}")
            if r["verdict"] == "dead":
                print(f"       └ {r['error']}")
        print(f"\n合计 {res['total']} 条：正常 {res['ok']}，反爬拦截 {res['blocked']}，"
              f"PDF 无法比对 {res['pdf']}，死链 {res['dead']}")
    return 0 if res["dead"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
