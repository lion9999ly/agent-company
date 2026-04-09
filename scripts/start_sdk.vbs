' SDK 后台静默启动脚本
' 放到 Windows 启动目录实现开机自启

Set ws = CreateObject("WScript.Shell")
ws.CurrentDirectory = "D:\Users\uih00653\my_agent_company\pythonProject1"
ws.Run "cmd /c .venv\Scripts\pythonw.exe scripts\feishu_sdk_client_v2.py >> .ai-state\feishu_sdk.log 2>&1", 0, False