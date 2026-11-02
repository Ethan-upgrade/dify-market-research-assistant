"""配置与调研范围（对应 Dify 开始节点上的 6 个下拉框）。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path


def _env_candidates() -> list:
    """.env 的查找位置：当前目录 → 上级 1~3 层（兼容从仓库根或 standalone/ 下运行）。"""
    cands = [Path.cwd() / ".env"]
    here = Path(__file__).resolve()
    for up in (2, 3, 4):
        try:
            cands.append(here.parents[up] / ".env")
        except IndexError:
            pass
    return cands


def load_env_file() -> str:
    """极简 .env 加载器（不依赖 python-dotenv）。已存在的环境变量优先，不覆盖。

    返回实际加载的文件路径，没找到返回空串。
    """
    seen = set()
    for p in _env_candidates():
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            if k and k not in os.environ:
                os.environ[k] = v
        return str(p)
    return ""


# ---------------------------------------------------------------- 范围选项
# 与 DSL 里 start 节点的 options 完全一致，改这里要同步改 DSL，反之亦然。
MARKET_OPTIONS = [
    "不限（全球为主）", "中国大陆", "中国 + 全球对照", "北美",
    "欧洲", "东南亚", "日韩", "中东",
]

INDUSTRY_OPTIONS = [
    "不限", "消费品/快消", "科技/软件/SaaS", "新能源/汽车", "医疗健康",
    "工业制造", "金融/支付", "教育", "文娱/内容", "跨境电商/零售",
]

PURPOSE_OPTIONS = [
    "竞品分析", "市场进入", "新品立项", "投资尽调",
    "定价策略", "渠道策略", "行业概览",
]

TIME_OPTIONS = ["近一年", "近三年", "近五年", "近十年", "不限"]

SOURCE_OPTIONS = [
    "不限", "优先券商研报/咨询报告", "优先官方统计/政府数据",
    "优先上市公司财报", "优先新闻报道", "优先电商/社媒数据",
]

DEPTH_OPTIONS = ["2", "3", "4"]

# 数据源偏好 -> (压进检索式的关键词, 报告里的口径提醒)
SOURCE_HINT = {
    "优先券商研报/咨询报告": ("券商研报 行业报告", "优先采用券商研报 / 咨询机构口径，自媒体数据只能作旁证"),
    "优先官方统计/政府数据": ("统计局 海关 官方数据", "优先采用官方统计与政策文件，商业机构口径需标注差异"),
    "优先上市公司财报": ("财报 年报 分部收入", "优先采用上市公司财报与分部披露，估算值必须标注"),
    "优先新闻报道": ("新闻报道 最新动态", "优先采用主流媒体近一年报道，注意去重与转载"),
    "优先电商/社媒数据": ("电商 销量 评论 社媒", "优先采用电商销量与社媒口碑数据，注意平台口径差异"),
}


@dataclass
class Scope:
    """调研范围。全部有默认值，命令行不传也能跑。"""

    market: str = "不限（全球为主）"
    industry: str = "不限"
    purpose: str = "竞品分析"
    time_range: str = "近三年"
    source_pref: str = "不限"
    depth: str = "3"

    def __post_init__(self):
        # 宽容归一：能映射就映射；映射不了就原样保留成「自定义口径」，绝不报错退出
        from .aliases import (MARKET_ALIASES, INDUSTRY_ALIASES, PURPOSE_ALIASES,
                              TIME_ALIASES, SOURCE_ALIASES, normalize)
        self.custom_fields = []
        pairs = (
            ("market", MARKET_OPTIONS, MARKET_ALIASES, "地区"),
            ("industry", INDUSTRY_OPTIONS, INDUSTRY_ALIASES, "行业"),
            ("purpose", PURPOSE_OPTIONS, PURPOSE_ALIASES, "目的"),
            ("time_range", TIME_OPTIONS, TIME_ALIASES, "时间范围"),
            ("source_pref", SOURCE_OPTIONS, SOURCE_ALIASES, "数据源偏好"),
        )
        for field, options, aliases, label in pairs:
            raw = getattr(self, field)
            try:
                setattr(self, field, normalize(raw, options, aliases, label))
            except ValueError:
                setattr(self, field, (raw or "").strip())
                self.custom_fields.append(field)

    def rounds(self) -> int:
        try:
            n = int(str(self.depth).strip())
        except (TypeError, ValueError):
            n = 3
        return min(4, max(2, n))

    # -------------------------------------------------- 渲染成 prompt 片段
    def search_scope(self) -> str:
        geo = "" if self.market.startswith("不限") else self.market
        src_kw, _ = SOURCE_HINT.get(self.source_pref, ("", ""))
        lines = [
            "【检索口径】",
            "- 地区：" + ("不限，全球视角为主" if not geo else geo),
            "- 行业类型：" + self.industry,
            "- 时间范围：" + ("不限" if self.time_range == "不限" else self.time_range + "内发布的数据优先"),
            "- 调研目的：" + self.purpose + "（检索要覆盖支撑该目的的指标）",
        ]
        if src_kw:
            lines.append("- 数据源偏好：" + self.source_pref + "（检索式里可带「" + src_kw + "」这类词）")
        return "\n".join(lines)

    def report_scope(self) -> str:
        geo = "" if self.market.startswith("不限") else self.market
        _, src_rule = SOURCE_HINT.get(self.source_pref, ("", ""))
        lines = [
            "【报告口径】",
            "- 地区范围：" + ("全球为主，中国作为重点对照" if not geo else geo),
            "- 行业类型：" + self.industry,
            "- 时间口径：" + ("不限年份，按数据可得性" if self.time_range == "不限"
                            else self.time_range + "为宜，更早的数据只在做趋势对比时引用"),
            "- 报告用途：" + self.purpose + "——结论与行动建议必须落到该用途上",
        ]
        if src_rule:
            lines.append("- 数据源：" + src_rule)
        return "\n".join(lines)

    @property
    def geo(self) -> str:
        return "全球" if self.market.startswith("不限") else self.market

    def summary(self) -> str:
        return (f"地区={self.market}｜行业={self.industry}｜目的={self.purpose}"
                f"｜时间={self.time_range}｜来源={self.source_pref}｜轮数={self.rounds()}")

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- 运行环境
@dataclass
class RuntimeConfig:
    """模型与检索服务的接入信息，全部来自环境变量。"""

    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 16384
    timeout: int = 180

    tavily_key: str = ""
    search_backend: str = "tavily"        # tavily | fixture
    fixture_path: str = ""
    max_results: int = 6
    search_depth: str = "advanced"

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        load_env_file()

        def g(*names, default=""):
            for n in names:
                v = os.environ.get(n, "").strip()
                if v:
                    return v
            return default

        return cls(
            base_url=g("MRA_BASE_URL", "OPENAI_BASE_URL", default="https://api.deepseek.com/v1"),
            api_key=g("MRA_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"),
            model=g("MRA_MODEL", "OPENAI_MODEL", default="deepseek-chat"),
            temperature=float(g("MRA_TEMPERATURE", default="0.7")),
            max_tokens=int(g("MRA_MAX_TOKENS", default="16384")),
            timeout=int(g("MRA_TIMEOUT", default="180")),
            tavily_key=g("TAVILY_API_KEY", "MRA_TAVILY_KEY"),
            search_backend=g("MRA_SEARCH_BACKEND", default="tavily").lower(),
            fixture_path=g("MRA_FIXTURE", default=""),
            max_results=int(g("MRA_MAX_RESULTS", default="6")),
            search_depth=g("MRA_SEARCH_DEPTH", default="advanced"),
        )
