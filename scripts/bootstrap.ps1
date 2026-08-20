$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$UseLauncher = $false
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 12))"
    $UseLauncher = $LASTEXITCODE -eq 0
}

if ($UseLauncher) {
    & py -3 -m venv .venv
} else {
    & python -c "import sys; raise SystemExit(sys.version_info < (3, 12))"
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.12 or newer is required."
    }
    & python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[daifuku,dev]"
& .\.venv\Scripts\python.exe -m playwright install chromium
& .\.venv\Scripts\pokesleep-score.exe doctor

Write-Host "Ready. Run: .\.venv\Scripts\pokesleep-score.exe demo"
