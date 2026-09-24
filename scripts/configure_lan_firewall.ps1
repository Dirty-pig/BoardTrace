$ErrorActionPreference = "Stop"

$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
$IsAdmin = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
    throw "Administrator rights are required. Right-click PowerShell and choose Run as administrator."
}

$RuleName = "BoardTrace TCP 5000"
$Existing = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
if ($Existing) {
    Set-NetFirewallRule -DisplayName $RuleName -Enabled True -Direction Inbound -Action Allow -Profile Public
    Write-Host "Firewall rule enabled: $RuleName"
} else {
    New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5000 -Profile Public -RemoteAddress LocalSubnet | Out-Null
    Write-Host "Firewall rule created: $RuleName"
}

Write-Host "Allowed source: LocalSubnet"
Write-Host "Local port: TCP 5000"
