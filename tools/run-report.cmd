@echo off
rem 双击即可：问几个问题 -> 出报告 -> 自动打开
rem 也可带参：run-report.cmd -Topic "调研XX市场" -Depth 2
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-report.ps1" %*
echo.
pause
