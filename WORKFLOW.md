# 完整工作流（从一句话到可核验报告）

这份文档把「市场调研报告助手」端到端串一遍：你只需要给一句话，剩下的按下面的链路自动走。

```
一句话需求
   │
   ▼
① 范围识别 ── 显式参数 / --smart 关键词 / --auto-scope 模型推断
   │
   ▼
② 需求解析 ── 判断信息是否充分 → 不充分则追问（最多 2 次）
   │
   ▼
③ 递归检索 ── 每轮 2 条检索式，按缺口重规划，2~4 轮
   │          （Tavily，两路并发）
   ▼
④ 去重编号 ── URL → 全局 [n]，跨轮累积；引擎摘要单独编号
   │
   ▼
⑤ 撰写报告 ── 七章结构，每个数字带 [n]
   │
   ▼
⑥ 引用整理 ── 确定性 tidy：连写合并、表格单元格去重、编号连续 1..N
   │
   ▼
⑦ 报告体检 ── 悬空引用 / 自造标注 / 利用率 / 密度 / 章节 / 篇幅
   │
   ▼
⑧ 来源核验 ── 链接体检（四层抓取）+ 数字溯源（表格级）
   │
   ▼
⑨ 交付 ── Markdown 文件 / stdout / HTTP 接口 / 定时任务
```

## 每一步的命令与产物

| 步骤 | 命令 | 产物 |
|---|---|---|
| 全流程 | `python -m mra "调研 XX" --smart -o r.md` | Markdown 报告 + 体检结论 |
| 只要体检 | `python -m mra.verify r.md` | 链接三档：OK / BOT / DEAD |
| 数字溯源 | `python -m mra.trace r.md` | 表格行：可核验 / 待复核 / 无法访问 |
| 起服务 | `python -m mra.serve --port 8765` | `/check` `/verify` `/research` |
| 定时跑 | `tools\install-task.ps1 -Time 09:00 -Weekly Monday` | 每周自动出报告 |

## 三种使用姿势

**A. 随手跑一份（最常用）**

```powershell
cd standalone
python -m mra "德语学习周期、学习方法与未来应用前景，尤其以职业为导向" --smart --depth 3 -o report.md
```

**B. 批量/定时**

```powershell
# topics.txt 一行一个主题
tools\batch-run.cmd
tools\install-task.ps1 -Time 09:00 -Weekly Monday -File topics.txt -Depth 2
```

**C. 给别人/别的系统用**

```powershell
python -m mra.serve --port 8765
# POST /research → job_id；GET /jobs/<id> 轮询
```

## 质量闸门（不过会怎样）

| 闸门 | 不过时的行为 |
|---|---|
| 信息不足 | 返回一句追问，退出码 3，不出报告 |
| 材料与主题无关 | 报告改为「无法形成可信报告」，退出码 3 |
| 引用缺失/悬空/密度超标 | 列出问题，退出码 1，**报告保留**供人工复核 |
| 链接死链 | 列出具体 URL，退出码 1 |
| 数字溯源有缺失 | 只提示，不阻断（可能是改口径/四舍五入） |

## 成本与耗时（实测）

| 配置 | 耗时 | tokens | Tavily |
|---|---|---|---|
| `--depth 2` | 2~3 分钟 | ~50k | 8 credits |
| `--depth 3` | 4~6 分钟 | ~76k | 12 credits |
| `--depth 4` | 6~8 分钟 | ~100k | 16 credits |
| `--smart` 识别 | +0 秒 | 0 | 0 |
| `--auto-scope` | +2 秒 | ~1~2k | 0 |
| `/check` `/verify` | 秒级 | 0 | 0 |

## 文件地图

```
dsl/            Dify 工作流（v1/v2/v3），导入即用
standalone/
  mra/
    config.py     范围与配置（宽容归一）
    autoscope.py  智能识别范围（关键词 / 模型）
    prompts.py    三份核心 prompt + 压缩 prompt
    nodes.py      DSL Code 节点的纯函数实现
    pipeline.py   编排：解析 → 检索 → 写 → 整理 → 体检
    checks.py     报告体检规则
    tidy.py       确定性引用整理（连写/表格/编号）
    verify.py     链接体检
    trace.py      数字溯源（表格级）
    fetch.py      四层抓取引擎 + PDF + 缓存
    serve.py      HTTP 服务（同步 + 异步任务）
  tests/          153 个用例
tools/          双击跑 / 批量 / 定时 / 常驻服务 / 桌面快捷方式
scripts/        Dify 导入发布与发布版验证
docs/           部署、架构、范围口径、排错、触发方式
```

## 一句话总结

**能用（Dify 网页或 CLI）→ 写得准（引用编号）→ 写得可读（不刷标）→ 来源能打开（链接体检）→ 数字查得到（溯源）→ 跑得快（并行+缓存）→ 能给别人用（HTTP 服务）。**
