# Create Windows Scheduled Task - Scheduled_Tasks_AutoStart
# Run with admin privileges

$TaskName = "Scheduled_Tasks_AutoStart"
$VbsPath = "D:\Users\uih00653\metabot\start_scheduled_tasks_hidden.vbs"
$BatPath = "D:\Users\uih00653\metabot\start_scheduled_tasks.bat"

# Create BAT file if not exists
if (-not (Test-Path $BatPath)) {
    $BatContent = '@echo off
cd /d D:\Users\uih00653\my_agent_company\pythonProject1
set PYTHONPATH=D:\Users\uih00653\my_agent_company\pythonProject1
py scripts\scheduled_tasks.py
timeout /t 10 /nobreak'
    Set-Content -Path $BatPath -Value $BatContent -Encoding ASCII
}

# Create VBS file if not exists
if (-not (Test-Path $VbsPath)) {
    $VbsContent = 'Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "' + $BatPath + '", 0, False
Set WshShell = Nothing'
    Set-Content -Path $VbsPath -Value $VbsContent -Encoding ASCII
}

# Check if task exists
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create task
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $VbsPath -WorkingDirectory "D:\Users\uih00653\metabot"
$trigger = New-ScheduledTaskTrigger -AtLogon
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
$principal = New-ScheduledTaskPrincipal -UserId "uih00653" -LogonType Interactive -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Scheduled Tasks AutoStart" -Force

Write-Host "Task created: $TaskName"
Write-Host "Trigger: AtLogon"
Write-Host "Command: wscript.exe $VbsPath"