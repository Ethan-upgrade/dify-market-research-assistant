"""命令行入口。

    python -m mra "调研 Nespresso 胶囊咖啡在中国市场的竞争格局" --market 中国大陆
    python -m mra -f query.txt --depth 3 --out report.md
    python -m mra --search fixture --fixture tests/fixtures/corpus.json "胶囊咖啡"
"""

from __future__ import annotations

import argparse
import io
import os
import sys

from . import __version__
from .config import RuntimeConfig, Scope, MARKET_OPTIONS, INDUSTRY_OPTIONS, PURPOSE_OPTIONS, TIME_OPTIONS, SOURCE_OPTIONS, DEPTH_OPTIONS
from .llm import LLM, LLMError
from .pipeline import Pipeline
from .search import SearchError, build_backend


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mra", description="市场调研报告助手（Dify 工作流的零依赖独立实现）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("query", nargs="?", help="调研需求，一句话；用 -f 从文件读")
    p.add_argument("-f", "--file", help="从文本文件读取调研需求")
    p.add_argument("--market", default="不限（全球为主）", choices=MARKET_OPTIONS, help="调研范围（地区）")
    p.add_argument("--industry", default="不限", choices=INDUSTRY_OPTIONS, help="行业类型")
    p.add_argument("--purpose", default="竞品分析", choices=PURPOSE_OPTIONS, help="调研目的")
    p.add_argument("--time", dest="time_range", default="近三年", choices=TIME_OPTIONS, help="时间范围")
    p.add_argument("--source", dest="source_pref", default="不限", choices=SOURCE_OPTIONS, help="数据源偏好")
    p.add_argument("--depth", default="3", choices=DEPTH_OPTIONS, help="检索深度（轮数）")

    p.add_argument("--search", dest="search_backend", default=None, choices=["tavily", "fixture"], help="检索后端")
    p.add_argument("--fixture", default=None, help="fixture 语料路径")
    p.add_argument("--model", default=None, help="模型名，覆盖 MRA_MODEL")
    p.add_argument("--base-url", default=None, help="OpenAI 兼容 base_url，覆盖 MRA_BASE_URL")
    p.add_argument("-o", "--out", default=None, help="报告输出路径（默认打印到 stdout）")
    p.add_argument("--json", action="store_true", help="额外输出一行 JSON 元数据到 stderr")
    p.add_argument("--no-normalize", dest="no_normalize", action="store_true",
                   help="跳过引用降噪（默认会再调一次模型合并重复标注）")
    p.add_argument("--no-check", dest="no_check", action="store_true",
                   help="跳过报告自检（悬空引用/来源利用率/章节数/篇幅）")
    p.add_argument("--min-chars", dest="min_chars", type=int, default=3000, help="自检：报告最少字数")
    p.add_argument("--min-cited-ratio", dest="min_cited_ratio", type=float, default=0.6,
                   help="自检：来源被引用率下限（默认 0.6）")
    p.add_argument("--max-density", dest="max_density", type=float, default=6.0,
                   help="自检：每百字引用标注数上限（默认 6）")
    p.add_argument("-q", "--quiet", action="store_true", help="不打印过程日志")
    p.add_argument("-V", "--version", action="version", version="mra " + __version__)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    query = args.query or ""
    if args.file:
        with io.open(args.file, encoding="utf-8") as f:
            query = f.read().strip()
    if not query:
        print("缺少调研需求：给一个位置参数，或用 -f 指定文件", file=sys.stderr)
        return 2

    cfg = RuntimeConfig.from_env()
    if args.model:
        cfg.model = args.model
    if args.base_url:
        cfg.base_url = args.base_url
    if args.search_backend:
        cfg.search_backend = args.search_backend
    if args.fixture:
        cfg.fixture_path = args.fixture

    if not cfg.api_key and "127.0.0.1" not in cfg.base_url and "localhost" not in cfg.base_url:
        print("缺少模型 Key：请设置 MRA_API_KEY（或 OPENAI_API_KEY / DEEPSEEK_API_KEY）", file=sys.stderr)
        return 2

    scope = Scope(market=args.market, industry=args.industry, purpose=args.purpose,
                  time_range=args.time_range, source_pref=args.source_pref, depth=args.depth)

    llm = LLM(cfg.base_url, cfg.api_key, cfg.model, cfg.temperature, cfg.max_tokens, cfg.timeout,
              verbose=not args.quiet)
    try:
        backend = build_backend(cfg)
    except SearchError as e:
        print("检索后端初始化失败：" + str(e), file=sys.stderr)
        return 2

    pipe = Pipeline(llm, backend, scope, verbose=not args.quiet,
                    normalize_citations=not getattr(args, "no_normalize", False))
    try:
        report = pipe.run(query)
    except (LLMError, SearchError) as e:
        print("运行失败：" + str(e), file=sys.stderr)
        return 1

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(report.markdown)
        if not args.quiet:
            print(f"\n已写入 {args.out}（{len(report.markdown)} 字）", file=sys.stderr)
    else:
        print(report.markdown)

    # 出完报告自检：默认开，--no-check 关。不合格不删报告，只报警并把退出码改成 1。
    check = None
    if not report.unclear and not getattr(args, "no_check", False):
        from .checks import check_report
        check = check_report(
            report.markdown,
            min_chars=getattr(args, "min_chars", 3000),
            min_cited_ratio=getattr(args, "min_cited_ratio", 0.6),
            max_marks_per_100=getattr(args, "max_density", 6.0),
        )
        if not check["ok"]:
            print("\n⚠ 报告体检未通过：", file=sys.stderr)
            for p in check["problems"]:
                print("   - " + p, file=sys.stderr)
            print("   （报告已保留，请人工复核；--no-check 可关闭自检）", file=sys.stderr)
        elif not args.quiet:
            m = check["metrics"]
            print(f"\n✓ 体检通过：{m['chars']} 字 / {m['chapters']} 章 / "
                  f"来源 {m['web']} 条（引用 {m['cited']}，{m['ratio']:.0%}）"
                  f" / 标注 {m['marks']} 处（每百字 {m['density']}）"
                  + (f" / 知识库 {m['kb']} 条" if m["kb"] else ""), file=sys.stderr)

    if args.json:
        import json
        meta = {
            "query": report.query, "scope": report.scope.as_dict(),
            "rounds": report.rounds_used, "sources": report.n_sources,
            "cited": report.n_cited, "unclear": report.unclear,
            "chars": len(report.markdown), **report.meta,
        }
        if check is not None:
            meta["check"] = check
        print(json.dumps(meta, ensure_ascii=False), file=sys.stderr)

    if report.unclear:
        return 3
    if check is not None and not check["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
