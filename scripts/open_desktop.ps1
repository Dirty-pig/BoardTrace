$ErrorActionPreference = 'Stop'

$ProjectDir = Split-Path -Parent $PSScriptRoot
$SiteUrl = 'http://127.0.0.1:5000'

$EdgeCandidates = @(
    'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    (Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\Application\msedge.exe')
)
$EdgeExe = $EdgeCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $EdgeExe) {
    throw 'Microsoft Edge not found. Install Edge or update its path in scripts\open_desktop.ps1.'
}

$Listener = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $Listener) { throw 'BoardTrace server is not running. Run the Start Server script first.' }
$Owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($Listener.OwningProcess)"
$ServerScript = Join-Path $PSScriptRoot 'serve.py'
if (-not $Owner -or $Owner.CommandLine -notlike "*$ServerScript*") {
    throw 'Port 5000 is used by another process, not BoardTrace.'
}
try {
    $Health = Invoke-RestMethod -Uri "$SiteUrl/healthz" -TimeoutSec 3
} catch {
    throw 'BoardTrace server is not ready. Run the Start Server script and try again.'
}
if ($Health.status -ne 'ok') { throw 'BoardTrace health check failed.' }

Start-Process -FilePath $EdgeExe -ArgumentList "--app=$SiteUrl" -WorkingDirectory $ProjectDir
Write-Host 'BoardTrace window opened. No server was started by this script.'
