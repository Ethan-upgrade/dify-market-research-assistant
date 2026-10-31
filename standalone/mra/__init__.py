"""mra —— 从 Dify 工作流里抽出来的市场调研报告生成器（零依赖）。

与 DSL 里的 Chatflow 一一对应：

    ① 调研需求解析   -> pipeline.plan()
    ② 信息是否充分   -> nodes.clean_brief() / clarify 分支
    ③ 递归检索       -> pipeline.research_loop()
    ⑫ 撰写报告       -> pipeline.write_report()
    ⑫ᵇ 生成来源表    -> nodes.build_cited_table()

不依赖 Docker、不依赖 Dify、不依赖第三方库，只需要 Python 3.9+ 和一个
OpenAI 兼容的模型接口（外加可选的 Tavily Key）。
"""

__version__ = "3.0.1"
