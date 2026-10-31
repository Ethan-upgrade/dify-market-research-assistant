@echo off
rem 让 `mra "主题" ...` 在任意目录可用。
rem 用法二选一：
rem   1) 把本文件所在目录加进 PATH，之后直接 `mra "调研 XX 市场"`
rem   2) 直接调用：D:\...\tools\mra.cmd "调研 XX 市场"
setlocal
set "ROOT=%~dp0.."
pushd "%ROOT%\standalone"
python -m mra %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
