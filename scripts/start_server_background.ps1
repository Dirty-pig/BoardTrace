$ErrorActionPreference = 'Stop'

$ProjectDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'python_env.ps1')
$PythonExe = Get-BoardTracePython
$ServerScript = Join-Path $PSScriptRoot 'serve.py'
$SiteUrl = 'http://127.0.0.1:5000'

# Serialize simultaneous double-clicks so both launchers cannot start a server.
$Mutex = [System.Threading.Mutex]::new($false, 'Local\BoardTraceServiceLauncher')
$HasLock = $false
try {
    try {
        $HasLock = $Mutex.WaitOne(10000)
    } catch [System.Threading.AbandonedMutexException] {
        $HasLock = $true
    }
    if (-not $HasLock) { throw 'Another BoardTrace launcher is still starting. Try again shortly.' }

    $Listener = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Listener) {
        $Owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($Listener.OwningProcess)"
        if (-not $Owner -or $Owner.CommandLine -notlike "*$ServerScript*") {
            throw 'Port 5000 is already used by another process. No new server was started.'
        }
        Write-Host "BoardTrace server is already running (PID $($Listener.OwningProcess))."
    } else {
        $LogDir = Join-Path $ProjectDir 'data\logs'
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        $Stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
        $Server = Start-Process -FilePath $PythonExe -ArgumentList ('"{0}"' -f $ServerScript) `
            -WorkingDirectory $ProjectDir -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $LogDir "server-$Stamp.out.log") `
            -RedirectStandardError (Join-Path $LogDir "server-$Stamp.err.log")
        Write-Host "BoardTrace server started in background (PID $($Server.Id))."
    }

    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        try {
            $Health = Invoke-RestMethod -Uri "$SiteUrl/healthz" -TimeoutSec 2
            if ($Health.status -eq 'ok') { $Ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 300
    }
    if (-not $Ready) {
        throw 'BoardTrace did not become ready. Check data\logs\server-*.err.log.'
    }
    Write-Host "BoardTrace is ready at $SiteUrl. Closing this window will not stop the server."
} finally {
    if ($HasLock) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
