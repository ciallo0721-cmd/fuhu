@echo off
title FuHu Tunnel
set EXE=C:\Users\ciallo0721_cmd\fuhu-status\cloudflared.exe
set CFG=C:\Users\ciallo0721_cmd\.cloudflared\config.yml
set LOG=C:\Users\ciallo0721_cmd\fuhu-status\launch.log

echo [%date% %time%] launch >> "%LOG%"

if not exist "%EXE%" (echo [x] exe missing >> "%LOG%" & exit /b 1)
if not exist "%CFG%" (echo [x] cfg missing >> "%LOG%" & exit /b 1)

tasklist /fi "imagename eq cloudflared.exe" 2>nul | find /i "cloudflared.exe" >nul
if not errorlevel 1 (
    taskkill /f /im cloudflared.exe >nul 2>&1
    ping -n 3 127.0.0.1 >nul
)

start "" /min "%EXE%" --config "%CFG%" tunnel run
ping -n 9 127.0.0.1 >nul

tasklist /fi "imagename eq cloudflared.exe" 2>nul | find /i "cloudflared.exe" >nul
if errorlevel 1 (echo [x] failed >> "%LOG%" & exit /b 1)
echo [v] ok >> "%LOG%"
exit /b 0
