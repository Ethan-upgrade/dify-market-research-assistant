# 日常怎么触发

五条路，按「手速」排序。前 3 条都不用打开 Dify。

---

## 1. 命令行（最常用，适合知道自己要什么）

```powershell
cd D:\dsh-workplace\dify-market-research-assistant\standalone
python -m mra "调研 XX 市场" --market 中国大陆 --purpose 竞品分析 --depth 3 -o report.md
```

嫌切目录麻烦，二选一：

```powershell
# a) 加一个 mra 命令（把 tools 目录塞进 PATH，只需一次）
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";D:\dsh-workplace\dify-market-research-assistant\tools", "User")
# 重开终端后，任意目录：
mra "调研 XX 市场" --depth 2

# b) 直接用 cmd 包装器
D:\dsh-workplace\dify-market-research-assistant\tools\mra.cmd "调研 XX 市场" --depth 2
```

常用参数只有四个：`--market`（地区）、`--purpose`（用途）、`--depth`（2 便宜 / 3 标准 / 4 深挖）、`-o`（输出文件）。

---

## 2. 双击出报告（不想敲命令）

```
tools\run-report.cmd
```

双击后会依次问：主题 → 地区 → 目的 → 深度，然后自动跑、自动把报告用默认编辑器打开，落在 `reports\`。

也可以给它带参，跳过提问：

```powershell
tools\run-report.cmd -Topic "调研胶囊咖啡在中国市场的竞争格局" -Market 中国大陆 -Depth 2
```

**放到桌面**（一次操作，以后双击）：

```powershell
$s = (New-Object -ComObject WScript.Shell).CreateShortcut("$env:USERPROFILE\Desktop\跑一份调研.lnk")
$s.TargetPath = "D:\dsh-workplace\dify-market-research-assistant\tools\run-report.cmd"
$s.WorkingDirectory = "D:\dsh-workplace\dify-market-research-assistant"
$s.IconLocation = "powershell.exe,0"
$s.Save()
```

---

## 3. 批量（一次跑一串主题）

编辑仓库根的 `topics.txt`，一行一个主题（`#` 开头是注释），然后：

```
tools\batch-run.cmd
```

或指定别的清单 / 换参数：

```powershell
tools\batch.ps1 -File my-topics.txt -Depth 2 -Market 北美 -Purpose 市场进入
```

行为：按顺序跑，每份报告命名 `reports\2026-11-01-0930-01-主题.md`，日志追加到 `reports\run-log.txt`；
某个主题失败默认停下（加 `-ContinueOnError` 继续）。

---

## 4. 定时自动跑（每周一早上自己出报告）

```powershell
# 每周一 09:00 按 topics.txt 跑一遍，深度 2
tools\install-task.ps1 -Time 09:00 -Weekly Monday -File topics.txt -Depth 2

# 每天 08:30
tools\install-task.ps1 -Time 08:30 -Daily -File topics.txt

# 先看看会注册什么（不落地）
tools\install-task.ps1 -Time 09:00 -Weekly Monday -WhatIf

# 立即试跑一次 / 查看上次结果 / 删除
Start-ScheduledTask -TaskName MRA-Weekly-Report
Get-ScheduledTask -TaskName MRA-Weekly-Report | Get-ScheduledTaskInfo
tools\install-task.ps1 -Remove -Name MRA-Weekly-Report
```

任务在当前用户下运行，不需要管理员；机器睡眠错过了会在唤醒后补跑（`StartWhenAvailable`）。

> 注意：定时任务读的是**仓库根的 `.env`**，所以填一次就够。
> 如果机器重启后 Dify 挂了不影响这条路（CLI 不依赖 Dify）。

---

## 5. 网页版 / 给别的系统调

**自己点**：http://127.0.0.1:8080/apps → 市场调研报告助手 v3 → 填表单 → 运行。

**别的系统调**（Dify service API，先在应用里建 API Key）：

```bash
curl -X POST http://127.0.0.1:8080/v1/chat-messages \
  -H "Authorization: Bearer app-xxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {"market_scope":"中国大陆","industry":"消费品/快消","research_purpose":"竞品分析","time_range":"近三年","source_pref":"不限","depth":"3"},
    "query": "调研胶囊咖啡在中国市场的竞争格局",
    "response_mode": "blocking",
    "user": "my-script"
  }'
```

返回 JSON 里的 `answer` 就是 Markdown 报告。

---

## 选哪条？

| 场景 | 用 |
|---|---|
| 每天临时问一两句 | 命令行（1） |
| 不想碰终端 | 双击（2） |
| 一次要看 5~20 个主题 | 批量（3） |
| 固定节奏（周报/日报） | 定时（4） |
| 团队共用、要界面 | 网页（5） |
| 接到飞书/钉钉/内部系统 | 网页 API（5） |
