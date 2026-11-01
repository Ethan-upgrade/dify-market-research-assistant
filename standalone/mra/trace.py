"""数字溯源：表格里的每个数字，能不能在它引用的那一页上找到？

`check_report()` 保证「编号对得上」，`verify.py` 保证「链接打得开」，
但这个数字**是不是真的来自那篇文章**，之前只能靠模型自觉。这个模块补最后一环。

为什么只查表格
--------------
正文一句话里常有多个数字、多个来源，硬做「数字↔来源」配对误报极高（试过：命中率 34%，
大量是模型自己算的同比、或是四舍五入）。而表格天然是「一行一个来源」的结构：

    | 指标 | 数值 | 年份 | 来源 |
    | 户储新增装机 | 1,640 MWh（同比 +7%） | 2023 | [9] |

一行只对应一个 [n]，数字归属没有歧义。所以只核验表格，宁少勿滥。

结果分三档：
- `verified`   页面抓到了，该行数字全部命中
- `not_found`  页面抓到了，但有数字没出现（疑似改口径/换单位/编造）
- `unreachable` 页面抓不到（403/超时/PDF），无法判断

用法：
    python -m mra.trace report.md --workers 6
    python -m mra.trace report.md --json --min-ratio 0.5
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .checks import parse_report

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")

SRC_LINE = re.compile(r"^(K?\d+)\.\s+(.*?)\s+—\s+(https?://\S+)\s*$")
NUM = re.compile(r"\d[\d,，]*(?:\.\d+)?")
CITE = re.compile(r"\[(\d+|K\d+)\]")


def norm_num(s: str) -> str:
    return s.replace(",", "").replace("，", "").replace(" ", "")


def as_float(s: str):
    try:
        return float(norm_num(s))
    except ValueError:
        return None


def numbers_in(text: str) -> list:
    """取数字，跳过年份（2020~2035）和无意义的小序号。"""
    out = []
    for m in NUM.findall(text or ""):
        v = as_float(m)
        if v is None:
            continue
        if "." not in m and 1900 <= v <= 2100:      # 年份
            continue
        if "." not in m and v < 1:                  # 0 之类
            continue
        out.append(norm_num(m))
    return out


def page_numbers(text: str) -> set:
    vals = set()
    for m in NUM.findall(text or ""):
        v = as_float(m)
        if v is not None:
            vals.add(v)
    return vals


def hit(value: str, pages: set) -> bool:
    v = as_float(value)
    if v is None:
        return False
    if v in pages:
        return True
    tol = max(1.0, abs(v) * 0.005)          # 允许四舍五入
    return any(abs(v - p) <= tol for p in pages)


def fetch_text(url: str, timeout: int = 15, fetcher: str = "auto") -> dict:
    from .fetch import fetch_text as _ft
    r = _ft(url, timeout, fetcher)
    return {"ok": r["ok"], "reason": r["reason"], "text": r["text"], "engine": r["engine"]}


def tables(markdown: str) -> list:
    """返回 [{header:[...], rows:[[cell,...], ...]}]"""
    body = parse_report(markdown)["body"]
    out, cur = [], None
    for line in body.split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            if cur:
                out.append(cur)
            cur = None
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if set(s) <= set("|-: "):
            continue
        if cur is None:
            cur = {"header": cells, "rows": []}
        else:
            cur["rows"].append(cells)
    if cur:
        out.append(cur)
    return out


def extract_claims(markdown: str) -> list:
    srcs = {}
    for ln in parse_report(markdown)["source_block"].split("\n"):
        m = SRC_LINE.match(ln.strip())
        if m:
            srcs[m.group(1)] = {"title": m.group(2), "url": m.group(3)}

    claims = []
    for tb in tables(markdown):
        header = tb["header"]
        src_idx = next((i for i, h in enumerate(header) if "来源" in h or "出处" in h), None)
        if src_idx is None:
            continue
        for row in tb["rows"]:
            if len(row) != len(header):
                continue
            cites = CITE.findall(row[src_idx])
            num_cells = [c for i, c in enumerate(row) if i != src_idx and i != 0]
            nums = []
            for c in num_cells:
                nums.extend(numbers_in(c))
            nums = sorted(set(nums), key=lambda x: -len(x))
            if not nums:
                continue
            for c in cites:
                if c.startswith("K") or c not in srcs:
                    continue
                claims.append({
                    "cite": c, "row": row[0][:40], "numbers": nums,
                    "title": srcs[c]["title"], "url": srcs[c]["url"],
                })
    return claims


def check(markdown: str, timeout: int = 15, workers: int = 6, fetcher: str = "auto") -> dict:
    claims = extract_claims(markdown)
    urls = sorted({c["url"] for c in claims})
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        pages = dict(zip(urls, ex.map(lambda u: fetch_text(u, timeout, fetcher), urls)))

    rows = []
    for c in claims:
        pg = pages[c["url"]]
        if not pg["ok"]:
            rows.append({**c, "verdict": "unreachable", "reason": pg["reason"],
                         "hit": [], "miss": c["numbers"]})
            continue
        nums = page_numbers(pg["text"])
        hits = [n for n in c["numbers"] if hit(n, nums)]
        miss = [n for n in c["numbers"] if n not in hits]
        rows.append({**c, "verdict": "verified" if not miss else "not_found",
                     "reason": "", "hit": hits, "miss": miss})

    total = sum(len(r["numbers"]) for r in rows)
    hitn = sum(len(r["hit"]) for r in rows)
    return {
        "claims": len(rows), "numbers": total, "hit": hitn,
        "ratio": round(hitn / total, 4) if total else 0.0,
        "verified": sum(1 for r in rows if r["verdict"] == "verified"),
        "not_found": sum(1 for r in rows if r["verdict"] == "not_found"),
        "unreachable": sum(1 for r in rows if r["verdict"] == "unreachable"),
        "rows": rows,
    }


def main(argv=None) -> int:
    try:                       # Windows 控制台默认非 UTF-8，中文输出会直接抛 UnicodeEncodeError
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(prog="mra.trace", description="表格数字溯源核验")
    ap.add_argument("report")
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--fetcher", default="auto",
                   choices=["auto", "urllib", "curl_cffi", "playwright", "firecrawl"])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--min-ratio", type=float, default=-1,
                   help="可选：命中率低于该值退出码 1（默认不卡，只做提示）")
    args = ap.parse_args(argv)

    with open(args.report, encoding="utf-8") as f:
        md = f.read()
    res = check(md, args.timeout, args.workers, args.fetcher)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for r in res["rows"]:
            if r["verdict"] == "not_found":
                print(f"[{r['cite']:>2}] MISS 未在原文找到 {','.join(r['miss'])[:50]:<50} {r['row'][:26]}")
            elif r["verdict"] == "unreachable":
                print(f"[{r['cite']:>2}] N/A  {r['reason']:<30} {r['row'][:26]}")
        print(f"\n表格论断 {res['claims']} 条 / 数字 {res['numbers']} 个")
        print(f"  · 整行数字都能在原文找到：{res['verified']} 行")
        print(f"  · 有数字没找到（需人工复核，可能是改口径/换单位/四舍五入）：{res['not_found']} 行")
        print(f"  · 页面打不开（403/PDF/超时），无法判断：{res['unreachable']} 行")
        print("  说明：本工具只做「页面文本里有没有这个数」的机械比对，不判断数字是否被正确解读。")
    if args.min_ratio >= 0 and res["ratio"] < args.min_ratio:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
