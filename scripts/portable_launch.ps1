$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Exe = Join-Path $Root 'BoardTrace.exe'
$DataDir = Join-Path $Root 'data'
$LogDir = Join-Path $DataDir 'logs'
$PidFile = Join-Path $DataDir 'server.pid'
$Port = if ($env:BOARDTRACE_PORT) { [int]$env:BOARDTRACE_PORT } else { 5000 }
$Url = "http://127.0.0.1:$Port"

if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) { throw 'BoardTrace.exe is missing.' }
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($Listener) {
    $OwnerProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($Listener.OwningProcess)"
    if (-not $OwnerProcess -or $OwnerProcess.ExecutablePath -ne $Exe) {
        throw "Port $Port is already in use by another program."
    }
} else {
    $Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $Server = Start-Process -FilePath $Exe -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $LogDir "server-$Stamp.out.log") `
        -RedirectStandardError (Join-Path $LogDir "server-$Stamp.err.log")
    Set-Content -LiteralPath $PidFile -Value $Server.Id -Encoding ASCII
}

$Ready = $false
for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
    try {
        $Health = Invoke-RestMethod -Uri "$Url/healthz" -TimeoutSec 2
        if ($Health.status -eq 'ok') { $Ready = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 300
}
if (-not $Ready) { throw 'BoardTrace did not start. Check the data/logs folder.' }
if ($env:BOARDTRACE_NO_BROWSER -ne '1') { Start-Process $Url }
