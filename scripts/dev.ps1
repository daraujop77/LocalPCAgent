[CmdletBinding()]
param(
    [int]$Port = 0
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Error "M4 environment not found. Run .\scripts\setup.ps1 first."
    exit 1
}

Set-Location $repoRoot
$pythonArguments = @("-m", "personal_ai.dev")
if ($Port -gt 0) {
    $pythonArguments += @("--port", $Port)
}
& $venvPython @pythonArguments
exit $LASTEXITCODE
