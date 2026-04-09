@echo off
chcp 65001 >nul 2>&1
cd /d D:\Users\uih00653\my_agent_company\pythonProject1

set PID_FILE=.ai-state\sdk.pid

echo 停止 SDK...

REM 通过 PID 文件停止
if exist "%PID_FILE%" (
    set /p PID=<"%PID_FILE%"
    taskkill /PID %PID% /F >nul 2>&1
    del "%PID_FILE%" >nul 2>&1
    echo 已停止 PID: %PID%
)

REM 通过进程名停止
for /f "tokens=2" %%i in ('wmic process where "commandline like '%%feishu_sdk%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /PID %%i /F >nul 2>&1
    echo 已停止 PID: %%i
)

echo 完成