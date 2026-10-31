# 不装 Docker 怎么跑

两条路：**B1 源码装 Dify**（要网页界面），**B2 standalone CLI**（只要报告，推荐）。

---

## B2. standalone：零依赖，最稳

### 要求

- Python 3.9+（Windows / macOS / Linux 都行）
- 一个 OpenAI 兼容的模型接口
- 可选：Tavily Key（不填就只能用离线语料）

### 安装

不需要 `pip install` 任何东西。

```bash
cd standalone
cp ../.env.example ../.env    # 或用环境变量
python -m mra --help
```

### 当命令用

```bash
# Linux/macOS
cat > ~/.local/bin/mra <<'EOF'
#!/usr/bin/env bash
export MRA_BASE_URL="https://api.deepseek.com/v1"
export MRA_API_KEY="sk-..."
export MRA_MODEL="deepseek-chat"
export TAVILY_API_KEY="tvly-..."
exec python3 -m mra "$@"
EOF
chmod +x ~/.local/bin/mra
```

```powershell
# Windows：复制 standalone/run.ps1 到 PATH 里，或直接调用
.\standalone\run.ps1 "调研 XX 市场" --market 中国大陆
```

### 当库用

```python
from mra.config import Scope, RuntimeConfig
from mra.llm import LLM
from mra.search import build_backend
from mra.pipeline import Pipeline

cfg = RuntimeConfig.from_env()
llm = LLM(cfg.base_url, cfg.api_key, cfg.model)
pipe = Pipeline(llm, build_backend(cfg), Scope(market="中国大陆", depth="3"), verbose=False)
report = pipe.run("调研胶囊咖啡在中国市场的竞争格局")
print(report.markdown)
print(report.n_sources, report.n_cited)
```

### 接到自己的系统里

`Report` 对象带 `markdown / rounds_used / n_sources / n_cited / meta`，直接塞进飞书文档、Notion、邮件、数据库都行。

### 离线验证（不花钱、不联网）

```bash
python -m mra --search fixture --fixture tests/fixtures/corpus.json "胶囊咖啡 竞争格局" --depth 2
```

---

## B1. 源码安装 Dify（不用 Docker）

Dify 就是 FastAPI + Next.js。要自己起这些中间件：

| 组件 | 版本 | 作用 |
|---|---|---|
| PostgreSQL | 15 + `pgvector` 扩展 | 主库 + 向量检索 |
| Redis | 6+ | 缓存 / Celery broker |
| Weaviate / Qdrant | 任一 | 向量库（也可直接用 pgvector） |
| Python | 3.12 | `api/` |
| `uv` | 0.8+ | 依赖管理 |
| Node.js | 22 LTS | `web/` |
| `pnpm` | 10+ | 前端包管理 |
| dify-plugin-daemon | 最新 | 插件运行时（不给就装不了模型供应商） |

### 步骤（Linux / WSL 上最顺）

```bash
# 1) 中间件（用本机已有服务，或先只起这三个）
#    postgres 需要：CREATE EXTENSION vector;

# 2) api
cd api
cp .env.example .env        # 填 DB_*/REDIS_*/SECRET_KEY/CELERY_BROKER_URL
uv sync
uv run flask db upgrade
uv run flask fab create-admin
uv run gunicorn -k gevent -w 2 -b 0.0.0.0:5001 --timeout 3600 -c gunicorn.conf.py app:app

# 3) worker（另开终端，必须有，否则工作流异步节点跑不动）
cd api
uv run celery -A app.celery worker -P gevent -c 1 --loglevel INFO -Q dataset,generation,mail,ops_trace,app_deletion,plugin,workflow

# 4) plugin daemon（另开终端）
git clone https://github.com/langgenius/dify-plugin-daemon.git
cd dify-plugin-daemon && go build -o main . && ./main

# 5) web
cd web
cp .env.example .env.local  # NEXT_PUBLIC_API_PREFIX=http://127.0.0.1:5001
pnpm install && pnpm build && pnpm start
```

### Windows 上为什么要三思

- `pgvector` 在 Windows 原生安装要自己编译，通常走 WSL；
- Celery 的 `gevent` pool 在 Windows 上不友好（官方也不建议）；
- plugin-daemon 需要 Go 工具链；
- 三个进程 + 三个中间件，任一个挂了都表现为「页面转圈」。

**所以 Windows 上要么 Docker，要么直接 route B（standalone）。**

### 对比

| | 源码装 Dify | standalone |
|---|---|---|
| 依赖 | PostgreSQL/Redis/向量库/Node/Go | 无 |
| 起始时间 | 1~2 天 | 1 分钟 |
| 可视化编排 | ✅ | ❌ |
| 多租户/权限 | ✅ | ❌ |
| 崩溃面 | 6 个进程 | 1 个进程 |
