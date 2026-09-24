$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'python_env.ps1')
$PythonExe = Get-BoardTracePython
Set-Location -LiteralPath $ProjectDir
& $PythonExe (Join-Path $ProjectDir "scripts\backup_now.py")
