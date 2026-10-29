param(
    [ValidateSet('up', 'down', 'status', 'logs', 'check')]
    [string]$Action = 'up'
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Invoke-Docker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed (exit $LASTEXITCODE)." }
}

function Invoke-Tools {
    Invoke-Docker run --rm --network "container:$script:Gateway" `
        --mount "type=bind,source=$PSScriptRoot,target=/workspace" `
        -w /workspace python:3.12-alpine python @args
}

if ($Action -eq 'down') { Invoke-Docker compose down; exit }
if ($Action -eq 'status') { Invoke-Docker compose ps; exit }
if ($Action -eq 'logs') { Invoke-Docker compose logs --tail 80 web worker gateway; exit }

Invoke-Docker info --format '{{.OSType}}'
if ($Action -eq 'up') {
    Invoke-Docker compose up -d
    Invoke-Docker compose wait catalog
}
$script:Gateway = & docker compose ps -q gateway
if ($LASTEXITCODE -ne 0 -or -not $script:Gateway) { throw 'Gateway is not running.' }
$script:Gateway = ($script:Gateway -join '').Trim()
Invoke-Tools poc.py check
if ($Action -eq 'up') {
    Write-Host 'Portal: https://localhost:8443'
    Write-Host 'Credentials: .env (KEYGEN_ADMIN_EMAIL / KEYGEN_ADMIN_PASSWORD)'
    Write-Host 'Local CA: .runtime/root.crt'
}
