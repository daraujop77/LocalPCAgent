[CmdletBinding()]
param()

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Error "M3 environment not found. Run .\scripts\setup.ps1 first."
    exit 1
}

Set-Location $repoRoot
& $venvPython -m ruff format --check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $venvPython -m ruff check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $venvPython -m pytest
exit $LASTEXITCODE
