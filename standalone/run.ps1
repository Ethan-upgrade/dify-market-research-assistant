# 市场调研报告助手 —— 零依赖 CLI 启动器
# 用法： .\run.ps1 "调研胶囊咖啡在中国市场的竞争格局" --market 中国大陆 --depth 3
#
# 首次使用：把下面四个变量填好，或先 copy ..\.env.example ..\.env 再自行 source。

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

if (-not $env:MRA_BASE_URL)    { $env:MRA_BASE_URL = "https://api.deepseek.com/v1" }
if (-not $env:MRA_MODEL)       { $env:MRA_MODEL = "deepseek-chat" }
# $env:MRA_API_KEY = "sk-..."
# $env:TAVILY_API_KEY = "tvly-..."

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $here
try {
    python -m mra @args
} finally {
    Pop-Location
}
