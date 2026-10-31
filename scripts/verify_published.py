"""通过「已发布版本」的 service API 验证链路与报告质量。

  --mode smoke  默认。一句笼统提问，只验链路通、追问分支正常、控制标记不外泄。约 5 秒、几乎不花检索额度。
  --mode full   明确提问 + 6 个范围参数，跑完整调研并校验：章节数、来源表、悬空引用、自造标注、利用率。

用法：
  python scripts/verify_published.py --app-id <APP_ID> --mode smoke
  python scripts/verify_published.py --app-id <APP_ID> --mode full --out report.md

APP_ID 也可以从 .dify-app-id 文件读取（deploy_dsl.py 会写）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("需要 requests：pip install requests")

SMOKE_QUERY = "你好"
FULL_QUERY = ("帮我调研 Nespresso 胶囊咖啡的市场情况，覆盖中国与全球市场，"
              "用于竞品分析，需要市场规模、竞争格局与增长趋势，时间范围近三年")
FULL_INPUTS = {
    "market_scope": "中国 + 全球对照", "industry": "消费品/快消",
    "research_purpose": "竞品分析", "time_range": "近三年",
    "source_pref": "优先券商研报/咨询报告", "depth": "3",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("DIFY_BASE", "http://127.0.0.1:8080"))
    ap.add_argument("--email", default=os.environ.get("DIFY_EMAIL", ""))
    ap.add_argument("--password", default=os.environ.get("DIFY_PASSWORD", ""))
    ap.add_argument("--app-id", default="")
    ap.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    ap.add_argument("--query", default="")
    ap.add_argument("--inputs-file", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--min-cited-ratio", type=float, default=0.6)
    args = ap.parse_args()

    app_id = args.app_id
    if not app_id:
        f = Path("dsl/market-research-assistant-v3.app-id")
        if f.is_file():
            app_id = f.read_text(encoding="utf-8").strip()
    if not app_id:
        sys.exit("缺少 --app-id（或先跑 deploy_dsl.py 生成 .app-id）")

    full = args.mode == "full"
    query = args.query or (FULL_QUERY if full else SMOKE_QUERY)

    inputs = {}
    if args.inputs_file:
        inputs = json.loads(Path(args.inputs_file).read_text(encoding="utf-8"))
    elif full:
        inputs = dict(FULL_INPUTS)

    print(f"mode={args.mode}  query={query[:40]}...")
    print("inputs:", json.dumps(inputs, ensure_ascii=False))

    s = requests.Session()
    s.trust_env = False
    r = s.post(f"{args.base}/console/api/login",
               json={"email": args.email, "password": args.password,
                     "language": "zh-Hans", "remember_me": True}, timeout=60)
    s.headers.update({"Authorization": "Bearer " + r.json()["data"]["access_token"]})

    keys = s.get(f"{args.base}/console/api/apps/{app_id}/api-keys", timeout=60).json().get("data") or []
    if keys:
        key = keys[0]["token"]
        print("复用 api key", keys[0]["id"])
    else:
        key = s.post(f"{args.base}/console/api/apps/{app_id}/api-keys", json={}, timeout=60).json()["token"]
        print("新建 api key")

    r = requests.post(
        f"{args.base}/v1/chat-messages",
        json={"inputs": inputs, "query": query, "response_mode": "blocking",
              "conversation_id": "", "user": "verify-published"},
        headers={"Authorization": "Bearer " + key}, timeout=900,
    )
    print("status", r.status_code)
    d = r.json()
    if r.status_code != 200:
        print(json.dumps(d, ensure_ascii=False)[:600])
        return 1

    ans = d.get("answer", "")
    leak = "<!--" in ans or "引用清单" in ans
    print("marker leak:", leak, "| chars:", len(ans))
    if args.out:
        Path(args.out).write_text(ans, encoding="utf-8")
        print("saved", args.out)

    if not full:
        if leak:
            print("FAIL: 控制标记/引用清单泄漏")
            return 1
        if not ans.strip():
            print("FAIL: 空答案")
            return 1
        print("answer:", ans[:200].replace("\n", " "))
        print("\nSMOKE PASS")
        return 0

    chapters = [ln for ln in ans.split("\n") if ln.startswith("## ")]
    has_sources = "参考来源" in ans
    body, _, src = ans.rpartition("## 参考来源")
    web = [int(x) for x in re.findall(r"^(\d+)\. ", src, re.M)]
    kb = [int(x) for x in re.findall(r"^K(\d+)\. ", src, re.M)]
    cited_web = {int(x) for x in re.findall(r"\[(\d+)\]", body)}
    cited_kb = {int(x) for x in re.findall(r"\[K(\d+)\]", body)}
    dangling = sorted(n for n in cited_web if n not in web) + sorted(k for k in cited_kb if k not in kb)
    ratio = len(cited_web & set(web)) / len(web) if web else 0.0
    bad_marks = sorted(set(re.findall(r"\[(?:搜索[A-Z]?|来源[A-Z]?|[0-9]+[a-zA-Z])\]", body)))

    print(f"chapters={len(chapters)} sources: web={len(web)} kb={len(kb)}")
    print(f"cite ratio: {ratio:.0%} (下限 {args.min_cited_ratio:.0%})")
    print("dangling refs:", dangling or "无")
    print("自造引用标注:", bad_marks or "无")

    problems = []
    if leak:
        problems.append("控制标记泄漏")
    if len(ans) < 3000:
        problems.append(f"报告过短（{len(ans)} 字）")
    if not has_sources:
        problems.append("缺少「参考来源」")
    if len(chapters) < 7:
        problems.append(f"章节不足（{len(chapters)} < 7）")
    if dangling:
        problems.append(f"悬空引用 {dangling}")
    if bad_marks:
        problems.append(f"自造引用标注 {bad_marks}")
    if ratio < args.min_cited_ratio:
        problems.append(f"来源利用率 {ratio:.0%} 低于下限")

    if problems:
        for p in problems:
            print("FAIL:", p)
        return 1
    print("\nFULL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
