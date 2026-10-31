# 快速开始

## 先选路线

```
你要「一个网页，团队点开就能用」？
├─ 是 → 有公网/能接受云服务？
│        ├─ 是 → Dify Cloud（docs/02 里的 A 段），导入 dsl/v3
│        └─ 否 → 本机 Docker Compose（docs/02 的 B 段）
└─ 否 → 只要能稳定出报告 → standalone CLI（docs/03），零 Docker
```

## route B：三分钟出第一份报告

**方式一（推荐）：填一次 `.env`，之后不用再 export**

```powershell
cd dify-market-research-assistant
copy .env.example .env      # 用记事本填 MRA_API_KEY 与 TAVILY_API_KEY
cd standalone
python -m mra "调研 Nespresso 胶囊咖啡在中国市场的竞争格局" --market 中国大陆 -o nespresso.md
```

`.env` 会在启动时自动加载；同名的 shell 环境变量优先。

**方式二：直接设环境变量（临时生效）**

```powershell
cd standalone
$env:MRA_BASE_URL = "https://api.deepseek.com/v1"
$env:MRA_API_KEY  = "sk-..."
$env:MRA_MODEL    = "deepseek-chat"
$env:TAVILY_API_KEY = "tvly-..."

python -m mra "调研 Nespresso 胶囊咖啡在中国市场的竞争格局" `
    --market 中国大陆 --purpose 竞品分析 --depth 3 -o nespresso.md
```

跑完会打印每步耗时，最后一行是报告字数。`--out` 不写就打到 stdout。

## 六个参数怎么选

| 参数 | 常用值 | 影响 |
|---|---|---|
| `--market` | `中国大陆` / `北美` / `不限（全球为主）` | 检索式里的地区词 + 报告地理口径 |
| `--industry` | `消费品/快消` / `科技/软件/SaaS` … | 优先参考的数据源类型 |
| `--purpose` | `竞品分析` / `市场进入` / `投资尽调` … | 第七章行动建议的落点 |
| `--time` | `近一年` / `近三年` / `近五年` | 检索式里的年份词 |
| `--source` | `优先券商研报/咨询报告` … | Tavily 关键词 + 可信度排序提醒 |
| `--depth` | `2` / `3` / `4` | 循环轮数；每轮 2 次检索，约 +4 秒 +10 credits |

## 常见返回码

| 码 | 含义 |
|---|---|
| `0` | 正常出报告 |
| `2` | 参数/配置问题（缺 Key、fixture 路径不存在） |
| `1` | 运行期失败（模型 5xx、检索 401/429） |
| `3` | 未出报告，而是**追问**（问题写得太含糊，或缺材料） |

`3` 不是错误：说明流程正在按设计追问澄清，把问题写清楚再跑一次即可。
