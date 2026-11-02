"""从一句话里猜调研范围。

两种模式：
- `guess()`：纯关键词规则，**不花 token**，毫秒级。用于 `--smart`。
- `infer()`：让模型读一遍 query 输出 JSON，**花一次小调用**（约 1~2k tokens）。用于 `--auto-scope`。

两者都只填「用户没显式指定」的字段；显式参数优先。
"""

from __future__ import annotations

import json
import re

from .aliases import (MARKET_ALIASES, INDUSTRY_ALIASES, PURPOSE_ALIASES,
                      TIME_ALIASES, normalize)
from .config import MARKET_OPTIONS, INDUSTRY_OPTIONS, PURPOSE_OPTIONS, TIME_OPTIONS

# 关键词 → 行业。按顺序匹配，命中即停。
INDUSTRY_RULES = [
    (("德语", "法语", "日语", "英语", "外语", "语言", "留学", "雅思", "托福", "培训", "教育", "课程", "考试", "证书"),
     "教育"),
    (("咖啡", "奶粉", "宠物", "食品", "饮料", "美妆", "护肤", "服装", "快消", "零食"), "消费品/快消"),
    (("saas", "软件", "云计算", "大模型", "ai", "芯片", "半导体", "互联网"), "科技/软件/SaaS"),
    (("储能", "电池", "光伏", "电动车", "新能源汽车", "充电桩"), "新能源/汽车"),
    (("医药", "医疗", "器械", "生物", "医院", "健康"), "医疗健康"),
    (("机床", "工业", "制造", "机器人", "自动化"), "工业制造"),
    (("支付", "银行", "保险", "券商", "金融", "信贷"), "金融/支付"),
    (("游戏", "影视", "短视频", "内容", "文娱", "音乐"), "文娱/内容"),
    (("电商", "零售", "跨境", "亚马逊", "独立站"), "跨境电商/零售"),
]

PURPOSE_RULES = [
    (("竞品", "对手", "对比", "份额", "排名"), "竞品分析"),
    (("进入", "出海", "落地", "开拓", "市场机会", "值不值得做"), "市场进入"),
    (("立项", "新品", "要不要做", "产品定义", "可行性"), "新品立项"),
    (("投资", "尽调", "估值", "融资", "赛道"), "投资尽调"),
    (("定价", "价格", "收费", "客单价"), "定价策略"),
    (("渠道", "经销", "代理", "铺货", "线上", "线下"), "渠道策略"),
    (("前景", "趋势", "概览", "现状", "怎么样", "全貌", "周期", "学习方法"), "行业概览"),
]

MARKET_RULES = [
    (("中国", "国内", "大陆", "人民币"), "中国大陆"),
    (("北美", "美国", "加拿大"), "北美"),
    (("欧洲", "德国", "法国", "英国", "欧盟"), "欧洲"),
    (("东南亚", "越南", "印尼", "泰国"), "东南亚"),
    (("日本", "韩国", "日韩"), "日韩"),
    (("中东", "沙特", "阿联酋"), "中东"),
    (("全球", "世界", "海外", "国际"), "不限（全球为主）"),
]


def _match(text: str, rules) -> str:
    low = text.lower()
    for keywords, value in rules:
        for k in keywords:
            if k.lower() in low:
                return value
    return ""


def guess(query: str) -> dict:
    """关键词规则推断；只返回有把握的字段，推断不出的不返回。"""
    out = {}
    ind = _match(query, INDUSTRY_RULES)
    if ind:
        out["industry"] = ind
    pur = _match(query, PURPOSE_RULES)
    if pur:
        out["purpose"] = pur
    mkt = _match(query, MARKET_RULES)
    if mkt:
        out["market"] = mkt
    tr = ""
    for k, v in TIME_ALIASES.items():
        if k in query:
            tr = v
            break
    if tr:
        out["time_range"] = tr
    return out


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


AUTO_PROMPT = """从用户这句话里判断调研范围，输出严格 JSON（只输出 JSON，不要解释）。

字段与可选值：
- market: 不限（全球为主）/ 中国大陆 / 中国 + 全球对照 / 北美 / 欧洲 / 东南亚 / 日韩 / 中东
- industry: 不限 / 消费品/快消 / 科技/软件/SaaS / 新能源/汽车 / 医疗健康 / 工业制造 / 金融/支付 / 教育 / 文娱/内容 / 跨境电商/零售
- purpose: 竞品分析 / 市场进入 / 新品立项 / 投资尽调 / 定价策略 / 渠道策略 / 行业概览
- time_range: 近一年 / 近三年 / 近五年 / 近十年 / 不限
- depth: "2" / "3" / "4"（信息密集的主题用 3 或 4）

判断不了就填 "不限"，不要编。"""


def infer(query: str, llm) -> dict:
    """让模型推断；失败返回空 dict。"""
    try:
        raw = llm.chat(AUTO_PROMPT, "用户需求：" + query, temperature=0.0, max_tokens=300)
        data = _extract_json(raw)
    except Exception:
        return {}
    out = {}
    for field, options, aliases in (("market", MARKET_OPTIONS, MARKET_ALIASES),
                                    ("industry", INDUSTRY_OPTIONS, INDUSTRY_ALIASES),
                                    ("purpose", PURPOSE_OPTIONS, PURPOSE_ALIASES),
                                    ("time_range", TIME_OPTIONS, TIME_ALIASES)):
        v = data.get(field)
        if not v:
            continue
        try:
            out[field] = normalize(str(v), options, aliases, field)
        except ValueError:
            continue
    if str(data.get("depth")) in ("2", "3", "4"):
        out["depth"] = str(data["depth"])
    return out
