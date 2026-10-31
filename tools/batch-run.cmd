@echo off
rem 双击即可：按 topics.txt 批量出报告
rem 也可带参：batch-run.cmd -File my-topics.txt -Depth 2
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0batch.ps1" %*
echo.
pause
