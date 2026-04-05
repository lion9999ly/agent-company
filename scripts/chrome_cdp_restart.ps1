# Chrome CDP Restart Script
Write-Host "=== Restarting Chrome with CDP ==="

# 1. Kill all Chrome
Write-Host "[1] Killing all Chrome processes..."
Stop-Process -Name chrome -Force -ErrorAction SilentlyContinue

# 2. Wait for complete exit
Write-Host "[2] Waiting for Chrome to exit..."
Start-Sleep -Seconds 5

# Verify no Chrome running
$remaining = Get-Process chrome -ErrorAction SilentlyContinue
if ($remaining) {
    Write-Host "  Warning: $($remaining.Count) Chrome processes still running"
    Stop-Process -Name chrome -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}

# 3. Create unique profile dir
$profileDir = "$env:TEMP\chrome-cdp-$([DateTime]::Now.Ticks)"
Write-Host "[3] Profile dir: $profileDir"
New-Item -ItemType Directory -Path $profileDir -Force | Out-Null

# 4. Start Chrome with CDP
Write-Host "[4] Starting Chrome..."
$chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$arguments = "--remote-debugging-port=9333 --user-data-dir=$profileDir"
Start-Process $chromePath -ArgumentList $arguments

# 5. Wait for Chrome to start
Write-Host "[5] Waiting for Chrome to initialize..."
Start-Sleep -Seconds 8

# 6. Check CDP
Write-Host "[6] Checking CDP endpoint..."
try {
    $result = Invoke-WebRequest -Uri "http://127.0.0.1:9333/json/version" -UseBasicParsing -TimeoutSec 5
    Write-Host "  SUCCESS! CDP is working."
    Write-Host "  $($result.Content)"
} catch {
    Write-Host "  FAILED: $($_.Exception.Message)"
    Write-Host ""
    Write-Host "  Checking port status..."
    $portCheck = netstat -ano | Select-String "9333"
    if ($portCheck) {
        Write-Host "  $portCheck"
    } else {
        Write-Host "  Port 9333 not found in netstat"
    }
}

Write-Host ""
Write-Host "=== Done ==="
Write-Host "Chrome should now be open."
Write-Host "If CDP is working, go to: https://claude.ai/chat/06d4bcbe-f474-4de9-9f88-ed187c0c687c"