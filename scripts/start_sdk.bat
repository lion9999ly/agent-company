@echo off
chcp 65001 >nul 2>&1
cd /d D:\Users\uih00653\my_agent_company\pythonProject1

set PID_FILE=.ai-state\sdk.pid
set LOG_FILE=.ai-state\feishu_sdk.log

echo 启动 SDK...

REM 停止旧进程
if exist "%PID_FILE%" (
    set /p OLD_PID=<"%PID_FILE%"
    taskkill /PID %OLD_PID% /F >nul 2>&1
    del "%PID_FILE%" >nul 2>&1
)

REM 通过进程名停止
for /f "tokens=2" %%i in ('wmic process where "commandline like '%%feishu_sdk%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /PID %%i /F >nul 2>&1
)

REM 清空日志
echo [%date% %time%] SDK 启动中... > "%LOG_FILE%"

REM 启动后台进程
start /B "" ".venv\Scripts\pythonw.exe" "scripts\feishu_sdk_client_v2.py" >> "%LOG_FILE%" 2>&1

REM 等待进程启动
ping -n 3 127.0.0.1 >nul

REM 获取 PID
for /f "tokens=2" %%i in ('wmic process where "commandline like '%%feishu_sdk%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    echo %%i > "%PID_FILE%"
    echo SDK 已启动，PID: %%i
    echo [%date% %time%] SDK 已启动，PID: %%i >> "%LOG_FILE%"
    goto :done
)

:done
echo 完成