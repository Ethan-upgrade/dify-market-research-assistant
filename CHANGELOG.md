# CHANGELOG

## 3.0.2

- **修**：`.env` 之前只是文档承诺，代码并不读取。现在 `config.load_env_file()` 会自动加载（当前目录 → 上级 3 层），shell 环境变量优先，不依赖 python-dotenv。
- 新增 `tests/test_config.py`：5 个用例（读取、优先级、引号剥离、缺文件、值内 `#`）。总计 44 个用例。
- CI 增加 `.env` 相关测试。
- 仓库根提供一个已配置本机网关的 `.env`（gitignore，不入库）。

## 3.0.1

- 新增 `standalone/tests/test_pipeline.py`：8 个编排层用例（正常成稿 / 追问分支 / 跑题拦截 / 轮数上限 / 引用裁剪 / 引擎摘要编号）。总计 39 个用例。
- 修 `scripts/deploy_dsl.py`：Dify 导入会沿用 DSL 里的应用名，`--name` 现在会显式改名生效。
- 启用 GitHub Actions（`ci.yml`）：三档 Python 单测 + DSL 结构校验 + 语法检查。
- 文档补充：ssh 推送绕过 OAuth `workflow` scope 限制的做法。

## 3.0.0

**新增 standalone 实现（route B）** —— 不依赖 Docker 的等价实现。

- `standalone/mra/`：节点逻辑、prompt、检索后端、编排、CLI 全部抽出，零第三方依赖。
- `standalone/tests/`：31 个用例，覆盖节点纯函数、Tavily 请求体逐字段契约、离线回放、引用表生成。
- 离线 fixture 后端：没有 Tavily Key 也能端到端跑通。

**文档重组**：README 增加「Dify 只能在 Docker 里跑吗」的四路对比，新增部署/架构/范围/排错等 7 篇文档。

**脚本去敏感化**：`scripts/` 下所有凭据改为环境变量读取，路径改为可配置。

## 2.x

- 接入内部知识库（RAG），召回片段编号 `[K1]`，带相关性门控。
- 引用体系改为全局编号 `[n]`，正文与来源表一一对应。
- 增加跑题拦截：零来源时反问，不再凭空生成报告。
- 开始节点新增 6 个调研范围维度。

## 1.0.0

- 首个可用版本：Dify Chatflow，固定两轮检索，七章报告结构。
