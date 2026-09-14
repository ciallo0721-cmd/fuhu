@echo off
title 伏虎穿透 - FuHu Tunnel
set EXE=C:\Users\ciallo0721_cmd\fuhu-status\cloudflared.exe
set CFG=C:\Users\ciallo0721_cmd\.cloudflared\config.yml

echo.
echo    ================================
echo      伏 虎 穿 透   FuHu Tunnel
echo    ================================
echo.

if not exist "%EXE%" (
    echo    [x] 找不到 cloudflared.exe
    echo.
    ping -n 12 127.0.0.1 >nul
    exit /b 1
)

tasklist /fi "imagename eq cloudflared.exe" 2>nul | find /i "cloudflared.exe" >nul
if not errorlevel 1 (
    echo    [*] 发现旧隧道, 正在结束...
    taskkill /f /im cloudflared.exe >nul 2>&1
    ping -n 4 127.0.0.1 >nul
)

echo    [*] 正在拉起隧道...
start "" /min "%EXE%" --config "%CFG%" tunnel run
ping -n 10 127.0.0.1 >nul

tasklist /fi "imagename eq cloudflared.exe" 2>nul | find /i "cloudflared.exe" >nul
if errorlevel 1 (
    echo    [x] 隧道启动失败
    echo.
    ping -n 20 127.0.0.1 >nul
    exit /b 1
)

echo    [v] 隧道已运行
netstat -ano | findstr "LISTENING" | findstr ":8899" >nul
if errorlevel 1 (echo    [!] 监控台 8899 未监听) else (echo    [v] 监控台 8899 正常)
netstat -ano | findstr "LISTENING" | findstr ":80 " >nul
if errorlevel 1 (echo    [!] MiniNAS 80 未监听) else (echo    [v] MiniNAS 80 正常)

echo.
echo    ----------------------------------------
echo     nas.ciallo0721-cmd.top   --^> :80
echo     status.xn--voqu06k.cc    --^> :8899
echo    ----------------------------------------
echo.
echo    隧道已在后台运行, 窗口稍后自动关闭
ping -n 14 127.0.0.1 >nul
exit /b 0
