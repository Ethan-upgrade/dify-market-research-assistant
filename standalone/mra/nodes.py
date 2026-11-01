"""纯函数节点层 —— 与 DSL 里的 Code 节点一一对应。

全部无副作用、无网络，可以直接单测（见 tests/test_nodes.py）。
"""

from __future__ import annotations

import json
import re


# ------------------------------------------------ ② 清洗简报（code_brief）
def clean_brief(raw: str) -> dict:
    text = (raw or "").replace("\r", "")
    ready = "yes" if "<!--READY-->" in text else "no"
    clarify = "yes" if "<!--CLARIFY-->" in text else "no"
    lines = [ln for ln in text.split("\n") if "<!--" not in ln]
    clean = "\n".join(lines).strip()
    question = ""
    if clarify == "yes":
        cand = [ln.strip() for ln in clean.split("\n") if ln.strip()]
        question = cand[0] if cand else "请补充：要调研的具体行业/品类，以及目标市场（国家或地区）？"
    return {"text": clean[:4000], "ready": ready, "clarify": clarify, "question": question}


# ------------------------------------------ ② 生成初始检索式（code_seed）
def seed_queries(brief: str, fallback: str, geo: str) -> dict:
    text = (brief or "").replace("\r", "")
    q1 = q2 = ""
    industry = market = ""
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("初始检索式1："):
            q1 = s.split("：", 1)[1].strip()
        elif s.startswith("初始检索式2："):
            q2 = s.split("：", 1)[1].strip()
        elif s.startswith("所属行业："):
            industry = s.split("：", 1)[1].strip()
        elif s.startswith("目标市场："):
            market = s.split("：", 1)[1].strip()

    geo = (geo or "").strip()
    if geo and geo != "全球":
        market = geo

    prefix = " ".join(x for x in (market, industry) if x).strip()
    if not prefix:
        prefix = (fallback or "市场").strip()[:30]

    if len(q1) < 4:
        q1 = prefix + " 市场规模 增长率"
    if len(q2) < 4 or q2 == q1:
        q2 = prefix + " 竞争格局 市场份额 主要厂商"
    return {"q1": q1[:80], "q2": q2[:80]}


# ------------------------------------------------ ④ 取本轮检索式（code_pick）
def pick_round(cur_q1: str, cur_q2: str, seed_q1: str, seed_q2: str,
               knowledge: str, max_rounds: int) -> dict:
    q1 = (cur_q1 or "").strip() or (seed_q1 or "").strip()
    q2 = (cur_q2 or "").strip() or (seed_q2 or "").strip()
    if q2 == q1:
        q2 = (seed_q2 or q2).strip()
    round_no = 1 + (knowledge or "").count("=== 第")
    try:
        max_rounds = int(max_rounds)
    except (TypeError, ValueError):
        max_rounds = 3
    left = max(0, max_rounds - round_no + 1)
    return {
        "q1": q1[:80], "q2": q2[:80], "round": round_no,
        "max_rounds": max_rounds, "rounds_left": left,
        "is_last": "yes" if left <= 1 else "no",
    }


# -------------------------------------------- ⑦ 去重 + 编号（code_pack）
def _clean(text, limit):
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text.replace("|", "｜")[:limit]


def pack_results(raw_a: dict, raw_b: dict, registry: str,
                 kb: str = "", kb_registry: str = "", round_no: int = 1,
                 max_per_query: int = 6) -> dict:
    lines = [ln for ln in (registry or "").split("\n") if ln.strip()]

    known = {}
    maxn = 0
    for ln in lines:
        parts = [p.strip() for p in ln.split("|")]
        if len(parts) >= 3 and parts[0].isdigit():
            known[parts[2]] = parts[0]
            maxn = max(maxn, int(parts[0]))

    out = []
    added = 0

    # 知识库片段只在第 1 轮注入，编号 K1..Kn
    if str(round_no) == "1" and (kb or "").strip():
        out.append("===== 内部知识库（历史报告） =====")
        out.append(kb.strip())
        for ln in (kb_registry or "").split("\n"):
            if ln.strip():
                lines.append(ln.strip())
                added += 1

    for tag, data in (("A", raw_a), ("B", raw_b)):
        if not isinstance(data, dict):
            data = {}

        answer = _clean(data.get("answer"), 700)
        if answer:
            key = "answer://" + tag
            if key in known:
                snum = known[key]
            else:
                maxn += 1
                snum = str(maxn)
                known[key] = snum
                added += 1
                lines.append(snum + " | Tavily 引擎摘要（检索式" + tag + "） | Tavily answer 字段 | ")
            out.append("[" + snum + "] Tavily 引擎摘要（检索式" + tag + "）\n" + answer)

        results = data.get("results") or []
        if not isinstance(results, list):
            results = []
        for item in results[:max_per_query]:
            if not isinstance(item, dict):
                continue
            url = (item.get("url") or "").strip()
            if not url:
                continue
            title = _clean(item.get("title"), 100)
            date = _clean(item.get("published_date"), 10)
            body = _clean(item.get("content"), 900)

            if url in known:
                num = known[url]
            else:
                maxn += 1
                num = str(maxn)
                known[url] = num
                added += 1
                lines.append(num + " | " + (title or "未命名来源") + " | " + url + " | " + date)

            out.append("[" + num + "] " + title + " (" + date + ")\n" + body)

    numbered = "\n\n".join(out) if out else "（本轮检索没有返回任何结果）"
    return {"numbered": numbered, "registry": "\n".join(lines),
            "new_count": added, "total_count": len(lines)}


