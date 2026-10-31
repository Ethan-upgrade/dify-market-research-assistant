# 注册 / 移除「定时自动跑调研」的 Windows 计划任务（当前用户，不需要管理员）
#
#   .\tools\install-task.ps1 -Time 09:00 -Weekly Monday -File topics.txt -Depth 2
#   .\tools\install-task.ps1 -Time 09:00 -Daily -File topics.txt
#   .\tools\install-task.ps1 -WhatIf                 # 只看会注册什么，不落地
#   .\tools\install-task.ps1 -Remove                 # 删掉该任务
#   .\tools\install-task.ps1 -Remove -Name MRA-TEST  # 删指定名字
#
# 任务行为：到点自动运行 batch.ps1，报告落进 reports\，日志追加到 reports\run-log.txt。

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Name = "MRA-Weekly-Report",
    [string]$Time = "09:00",
    [ValidateSet("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")]
    [string]$Weekly = "Monday",
    [switch]$Daily,
    [string]$File = "topics.txt",
    [ValidateSet("2", "3", "4")][string]$Depth = "3",
    [string]$Market = "中国大陆",
    [string]$Purpose = "竞品分析",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$batch = Join-Path $root "tools\batch.ps1"

if ($Remove) {
    $exist = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if (-not $exist) { Write-Host "没有名为 $Name 的任务。"; exit 0 }
    if ($PSCmdlet.ShouldProcess($Name, "删除计划任务")) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
        Write-Host "已删除任务：$Name" -ForegroundColor Green
    }
    exit 0
}

$psArgs = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -File "{1}" -Depth {2} -Market "{3}" -Purpose "{4}"' -f `
    $batch, $File, $Depth, $Market, $Purpose

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs -WorkingDirectory $root

if ($Daily) {
    $trigger = New-ScheduledTaskTrigger -Daily -At $Time
    $desc = "每天 $Time"
} else {
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Weekly -At $Time
    $desc = "每周 $Weekly $Time"
}

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)

Write-Host "将注册任务：" -ForegroundColor Cyan
Write-Host "  名称：$Name"
Write-Host "  时间：$desc"
Write-Host "  动作：powershell $psArgs"
Write-Host "  主题：$File（$root）"

if ($PSCmdlet.ShouldProcess($Name, "注册计划任务")) {
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Settings $settings `
        -Description "市场调研报告助手：定时批量出报告" -Force | Out-Null
    Write-Host "已注册。查看：Get-ScheduledTask -TaskName $Name | Get-ScheduledTaskInfo" -ForegroundColor Green
    Write-Host "试跑一次：Start-ScheduledTask -TaskName $Name" -ForegroundColor Green
    Write-Host "删除：.\tools\install-task.ps1 -Remove -Name $Name" -ForegroundColor Green
}
