$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
$CondaCandidates = @(
    $env:CONDA_EXE,
    (Join-Path $env:USERPROFILE 'miniconda3\Scripts\conda.exe'),
    (Join-Path $env:USERPROFILE 'anaconda3\Scripts\conda.exe')
)
$CondaExe = $CondaCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
if (-not $CondaExe) { throw 'Conda not found. Install Miniconda or set CONDA_EXE.' }
& $CondaExe env update -n problem-system -f (Join-Path $ProjectDir "environment.yml") --prune
Write-Host "Environment ready: problem-system"
