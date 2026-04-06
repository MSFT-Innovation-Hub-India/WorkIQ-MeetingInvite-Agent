# Stop Hub SE Agent
$stopped = $false
Get-Process pythonw -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.Id -Force
    $stopped = $true
}
if ($stopped) {
    Write-Host "Hub SE Agent stopped." -ForegroundColor Yellow
} else {
    Write-Host "Hub SE Agent is not running." -ForegroundColor Gray
}
