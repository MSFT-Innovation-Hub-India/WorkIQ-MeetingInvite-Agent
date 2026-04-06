# Start Hub SE Agent (invisible, detached from this terminal)
$projectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pythonw = Join-Path $projectDir ".venv\Scripts\pythonw.exe"
$agent = Join-Path $projectDir "meeting_agent.py"

if (-not (Test-Path $pythonw)) {
    Write-Host "pythonw.exe not found at $pythonw" -ForegroundColor Red
    exit 1
}

Start-Process -FilePath $pythonw -ArgumentList $agent -WorkingDirectory $projectDir -WindowStyle Hidden
Write-Host "Hub SE Agent started. Look for the tray icon near the clock." -ForegroundColor Green
