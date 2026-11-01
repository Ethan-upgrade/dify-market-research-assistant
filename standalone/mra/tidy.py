"""确定性的小工具：不依赖模型的硬规则修正。

为什么需要：模型（尤其是快模型）在「输出长文档 + 同时遵守多条格式规则」这件事上不稳定。
体检能发现问题，但「报告不合格」不该是终点——凡是能确定性修好的，就直接修，修不了的才回退。

这里只做**不改变语义**的机械修正：
- 合并相邻的连写引用（[15][16][18][15][16] → [15][16]）
- 删除表格数据单元格里重复的编号（来源列已有，单元格里再标就是噪音）

绝不改文字、绝不增删数字、绝不删来源行。
"""

from __future__ import annotations

import re

_CITE = r"\[\d+\]|\[K\d+\]"
_CITE_RE = re.compile(_CITE)
_RUN_RE = re.compile(r"(?:" + _CITE + r"){3,}")


def _dedupe_run(run: str, keep: int = 2) -> str:
    """把一段连写标注按首次出现顺序去重，只留前 keep 个。"""
    nums = _CITE_RE.findall(run)
    seen = []
    for n in nums:
        if n not in seen:
            seen.append(n)
    return "".join(seen[:keep])


def collapse_citation_runs(text: str, keep: int = 2) -> str:
    """3 个及以上连写的引用 → 去重后保留 keep 个。"""
    return _RUN_RE.sub(lambda m: _dedupe_run(m.group(0), keep), text)


def strip_table_cell_citations(text: str) -> str:
    """表格里如果有「来源/出处」列，数据单元格内的标注删除（来源列保留）。

    只处理形如 `| a[1] | b[2] | [1][2] |` 的行：如果最后两列都有标注，删掉非最后列的。
    判定不了就原样返回，宁可不改。
    """
    out_lines = []
    header = None
    for line in text.split("\n"):
        s = line.strip()
        if not s.startswith("|") or set(s) <= set("|-: "):
            out_lines.append(line)
            continue

        cells = s.strip("|").split("|")
        joined = "".join(cells)
        if ("来源" in joined or "出处" in joined) and not _CITE_RE.search(joined):
            header = [c.strip() for c in cells]      # 表头行
            out_lines.append(line)
            continue

        if header and len(cells) == len(header) and _CITE_RE.search(cells[-1]):
            # 最后一列是来源列，且非空 → 清掉前面各列里的编号
            new_cells = [c if i == len(cells) - 1 else _CITE_RE.sub("", c)
                         for i, c in enumerate(cells)]
            if _CITE_RE.search(cells[-1]):
                out_lines.append("|" + "|".join(new_cells) + "|")
                continue

        out_lines.append(line)
    return "\n".join(out_lines)


def tidy(markdown: str, max_run: int = 2) -> str:
    """体检前/降噪后的机械整理：先清表格、再合并连写。"""
    return collapse_citation_runs(strip_table_cell_citations(markdown), keep=max_run)

def renumber_citations(body: str, source_list: str) -> tuple:
    """把来源表编号压成连续的 1..N，并同步改正文里的引用。

    为什么需要：写作时引用了 [1][3][18]，没用到的编号会被剔掉，来源表就跳号
    （11 直接到 13）。读者会以为漏了。这里按首次出现顺序重排，正文和来源表一起改，
    保证「表里第 3 条 = 正文 [3]」且没有空号。

    返回 (new_body, new_source_list)。
    """
    rows = []
    for ln in (source_list or "").split("\n"):
        m = re.match(r"^(K?\d+)\.\s+(.*)$", ln.strip())
        if m:
            rows.append((m.group(1), m.group(2)))

    nums = [n for n, _ in rows if not n.startswith("K")]
    if not nums:
        return body, source_list

    # 按「传入的行顺序」重排（调用方已排好：知识库 → 真实网页 → 引擎摘要），
    # 不能按旧编号排序，否则引擎摘要又会被顶回中间。
    order = [n for n, _ in rows if not n.startswith("K")]
    mapping = {old: str(i + 1) for i, old in enumerate(order)}

    def sub(m):
        token = m.group(1)
        return "[" + mapping.get(token, token) + "]"

    new_body = re.sub(r"\[(\d+)\]", sub, body)

    new_rows = []
    for old, rest in rows:
        if old.startswith("K"):
            new_rows.append(f"{old}. {rest}")
        else:
            new_rows.append(f"{mapping.get(old, old)}. {rest}")
    return new_body, "\n".join(new_rows)
