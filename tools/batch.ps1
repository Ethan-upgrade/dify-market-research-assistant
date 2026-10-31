# 批量跑：topics.txt 一行一个主题，顺序执行，各自出一份报告
#
#   .\tools\batch.ps1                        # 用 topics.txt（默认）
#   .\tools\batch.ps1 -File my-topics.txt -Depth 2 -Offline
#   .\tools\batch.ps1 -Topics "调研A","调研B" -Depth 3
#
# topics.txt 里 # 开头的行会被忽略。

[CmdletBinding()]
param(
    [string]$File = "topics.txt",
    [string[]]$Topics = @(),
    [string]$Market = "中国大陆",
    [string]$Industry = "不限",
    [string]$Purpose = "竞品分析",
    [ValidateSet("2", "3", "4")][string]$Depth = "3",
    [switch]$Offline,
    [switch]$ContinueOnError
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$standalone = Join-Path $root "standalone"
$reports = Join-Path $root "reports"
New-Item -ItemType Directory -Force -Path $reports | Out-Null

if (-not $Topics -or $Topics.Count -eq 0) {
    $path = if ([IO.Path]::IsPathRooted($File)) { $File } else { Join-Path $root $File }
    if (-not (Test-Path $path)) {
        Write-Host "找不到 $path。先写几行主题，或用 -Topics 直接给。" -ForegroundColor Yellow
        exit 2
    }
    $Topics = Get-Content $path -Encoding UTF8 |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and -not $_.StartsWith("#") }
}

if (-not $Topics) { Write-Host "没有可跑的主题。"; exit 2 }

Write-Host ("共 {0} 个主题，深度 {1}{2}" -f $Topics.Count, $Depth, $(if ($Offline) { "，离线模式" } else { "" }))
$stamp = Get-Date -Format "yyyy-MM-dd-HHmm"
$i = 0
$ok = 0; $fail = 0

foreach ($t in $Topics) {
    $i++
    $slug = ($t -replace '[\\/:*?"<>|\s]+', '-')
    if ($slug.Length -gt 40) { $slug = $slug.Substring(0, 40) }
    $out = Join-Path $reports ("{0}-{1:d2}-{2}.md" -f $stamp, $i, $slug)

    Write-Host ""
    Write-Host ("[{0}/{1}] {2}" -f $i, $Topics.Count, $t) -ForegroundColor Cyan

    $cliArgs = @("-m", "mra", $t, "--market", $Market, "--industry", $Industry,
              "--purpose", $Purpose, "--depth", $Depth, "-o", $out)
    if ($Offline) {
        $cliArgs += @("--search", "fixture", "--fixture", (Join-Path $standalone "tests\fixtures\corpus.json"))
    }

    Push-Location $standalone
    try { & python @cliArgs } catch { Write-Host ("  异常：{0}" -f $_.Exception.Message) -ForegroundColor Red }
    $code = $LASTEXITCODE
    Pop-Location

    if ((Test-Path $out) -and $code -eq 0) {
        $ok++
        "[{0}] OK   {1} | {2}" -f (Get-Date -Format s), $t, $out | Add-Content (Join-Path $reports "run-log.txt") -Encoding UTF8
    } else {
        $fail++
        "[{0}] FAIL exit={1} | {2}" -f (Get-Date -Format s), $code, $t | Add-Content (Join-Path $reports "run-log.txt") -Encoding UTF8
        Write-Host ("  失败，退出码 {0}" -f $code) -ForegroundColor Yellow
        if (-not $ContinueOnError) {
            Write-Host "已停止（加 -ContinueOnError 可跳过失败继续）。" -ForegroundColor Yellow
            break
        }
    }
}

Write-Host ""
Write-Host ("完成：成功 {0}，失败 {1}。报告在 {2}" -f $ok, $fail, $reports) -ForegroundColor Green
exit $(if ($fail -gt 0) { 1 } else { 0 })
