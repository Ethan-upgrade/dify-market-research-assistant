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
    marks = re.findall(r"\[(\d+|K\d+)\]", body)
    per_source = {}
    for m in marks:
        per_source[m] = per_source.get(m, 0) + 1
    return {
        "body": body,
        "source_block": src,
        "web": web,
        "kb": kb,
        "cited_web": cited_web,
        "cited_kb": cited_kb,
        "chapters": chapters,
        "chars": len(text),
        "mark_total": len(marks),
        "per_source": per_source,
        "body_chars": len(body),
    }


def check_report(markdown: str, min_chars: int = 3000,
                 min_cited_ratio: float = 0.6, min_chapters: int = 7,
                 max_marks_per_100: float = 8.0, max_same_in_paragraph: int = 5) -> dict:
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

    # 引用密度：标注太多等于刷标，读者没法看
    body_chars = p["body_chars"] or 1
    density = p["mark_total"] * 100.0 / body_chars
    if density > max_marks_per_100:
        problems.append(
            f"引用密度过高（每百字 {density:.1f} 处 > 上限 {max_marks_per_100:.0f}），"
            f"共 {p['mark_total']} 处标注")

    # 同一编号在一段里反复出现
    spam = []
    for para in re.split(r"\n\s*\n", p["body"]):
        marks = re.findall(r"\[(\d+|K\d+)\]", para)
        if not marks:
            continue
        top = max(set(marks), key=marks.count)
        if marks.count(top) > max_same_in_paragraph:
            spam.append(f"[{top}]×{marks.count(top)}")
    if spam:
        problems.append(f"同一来源在一段内重复标注过多：{', '.join(spam[:5])}")

    # 连续三连标注 [a][b][c]（4 个及以上）通常是刷标
    runs = re.findall(r"(?:\[\d+\]){4,}", p["body"])
    if runs:
        problems.append(f"存在连续 4 个以上引用标注（{len(runs)} 处，如 {runs[0][:40]}）")

    # 表格里有「来源」列却整列空白 → 数字全裸，无出处
    blank_src_rows = count_blank_source_rows(p["body"])
    if blank_src_rows:
        problems.append(f"表格「来源」列有 {blank_src_rows} 行空白，数字无出处")

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
            "marks": p["mark_total"],
            "density": round(density, 2),
        },
    }

def count_blank_source_rows(body: str) -> int:
    """统计「来源」列整列空白的表格行数（表头最后一个是 来源/出处/引用）。"""
    bad = 0
    lines = body.split("\n")
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s.startswith("|") or "---" in s:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells:
            continue
        # 找本表的表头行（该行首格不是纯数字/数字+单位）
        header = None
        for j in range(i, max(-1, i - 40), -1):
            h = lines[j].strip()
            if h.startswith("|") and "---" not in h:
                hc = [c.strip() for c in h.strip("|").split("|")]
                if any(("来源" in c) or ("出处" in c) for c in hc):
                    header = hc
                    break
        if header is None or "来源" not in "".join(header) and "出处" not in "".join(header):
            continue
        if len(cells) == len(header) and cells[-1] == "":
            # 该行前面几列里有数字，但来源列空
            if re.search(r"\d", " ".join(cells[:-1])):
                bad += 1
    return bad
