function Get-BoardTracePython {
    $ProjectDir = Split-Path -Parent $PSScriptRoot
    $Candidates = @(
        $env:BOARDTRACE_PYTHON,
        (Join-Path $ProjectDir '.venv\Scripts\python.exe'),
        (Join-Path $env:USERPROFILE 'miniconda3\envs\problem-system\python.exe'),
        (Join-Path $env:USERPROFILE 'anaconda3\envs\problem-system\python.exe')
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
            return $Candidate
        }
    }
    throw 'Python environment not found. Set BOARDTRACE_PYTHON or create .venv.'
}
