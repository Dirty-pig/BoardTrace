$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Exe = Join-Path $Root 'BoardTrace.exe'
$PidFile = Join-Path $Root 'data\server.pid'
if (-not (Test-Path -LiteralPath $PidFile -PathType Leaf)) {
    Write-Host 'No BoardTrace server PID was found.'
    exit 0
}
$ServerPid = [int](Get-Content -LiteralPath $PidFile -Raw)
$Server = Get-CimInstance Win32_Process -Filter "ProcessId=$ServerPid"
if ($Server -and $Server.ExecutablePath -eq $Exe) {
    Stop-Process -Id $ServerPid
    Write-Host 'BoardTrace server stopped.'
} else {
    Write-Host 'The saved PID does not belong to this BoardTrace package.'
}
Remove-Item -LiteralPath $PidFile -Force
