# 排错手册

按「症状 → 原因 → 处理」查。

## route B（standalone）

| 症状 | 原因 | 处理 |
|---|---|---|
| `缺少模型 Key` | 没设 `MRA_API_KEY` | 设环境变量；本地网关可任意填 |
| `HTTP 401` (模型) | Key 错/过期 | 换 Key；注意别把 `Bearer` 写进 Key |
| `HTTP 429` | 免费额度用尽 | 换后端/换模型，或降到 `--depth 2` |
| `Tavily 返回 429` | 1000 credits/月用尽 | 等月度重置，或 `--search fixture` 先验流程 |
| `Tavily 网络错误` | 代理/防火墙 | 设 `HTTPS_PROXY`；确认能通 `api.tavily.com:443` |
| 返回码 `3`，只输出一句追问 | 问题太含糊，流程按设计追问 | 补清「行业/品类 + 目标市场」再跑 |
| 报告里大量「材料未覆盖」 | 检索没命中 | 换 `--source`、加 `--market`、调高 `--depth` |
| 正文有 `[7]` 但来源表没有 | 模型编了编号（少见） | 提高模型能力；或把 `temperature` 降到 0.5 |
| Windows 控制台中文乱码 | 代码页不是 UTF-8 | `$env:PYTHONUTF8=1`；或 `chcp 65001` |

## route A（Dify + Docker）

| 症状 | 原因 | 处理 |
|---|---|---|
| 网站打不开 | Docker 没跑 / 容器没起 | `python scripts\start_dify.py`；或 `docker compose up -d` |
| 重启后就打不开 | Docker Desktop 不信守自启 | 设置里勾「登录时启动」+ 装 `start_dify.py --install-autostart` |
| `Default model not found` | 模型供应商没配 / 网关掉了 | 设置里重配；本机网关确认端口在听 |
| 工作流跑到一半卡住 | Celery worker 挂了 | `docker compose ps` 看 worker；`docker compose restart worker` |
| 检索节点 500 | Tavily Key 没填/失效 | 应用「环境变量」里重填 `TAVILY_API_KEY`，重新发布 |
| 知识库召回全空 | 文档没索引完 / embedding 模型没配 | 知识库页面看索引状态；确认 embedding 供应商可用 |
| 导入 DSL 报 schema 错 | Dify 版本低于 DSL 版本 | 升级到 1.9+，或换低版本 DSL |
| 容器内存爆 | 11 个容器 ≥ 8 GB | 关掉不用的（weaviate/certbot），或换 Dify Cloud |
| 蓝屏 `0x124` 后全部失联 | 硬件/驱动层崩溃 | 开机自启 + `start_dify.py` 兜底；长期方案是换 route B |

## 诊断命令

```powershell
# 容器状态
docker compose ps
docker compose logs --tail 100 api
docker compose logs --tail 100 worker

# 端口
Get-NetTCPConnection -LocalPort 8080 -State Listen
Get-NetTCPConnection -LocalPort PORT -State Listen   # 本机模型网关端口

# 模型连通性（任何 OpenAI 兼容端点）
curl http://127.0.0.1:PORT/v1/models
```

```bash
# standalone 自检
python -m mra --search fixture --fixture tests/fixtures/corpus.json "测试" --depth 2 -q
python tests/test_nodes.py && python tests/test_search.py
```

## 一条经验

**「网站打不开」九成不是网站的问题，是容器没起来。** 先跑体检命令再怀疑代码。
