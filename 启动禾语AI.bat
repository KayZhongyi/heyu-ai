@echo off
setlocal
chcp 65001 >nul
set "ROOT=%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start-windows.ps1"
if errorlevel 1 (
  echo.
  echo 禾语 AI 启动失败。请查看上方错误信息。
  pause
  exit /b 1
)
