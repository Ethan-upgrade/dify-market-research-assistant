"""输出校验规则 —— 从流程里抽出来的「报告合格线」。

为什么单独抽：以前这些判断散在 verify_published.py 里，只能对线上应用跑；
抽成纯函数后，CLI 出完报告能自己体检，CI 也能测。

对应文档：docs/06-prompt-design.md 的「引用规则」。
"""

from __future__ import annotations

import re

# 模型偶尔会自造这类标注，一律判定不合格
BAD_MARK_RE = re.compile(r"\[(?:搜索[A-Z]?|来源[A-Z]?|[0-9]+[a-zA-Z]+)\]")


def parse_report(markdown: str) -> dict:
    """把一份报告拆成：正文、来源表里登记的编号、正文实际引用的编号。"""
    text = markdown or ""
    body, sep, src = text.rpartition("## 参考来源")
    if not sep:                      # 没有来源表，整篇当正文
        body, src = text, ""

    web = [int(x) for x in re.findall(r"^(\d+)\. ", src, re.M)]
    kb = [int(x) for x in re.findall(r"^K(\d+)\. ", src, re.M)]
    cited_web = {int(x) for x in re.findall(r"\[(\d+)\]", body)}
    cited_kb = {int(x) for x in re.findall(r"\[K(\d+)\]", body)}
    chapters = [ln for ln in body.split("\n") if ln.startswith("## ")]
    return {
        "body": body,
        "source_block": src,
        "web": web,
        "kb": kb,
        "cited_web": cited_web,
        "cited_kb": cited_kb,
        "chapters": chapters,
        "chars": len(text),
    }


def check_report(markdown: str, min_chars: int = 3000,
                 min_cited_ratio: float = 0.6, min_chapters: int = 7) -> dict:
    """体检一份报告，返回 {ok, problems[], metrics{}}。"""
    p = parse_report(markdown)
    problems = []

    if "<!--" in markdown or "引用清单" in markdown:
        problems.append("控制标记/引用清单泄漏到了正文")

    if p["chars"] < min_chars:
        problems.append(f"报告过短（{p['chars']} < {min_chars} 字）")

    if not p["source_block"]:
        problems.append("缺少「参考来源」章节")

    if len(p["chapters"]) < min_chapters:
        problems.append(f"章节不足（{len(p['chapters'])} < {min_chapters}）")

    dangling = sorted(n for n in p["cited_web"] if n not in set(p["web"]))
    dangling_kb = sorted(k for k in p["cited_kb"] if k not in set(p["kb"]))
    if dangling or dangling_kb:
        problems.append(f"悬空引用 web={dangling} kb={dangling_kb}")

    bad_marks = sorted(set(BAD_MARK_RE.findall(p["body"])))
    if bad_marks:
        problems.append(f"自造引用标注 {bad_marks}")

    total_web = len(p["web"])
    used = len(p["cited_web"] & set(p["web"]))
    ratio = (used / total_web) if total_web else 0.0
    if ratio < min_cited_ratio:
        problems.append(f"来源利用率 {ratio:.0%} 低于下限 {min_cited_ratio:.0%}")

    return {
        "ok": not problems,
        "problems": problems,
        "metrics": {
            "chars": p["chars"],
            "chapters": len(p["chapters"]),
            "web": total_web,
            "kb": len(p["kb"]),
            "cited": used,
            "ratio": round(ratio, 4),
        },
    }
