# 把 mra.serve 注册成「登录自启」的常驻服务（Windows，当前用户，不需要管理员）
#
#   .\tools\install-serve-task.ps1                      # 注册，端口 8765
#   .\tools\install-serve-task.ps1 -Port 9000 -Token abc
#   .\tools\install-serve-task.ps1 -WhatIf              # 只看会注册什么
#   .\tools\install-serve-task.ps1 -Remove              # 删除
#
# 行为：登录时自动启动 `python -m mra.serve`，失败每分钟重试一次（计划任务自带），
# 端口固定、日志写到 logs\serve.log。

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Name = "MRA-Serve",
    [int]$Port = 8765,
    [string]$Token = "",
    [int]$DelaySeconds = 20,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$standalone = Join-Path $root "standalone"
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

if ($Remove) {
    $exist = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if (-not $exist) { Write-Host "没有名为 $Name 的任务。"; exit 0 }
    if ($PSCmdlet.ShouldProcess($Name, "删除计划任务")) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
        Write-Host "已删除任务：$Name" -ForegroundColor Green
    }
    exit 0
}

$envPrefix = if ($Token) { "`$env:MRA_TOKEN='$Token'; " } else { "" }
$logFile = Join-Path $logs "serve.log"
$inner = "{0}Set-Location '{1}'; python -m mra.serve --port {2} *>> '{3}'" -f $envPrefix, $standalone, $Port, $logFile

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ("-NoProfile -WindowStyle Hidden -Command `"{0}`"" -f $inner) `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
if ($DelaySeconds -gt 0) { $trigger.Delay = "PT${DelaySeconds}S" }

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Write-Host "将注册常驻服务：" -ForegroundColor Cyan
Write-Host "  名称：$Name"
Write-Host "  触发：登录后 ${DelaySeconds}s（失败每分钟重启）"
Write-Host "  命令：powershell -NoProfile -WindowStyle Hidden -Command `"$inner`""
Write-Host "  日志：$logFile"

if ($PSCmdlet.ShouldProcess($Name, "注册计划任务")) {
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Settings $settings `
        -Description "市场调研报告助手：本地 HTTP 服务" -Force | Out-Null
    Write-Host "已注册。立即启动：Start-ScheduledTask -TaskName $Name" -ForegroundColor Green
    Write-Host "验证：Invoke-RestMethod http://127.0.0.1:$Port/health" -ForegroundColor Green
    Write-Host "删除：.\tools\install-serve-task.ps1 -Remove -Name $Name" -ForegroundColor Green
}
