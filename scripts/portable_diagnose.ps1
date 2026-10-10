$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Exe = Join-Path $Root 'BoardTrace.exe'
$LogDir = Join-Path $Root 'data\logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Report = Join-Path $LogDir 'app-control-report.txt'

$Lines = @(
    "Collected: $(Get-Date -Format s)",
    "Executable: $Exe",
    "SHA256: $((Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash)",
    "Signature: $((Get-AuthenticodeSignature -FilePath $Exe).Status)",
    ''
)

foreach ($LogName in @(
    'Microsoft-Windows-CodeIntegrity/Operational',
    'Microsoft-Windows-AppLocker/EXE and DLL'
)) {
    $Lines += "[$LogName]"
    try {
        $Matches = @(Get-WinEvent -LogName $LogName -MaxEvents 150 -ErrorAction Stop |
            Where-Object { $_.Message -like '*BoardTrace.exe*' } |
            Select-Object -First 10)
        if ($Matches.Count -eq 0) { $Lines += 'No recent BoardTrace.exe events found.' }
        foreach ($Event in $Matches) {
            $Lines += "Time: $($Event.TimeCreated)  Event ID: $($Event.Id)"
            $Lines += $Event.Message
            $Lines += ''
        }
    } catch {
        $Lines += "Could not read this log: $($_.Exception.Message)"
    }
    $Lines += ''
}

$Lines | Set-Content -LiteralPath $Report -Encoding UTF8
Write-Host "Report written to $Report"
