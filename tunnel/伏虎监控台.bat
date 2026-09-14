@echo off
title 伏虎监控台 - FuHu Status

echo.
echo    ================================
echo      伏 虎 监 控 台   FuHu Status
echo    ================================
echo.

netstat -ano | findstr "LISTENING" | findstr ":8899" >nul
if not errorlevel 1 (
    echo    [i] 8899 已被占用, 结束旧进程...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":8899"') do taskkill /f /pid %%a >nul 2>&1
    timeout /t 2 /nobreak >nul
)

if not exist "C:\Users\ciallo0721_cmd\fuhu-status\status_server.py" (
    echo    [x] 找不到 status_server.py
    echo.
    timeout /t 20 /nobreak >nul
    exit /b 1
)

start "" /min "C:\Users\ciallo0721_cmd\AppData\Local\Programs\Python\Python39\pythonw.exe" "C:\Users\ciallo0721_cmd\fuhu-status\status_server.py"
timeout /t 6 /nobreak >nul

netstat -ano | findstr "LISTENING" | findstr ":8899" >nul
if errorlevel 1 (echo    [x] 启动失败) else (echo    [v] 监控台已运行  http://localhost:8899)
echo.
timeout /t 12 /nobreak >nul
exit /b 0
