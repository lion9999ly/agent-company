# Chrome CDP Diagnostic Script
Write-Host "=== Chrome CDP Diagnostic ==="

# 1. Check Chrome processes
Write-Host ""
Write-Host "[1] Chrome processes:"
$chromeProcesses = Get-Process chrome -ErrorAction SilentlyContinue
if ($chromeProcesses) {
    Write-Host "  Found $($chromeProcesses.Count) Chrome processes"
} else {
    Write-Host "  No Chrome processes found"
}

# 2. Check listening ports
Write-Host ""
Write-Host "[2] Listening ports (9222, 9333):"
$ports = netstat -ano | Select-String "9222|9333" | Select-String "LISTENING"
if ($ports) {
    Write-Host "  $ports"
} else {
    Write-Host "  No ports listening"
}

# 3. Try to connect to CDP
Write-Host ""
Write-Host "[3] Try CDP endpoints:"
foreach ($p in @(9222, 9333)) {
    try {
        $result = Invoke-WebRequest -Uri "http://127.0.0.1:${p}/json/version" -UseBasicParsing -TimeoutSec 2
        Write-Host "  Port ${p}: SUCCESS"
        Write-Host "  $($result.Content)"
    } catch {
        Write-Host "  Port ${p}: FAILED"
    }
}

# 4. Check Chrome command lines
Write-Host ""
Write-Host "[4] Chrome command lines with remote-debugging:"
$cmdLines = Get-WmiObject Win32_Process -Filter "name='chrome.exe'" |
    Where-Object { $_.CommandLine -like '*remote-debugging*' } |
    Select-Object ProcessId, CommandLine
if ($cmdLines) {
    foreach ($cmd in $cmdLines) {
        $shortCmd = $cmd.CommandLine.Substring(0, [Math]::Min(100, $cmd.CommandLine.Length))
        Write-Host "  PID $($cmd.ProcessId): $shortCmd..."
    }
} else {
    Write-Host "  No Chrome with remote-debugging found"
}

Write-Host ""
Write-Host "=== End Diagnostic ==="