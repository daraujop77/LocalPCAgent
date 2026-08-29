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

function Invoke-ApprovedPcAction {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Payload
    )

    $requestPayload = @{
        action = $Payload.action
        parameters = if ($Payload.parameters) { $Payload.parameters } else { @{} }
        requested_by = "scripts/pc-acceptance.ps1"
        reason = "Opt-in interactive M4 acceptance"
    }
    if ($Payload.target) {
        $requestPayload.target = $Payload.target
    }
    $approval = Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/v1/approvals" `
        -ContentType "application/json" `
        -Body ($requestPayload | ConvertTo-Json -Depth 8)
    Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/v1/approvals/$($approval.approval_id)/accept" `
        -ContentType "application/json" `
        -Body '{"decided_by":"interactive-acceptance-script"}' | Out-Null
    $Payload.parameters.approval_id = $approval.approval_id
    return Invoke-PcAction $Payload
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
Invoke-ApprovedPcAction @{
    action = "pc.input.type"
    parameters = @{ text = $knownText }
} | Out-Null
Invoke-ApprovedPcAction @{
    action = "pc.input.hotkey"
    parameters = @{ keys = @("CTRL", "S") }
} | Out-Null
Start-Sleep -Seconds 1

$read = Invoke-PcAction @{ action = "pc.files.read"; target = $relativePath }
if ($read.data.content -ne $knownText) {
    throw "The saved file contents did not match the known acceptance text."
}

Invoke-ApprovedPcAction @{
    action = "pc.apps.close"
    parameters = @{ hwnd = [int]$window.hwnd }
} | Out-Null

Write-Output "M4 permission and PC acceptance passed."
Write-Output "Controlled file: $relativePath"
