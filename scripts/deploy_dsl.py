"""把 dsl/*.yml 导入（或更新）到一个 Dify 实例，并可选发布。

凭据只从环境变量或参数取，不写死任何账号密码。

用法：
  set DIFY_BASE=http://127.0.0.1:8080
  set DIFY_EMAIL=admin@example.com
  set DIFY_PASSWORD=***
  set TAVILY_KEY=tvly-***
  python scripts/deploy_dsl.py --file dsl/market-research-assistant-v3.yml --name "市场调研报告助手 v3" --publish

  --keep    复用上次的应用 ID（.dify-app-id 文件），只替换画布，分享链接不变
  --model   指定模型名（默认取 DIFY_MODEL，再默认 deepseek-chat）
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import requests
    import yaml
except ImportError:
    sys.exit("需要 requests 与 pyyaml：pip install requests pyyaml")

PROVIDER = "langgenius/openai_api_compatible/openai_api_compatible"
TEMPS = {"llm_brief": 0.3, "llm_analyze": 0.3, "llm_report": 0.7}
MAXES = {"llm_brief": 4096, "llm_analyze": 16384, "llm_report": 16384}


def env(name: str, default: str = "", required: bool = False) -> str:
    v = os.environ.get(name, default).strip()
    if required and not v:
        sys.exit(f"缺少环境变量 {name}")
    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=env("DIFY_BASE", "http://127.0.0.1:8080"))
    ap.add_argument("--email", default=env("DIFY_EMAIL"))
    ap.add_argument("--password", default=env("DIFY_PASSWORD"))
    ap.add_argument("--file", default="dsl/market-research-assistant-v3.yml")
    ap.add_argument("--name", default="市场调研报告助手 v3")
    ap.add_argument("--model", default=env("DIFY_MODEL", "deepseek-chat"))
    ap.add_argument("--keep", action="store_true", help="复用 .dify-app-id 里的应用，只换画布")
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()

    if not args.email or not args.password:
        sys.exit("需要 DIFY_EMAIL / DIFY_PASSWORD（或 --email/--password）")

    dsl_path = Path(args.file)
    if not dsl_path.is_file():
        dsl_path = Path(__file__).resolve().parent.parent / args.file
    dsl_text = dsl_path.read_text(encoding="utf-8")
    id_file = dsl_path.with_suffix(".app-id")
    tavily = env("TAVILY_KEY") or env("DIFY_TAVILY_KEY")

    s = requests.Session()
    s.trust_env = False
    r = s.post(f"{args.base}/console/api/login",
               json={"email": args.email, "password": args.password,
                     "language": "zh-Hans", "remember_me": True}, timeout=60)
    if r.status_code >= 400:
        sys.exit(f"登录失败 {r.status_code}: {r.text[:300]}")
    s.headers.update({"Authorization": "Bearer " + r.json()["data"]["access_token"]})

    def env_variables():
        if not tavily:
            return []
        return [{
            "id": "3f7b2c41-9d5e-4a8c-b1f6-2e4d7a9c0b13",
            "name": "TAVILY_API_KEY", "value": tavily, "value_type": "secret",
            "description": "Tavily 搜索 API Key", "selector": ["env", "TAVILY_API_KEY"],
        }]

    def wire_llm(graph):
        for node in graph["nodes"]:
            d = node.get("data", {})
            if d.get("type") != "llm":
                continue
            nid = node["id"]
            d["model"] = {"provider": PROVIDER, "name": args.model, "mode": "chat",
                          "completion_params": {"temperature": TEMPS.get(nid, 0.4),
                                                "max_tokens": MAXES.get(nid, 4096)}}
            print("  wired", nid)

    doc = yaml.safe_load(dsl_text)
    wf = doc["workflow"]

    if args.keep and id_file.exists():
        app_id = id_file.read_text(encoding="utf-8").strip()
        print("复用应用:", app_id)
        graph = wf["graph"]
        wire_llm(graph)
        cur = s.get(f"{args.base}/console/api/apps/{app_id}/workflows/draft", timeout=60).json()
        payload = {"graph": graph, "features": cur.get("features") or wf["features"],
                   "hash": cur.get("hash"), "environment_variables": env_variables(),
                   "conversation_variables": cur.get("conversation_variables") or []}
    else:
        apps = s.get(f"{args.base}/console/api/apps", params={"page": 1, "limit": 100}, timeout=60).json()["data"]
        for a in apps:
            if a["name"] == args.name:
                rr = s.delete(f"{args.base}/console/api/apps/{a['id']}", timeout=60)
                print(f"删除同名旧应用 {a['name']!r} -> {rr.status_code}")

        r = s.post(f"{args.base}/console/api/apps/imports",
                   json={"mode": "yaml-content", "yaml_content": dsl_text}, timeout=240)
        print("import:", r.status_code)
        if r.status_code >= 400:
            print(r.text[:1500])
            return 1
        app_id = r.json()["app_id"]
        print("app_id:", app_id)

        draft = s.get(f"{args.base}/console/api/apps/{app_id}/workflows/draft", timeout=60).json()
        print("节点数:", len(draft["graph"]["nodes"]))
        wire_llm(draft["graph"])
        payload = {"graph": draft["graph"], "features": draft["features"],
                   "hash": draft.get("hash"), "environment_variables": env_variables(),
                   "conversation_variables": draft.get("conversation_variables", [])}

    r = s.post(f"{args.base}/console/api/apps/{app_id}/workflows/draft", json=payload, timeout=240)
    print("sync draft:", r.status_code)
    if r.status_code >= 400:
        print(r.text[:1500])
        return 1

    if args.publish:
        r = s.post(f"{args.base}/console/api/apps/{app_id}/workflows/publish", timeout=120)
        print("publish:", r.status_code, r.text[:120])

    id_file.write_text(app_id, encoding="utf-8")
    print("已保存应用 ID 到", id_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
