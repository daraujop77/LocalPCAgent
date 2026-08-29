[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$relativePath = "artifacts/m3-pc-acceptance-$([guid]::NewGuid().ToString('N')).txt"
$knownText = "Personal AI Platform M3 acceptance`r`n"

function Invoke-PcAction {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Payload
    )

    $response = Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/v1/pc/invoke" `
        -ContentType "application/json" `
        -Body ($Payload | ConvertTo-Json -Depth 8)
    if (-not $response.success) {
        throw "PC action '$($Payload.action)' failed: $($response.error)"
    }
    return $response
}

$launch = Invoke-PcAction @{ 
    action = "pc.apps.launch"
    parameters = @{
        executable = "notepad.exe"
        path = $relativePath
    }
}
Start-Sleep -Seconds 2

$windows = Invoke-PcAction @{ action = "pc.window.list" }
$window = $windows.data.windows |
    Where-Object { $_.title -like "*$([System.IO.Path]::GetFileName($relativePath))*" } |
    Select-Object -First 1
if ($null -eq $window) {
    throw "The Notepad acceptance window was not found."
}

Invoke-PcAction @{
    action = "pc.window.focus"
    parameters = @{ hwnd = [int]$window.hwnd }
} | Out-Null
Invoke-PcAction @{
    action = "pc.input.type"
    parameters = @{ approval_granted = $true; text = $knownText }
} | Out-Null
Invoke-PcAction @{
    action = "pc.input.hotkey"
    parameters = @{ approval_granted = $true; keys = @("CTRL", "S") }
} | Out-Null
Start-Sleep -Seconds 1

$read = Invoke-PcAction @{ action = "pc.files.read"; target = $relativePath }
if ($read.data.content -ne $knownText) {
    throw "The saved file contents did not match the known acceptance text."
}

Invoke-PcAction @{
    action = "pc.apps.close"
    parameters = @{ approval_granted = $true; hwnd = [int]$window.hwnd }
} | Out-Null

Write-Output "M3 PC acceptance passed."
Write-Output "Controlled file: $relativePath"
