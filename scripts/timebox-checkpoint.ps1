[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
Set-Location -LiteralPath $repoRoot

$gitRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($gitRoot)) {
    throw "The timebox checkpoint is not running inside a Git repository."
}

$expectedRoot = [IO.Path]::GetFullPath($repoRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
$resolvedGitRoot = [IO.Path]::GetFullPath($gitRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
if ($resolvedGitRoot -ine $expectedRoot) {
    throw "The timebox checkpoint resolved an unexpected repository root: $resolvedGitRoot"
}

$status = @(& git status --porcelain=v1 --untracked-files=all)
if ($status.Count -eq 0) {
    exit 0
}

& git add -A
if ($LASTEXITCODE -ne 0) {
    throw "git add failed with exit code $LASTEXITCODE"
}

$commitMessage = "Save LocalAgent timebox progress $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
& git commit -m $commitMessage
if ($LASTEXITCODE -ne 0) {
    throw "git commit failed with exit code $LASTEXITCODE"
}

& git push origin main
if ($LASTEXITCODE -ne 0) {
    throw "git push failed with exit code $LASTEXITCODE"
}
