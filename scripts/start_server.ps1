$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'python_env.ps1')
$PythonExe = Get-BoardTracePython
if (-not (Test-Path -LiteralPath $PythonExe)) { throw "Python environment not found. Run scripts\setup_env.ps1 first." }
Set-Location -LiteralPath $ProjectDir
$Listener = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($Listener) {
    Write-Host "BoardTrace is already running: http://127.0.0.1:5000"
    exit 0
}
$LanAddress = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq "Up" } | ForEach-Object { $_.IPv4Address.IPAddress } | Select-Object -First 1
Write-Host "Starting BoardTrace: http://127.0.0.1:5000"
if ($LanAddress) { Write-Host "LAN access: http://${LanAddress}:5000" }
& $PythonExe (Join-Path $ProjectDir "scripts\serve.py")
