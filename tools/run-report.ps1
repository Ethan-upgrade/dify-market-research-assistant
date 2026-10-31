# 交互式跑一份调研：问几个问题 → 出报告 → 自动打开
#
# 双击运行（右键「使用 PowerShell 运行」）或：
#   .\tools\run-report.ps1
#   .\tools\run-report.ps1 -Topic "调研胶囊咖啡在中国市场的竞争格局" -Market 中国大陆 -Depth 2
#   .\tools\run-report.ps1 -Topic "..." -Offline        # 用离线语料，不花额度

[CmdletBinding()]
param(
    [string]$Topic = "",
    [string]$Market = "中国大陆",
    [string]$Industry = "消费品/快消",
    [string]$Purpose = "竞品分析",
    [string]$TimeRange = "近三年",
    [string]$Source = "不限",
    [ValidateSet("2", "3", "4")][string]$Depth = "3",
    [switch]$Offline,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$standalone = Join-Path $root "standalone"
$reports = Join-Path $root "reports"
New-Item -ItemType Directory -Force -Path $reports | Out-Null

function Ask($prompt, $default) {
    if ($default) { $v = Read-Host "$prompt [$default]" } else { $v = Read-Host $prompt }
    if ([string]::IsNullOrWhiteSpace($v)) { return $default }
    return $v.Trim()
}

if (-not $Topic) { $Topic = Ask "调研主题（一句话）" "" }
if ([string]::IsNullOrWhiteSpace($Topic)) { Write-Host "没给主题，退出。"; exit 2 }
if (-not $PSBoundParameters.ContainsKey("Market")) { $Market = Ask "地区（中国大陆 / 北美 / 不限（全球为主）…）" "中国大陆" }
if (-not $PSBoundParameters.ContainsKey("Purpose")) { $Purpose = Ask "目的（竞品分析 / 市场进入 / 新品立项 / 投资尽调 / 定价策略 / 渠道策略 / 行业概览）" "竞品分析" }
if (-not $PSBoundParameters.ContainsKey("Depth")) { $Depth = Ask "深度 2/3/4（3 最常用，约 12 credits）" "3" }

$slug = ($Topic -replace '[\\/:*?"<>|\s]+', '-')
if ($slug.Length -gt 40) { $slug = $slug.Substring(0, 40) }
$stamp = Get-Date -Format "yyyy-MM-dd-HHmm"
$out = Join-Path $reports "$stamp-$slug.md"

$cliArgs = @("-m", "mra", $Topic, "--market", $Market, "--industry", $Industry,
          "--purpose", $Purpose, "--time", $TimeRange, "--source", $Source,
          "--depth", $Depth, "-o", $out)
if ($Offline) {
    $cliArgs += @("--search", "fixture", "--fixture", (Join-Path $standalone "tests\fixtures\corpus.json"))
}

Write-Host ""
Write-Host "主题 : $Topic"
Write-Host "范围 : $Market ｜ $Industry ｜ $Purpose ｜ $TimeRange ｜ 深度 $Depth$(if ($Offline) { ' ｜ 离线模式' })"
Write-Host "输出 : $out"
Write-Host ""

Push-Location $standalone
try { & python @cliArgs } finally { Pop-Location }

$code = $LASTEXITCODE
if (Test-Path $out) {
    "[{0}] exit={1} chars={2} file={3} topic={4}" -f (Get-Date -Format s), $code, (Get-Item $out).Length, $out, $Topic |
        Add-Content -Path (Join-Path $reports "run-log.txt") -Encoding UTF8
    Write-Host ""
    Write-Host "报告已生成：$out" -ForegroundColor Green
    if (-not $NoOpen) { Invoke-Item $out }
} else {
    Write-Host "没生成报告（退出码 $code）。常见原因：信息不足触发追问（码 3）、Key 失效（码 1/2）。" -ForegroundColor Yellow
}
exit $code