# --------------------------------------------- ⑨ 拆解本轮结果（code_parse）
OFFTOPIC_MARKS = (
    "本轮材料与主题无关", "主题不明", "跑题", "无关内容",
    "素材不含任何具体", "不含任何具体", "无具体行业",
    "无法支撑", "无法形成结论", "没有可提炼", "缺乏具体",
    "不具备交付条件", "缺少调研对象",
)


def parse_analyze(analyze: str, knowledge: str, registry: str,
                  new_count: int, fallback: str) -> dict:
    text = (analyze or "").replace("\r", "")
    lines = text.split("\n")

    queries, keep = [], []
    upper_all = text.upper()
    for line in lines:
        s = line.strip()
        up = s.upper()
        if up.startswith("QUERY") or up.startswith("检索式"):
            val = s
            for sep in ("：", ":"):
                if sep in s:
                    val = s.split(sep, 1)[1].strip()
                    break
            val = val.strip(" -•*[]()\"'")
            if len(val) >= 4 and val.upper() not in ("QUERY1", "QUERY2"):
                queries.append(val)
            continue
        if s.startswith("【下一轮检索式】"):
            continue
        keep.append(line)

    body = "\n".join(keep).strip()
    if "DONE" in upper_all and "【" not in body:
        body = body.replace("DONE", "").strip()

    prev = (knowledge or "").strip()
    rounds = prev.count("=== 第") + 1
    chunk = "=== 第 " + str(rounds) + " 轮 ===\n" + (body or "（本轮无有效要点）")
    merged = (prev + "\n\n" + chunk).strip() if prev else chunk

    done = "no"
    if "DONE" in upper_all or not queries:
        done = "yes"
    try:
        if int(new_count or 0) == 0:
            done = "yes"
    except (TypeError, ValueError):
        pass

    total_rows = len([ln for ln in (registry or "").split("\n") if ln.strip()])
    offtopic = "no"
    if rounds >= 1 and total_rows == 0:
        offtopic = "yes"
    if any(k in text for k in OFFTOPIC_MARKS):
        offtopic = "yes"

    uniq = []
    for q in queries:
        if q not in uniq:
            uniq.append(q)
    prefix = (fallback or "该市场").strip()[:30]
    while len(uniq) < 2:
        uniq.append(prefix + (" 最新数据 增速" if len(uniq) == 0 else " 份额 排名 价格"))

    return {"knowledge": merged, "registry": registry or "",
            "q1": uniq[0][:80], "q2": uniq[1][:80],
            "done": done, "offtopic": offtopic}


# ---------------------------------------- ⑪ 汇总材料与来源表（code_sources）
def summarize_sources(knowledge: str, registry: str) -> dict:
    materials = (knowledge or "").strip()
    if not materials:
        materials = ("（本次检索没有返回任何材料：请确认 TAVILY_API_KEY 有效，"
                     "或改用 --search fixture 离线回放）")

    rows = [ln for ln in (registry or "").split("\n") if ln.strip()]
    lines, kb_lines, all_nums, all_k = [], [], [], []
    for ln in rows:
        parts = [p.strip() for p in ln.split("|")]
        num = parts[0] if parts else ""
        title = parts[1] if len(parts) > 1 else ""
        url = parts[2] if len(parts) > 2 else ""
        date = parts[3] if len(parts) > 3 else ""
        if not num:
            continue
        when = "（" + date + "）" if date else ""
        tail = " — " + url if url else ""
        entry = num + ". " + (title or "未命名来源") + when + tail
        if num.startswith("K"):
            kb_lines.append(entry)
            all_k.append(num)
        else:
            lines.append(entry)
            all_nums.append(num)

    source_list = "\n".join(kb_lines + lines) if (kb_lines or lines) else "（本次没有取得可用来源）"

    cited = set(re.findall(r"\[([0-9]+|K[0-9]+)\]", materials))
    unused_web = [n for n in all_nums if n not in cited]
    unused_kb = [k for k in all_k if k not in cited]
    unused = "、".join("[" + x + "]" for x in (unused_kb + unused_web))
    if not unused:
        unused = "无（所有来源都已被引用）"

    return {"materials": materials, "source_list": source_list,
            "n_sources": len(lines) + len(kb_lines), "n_kb": len(kb_lines),
            "unused": unused}


# ------------------------------------- ⑫ᵇ 按实际引用生成来源表（code_cite）
def build_cited_table(text: str, source_list: str) -> dict:
    raw = (text or "").replace("\r", "")
    body = raw

    cited = []
    m = re.search(r"^\s*引用清单[:：]\s*(.+)$", raw, re.M)
    if m:
        cited = re.findall(r"(K?[0-9]+)", m.group(1))
        body = (raw[: m.start()] + raw[m.end():]).strip()

    body = re.sub(r"<!--.*?-->", "", body, flags=re.S).strip()

    if not cited:
        cited = re.findall(r"\[([0-9]+|K[0-9]+)\]", body)

    order = []
    for c in cited:
        if c not in order:
            order.append(c)

    rows = {}
    for ln in (source_list or "").split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        mm = re.match(r"^(K?[0-9]+)\.\s", ln)
        if mm:
            rows[mm.group(1)] = ln

    picked_k = [c for c in order if c.startswith("K") and c in rows]
    picked_n = sorted([c for c in order if not c.startswith("K") and c in rows],
                      key=lambda x: int(x))
    # 真实来源在前，搜索引擎摘要垫底（它不是原始出处）
    real = [c for c in picked_n if "Tavily 引擎摘要" not in rows[c]]
    engine = [c for c in picked_n if "Tavily 引擎摘要" in rows[c]]
    final = picked_k + real + engine

    lines = [rows[c] for c in final]
    cited_list = "\n".join(lines) if lines else "（正文没有引用任何来源）"
    return {"body": body, "cited_list": cited_list,
            "n_cited": len(lines), "dropped": max(0, len(rows) - len(lines))}
