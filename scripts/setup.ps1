[CmdletBinding()]
param()

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $repoRoot ".venv"
$pythonLauncher = Get-Command py -ErrorAction SilentlyContinue

if ($null -eq $pythonLauncher) {
    Write-Error "Python launcher 'py' was not found. Install Python 3.12 first."
    exit 1
}

if (-not (Test-Path -LiteralPath $venvPath)) {
    & $pythonLauncher.Source -3.12 -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $venvPython -m pip install --editable "${repoRoot}[dev]"
exit $LASTEXITCODE
