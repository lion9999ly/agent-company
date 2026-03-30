<#
.SYNOPSIS
一键重启 cc-connect 并验证规则加载
.DESCRIPTION
自动终止旧进程、重启 cc-connect、打开飞书验证提示
#>

# 1. 强制终止所有 node 进程（cc-connect）
Write-Host "正在终止旧的 cc-connect 进程..." -ForegroundColor Yellow
Get-Process | Where-Object {$_.ProcessName -like "*node*"} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# 2. 进入项目目录
$projectPath = "D:\Users\uih00653\my_agent_company\pythonProject1"
Set-Location $projectPath
Write-Host "已进入项目目录：$projectPath" -ForegroundColor Green

# 3. 启动 cc-connect（在新窗口运行，避免阻塞）
Write-Host "正在启动 cc-connect..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$projectPath'; npx cc-connect@latest"

# 4. 弹出提示，提醒去飞书验证
Write-Host "`n✅ cc-connect 重启成功！" -ForegroundColor Green
Write-Host "⚠️  请立即去飞书端发送纯文本验证规则加载：" -ForegroundColor Cyan
Write-Host "   请列出你当前加载的所有CLAUDE.md规则" -ForegroundColor Cyan
Write-Host "`n按任意键关闭此窗口..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")