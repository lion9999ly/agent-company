@echo off
chcp 65001 >nul 2>&1
title Smart Helmet RD Center v2
echo ==========================================
echo   Smart Helmet RD Center v2
echo ==========================================
cd /d D:\Users\uih00653\my_agent_company\pythonProject1
echo [1/2] Activating venv...
call .venv\Scripts\activate.bat
echo [2/2] Starting main service (v2 modular)...
python scripts/feishu_sdk_client_v2.py
pause