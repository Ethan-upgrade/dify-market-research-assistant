# 部署 Dify（route A）

## A. Dify Cloud（最省事）

1. 打开 https://cloud.dify.ai ，注册。
2. 设置 → 模型供应商 → 添加「OpenAI-API-compatible」，填 base_url / key / 模型名。
3. 工作室 → 创建空白应用 → 右上「导入 DSL」→ 选 `dsl/market-research-assistant-v3.yml`。
4. 应用内「环境变量」→ `TAVILY_API_KEY` 填你的 Tavily Key。
5. 发布 → 打开 Web App。

## B. 本机 Docker Compose

### 前置

- Docker Desktop（Windows 需开 WSL2）
- 内存 ≥ 8 GB 空闲（11 个容器：api / worker / web / db / redis / sandbox / ssrf_proxy / plugin_daemon / weaviate / nginx / certbot）

### 步骤

```powershell
git clone https://github.com/langgenius/dify.git
cd dify/docker
copy .env.example .env
docker compose up -d
docker compose ps          # 等到全部 healthy
```

访问 http://127.0.0.1:8080 ，先注册管理员（第一个注册的人即管理员）。

### 一定要做的三件稳定化

1. **给容器组设重启策略**：`docker update --restart unless-stopped $(docker ps -q)`
2. **Docker Desktop 开机自启**：设置 → General → 勾选 *Start Docker Desktop when you sign in*。
3. **加一个自愈脚本**（本仓库 `scripts/start_dify.py`）：

```powershell
python scripts\start_dify.py                # 起 Docker → 起容器 → 等 8080 通
python scripts\start_dify.py --check        # 只体检
python scripts\start_dify.py --install-autostart   # 写进启动文件夹
```

### 首次初始化

```powershell
# 1) 建管理员 + 登录，拿 token
python scripts\deploy_v3.py --base http://127.0.0.1:8080 --file dsl\market-research-assistant-v3.yml --publish

# 2) 冒烟验证（约 20 秒，验链路不验质量）
python scripts\verify_published.py --base http://127.0.0.1:8080 --mode smoke
```

凭据全部从环境变量读：`DIFY_EMAIL` / `DIFY_PASSWORD` / `DIFY_TAVILY_KEY`。

## C. 模型怎么接

Dify 支持任意 OpenAI 兼容端点。本机网关、Ollama、云厂商都行：

| 场景 | base_url | 备注 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | 性价比首选 |
| OpenAI | `https://api.openai.com/v1` | — |
| 本机 Ollama | `http://host.docker.internal:11434/v1` | 容器里访问宿主机要用 host.docker.internal |
| 公司网关 | `http://host.docker.internal:PORT/v1` | 网关掉了应用会报 `Default model not found` |

> 注意：容器内的 `127.0.0.1` 指向容器自己，访问宿主机服务必须用 `host.docker.internal`。
