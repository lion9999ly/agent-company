@echo off
chcp 65001 >nul
echo ==========================================
echo   智能骑行头盔虚拟研发中心 - 一键启动
echo ==========================================
echo.

cd /d D:\Users\uih00653\my_agent_company\pythonProject1

echo [1/2] 激活虚拟环境...
call .venv\Scripts\activate.bat

echo [2/2] 启动主服务（含 watchdog + 每日学习 + 文档监控）...
python scripts/feishu_sdk_client.py

pause