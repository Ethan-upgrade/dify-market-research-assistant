# 在桌面创建一个「跑一份调研」快捷方式（可重复运行，会覆盖）
#   .\tools\make-shortcut.ps1
#   .\tools\make-shortcut.ps1 -Name "市场调研" -Remove
[CmdletBinding()]
param(
    [string]$Name = "跑一份调研",
    [switch]$Remove
)

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$desk = [Environment]::GetFolderPath("Desktop")
$target = Join-Path $root "tools\run-report.cmd"
$lnk = Join-Path $desk ($Name + ".lnk")

if ($Remove) {
    if (Test-Path -LiteralPath $lnk) { Remove-Item -LiteralPath $lnk -Force; Write-Host "已删除 $lnk" } else { Write-Host "没有 $lnk" }
    exit 0
}

if (-not (Test-Path -LiteralPath $target)) { Write-Host "找不到 $target" -ForegroundColor Red; exit 2 }

try {
    $sh = New-Object -ComObject WScript.Shell
    $sc = $sh.CreateShortcut($lnk)
    $sc.TargetPath = $target
    $sc.WorkingDirectory = $root
    $sc.IconLocation = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe,0"
    $sc.Description = "市场调研报告助手"
    $sc.Save()
} catch {
    # 中文文件名在个别环境下写不进去，退回 ASCII 名
    $lnk = Join-Path $desk "Market-Research.lnk"
    $sh = New-Object -ComObject WScript.Shell
    $sc = $sh.CreateShortcut($lnk)
    $sc.TargetPath = $target
    $sc.WorkingDirectory = $root
    $sc.Save()
    Write-Host "（中文名失败，已用 ASCII 名）" -ForegroundColor Yellow
}

if (Test-Path -LiteralPath $lnk) {
    Write-Host "已创建：$lnk" -ForegroundColor Green
} else {
    Write-Host "创建失败" -ForegroundColor Red; exit 1
}
