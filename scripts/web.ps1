[CmdletBinding()]
param(
    [int]$Port = 4173
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Error "M15-M18 environment not found. Run .\scripts\setup.ps1 first."
    exit 1
}

Set-Location $repoRoot
& $pythonPath -m http.server $Port --directory (Join-Path $repoRoot "apps\web")
exit $LASTEXITCODE
