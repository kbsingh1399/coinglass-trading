Write-Host "Waiting for Engine_1.py to start..."
while ($true) {
    $process = Get-WmiObject Win32_Process -Filter "Name='python.exe' AND CommandLine LIKE '%Engine_1.py%'" -ErrorAction SilentlyContinue
    if ($process) {
        Write-Host "Engine_1.py is now running. Watching for crashes..."
        break
    }
    Start-Sleep -Seconds 2
}

while ($true) {
    $process = Get-WmiObject Win32_Process -Filter "Name='python.exe' AND CommandLine LIKE '%Engine_1.py%'" -ErrorAction SilentlyContinue
    if (-not $process) {
        Write-Output "CRASH DETECTED - WAKING UP AGENT"
        exit 0
    }
    Start-Sleep -Seconds 2
}
