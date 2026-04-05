@echo off
chcp 65001 >nul 2>&1
title Smart Helmet RD Center v2
cd /d D:\Users\uih00653\my_agent_company\pythonProject1

:loop
echo ==========================================
echo   Smart Helmet RD Center v2
echo   %date% %time%
echo ==========================================
echo [START] Feishu service starting...
.venv\Scripts\python.exe scripts/feishu_sdk_client_v2.py
echo.
echo [%date% %time%] Service exited, restarting in 5s...
timeout /t 5
goto loop
