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
    # Credentials remain on the host and survive container recreation.
    Invoke-Docker run --rm `
        --mount "type=bind,source=$PSScriptRoot,target=/workspace" `
        -w /workspace python:3.12-alpine python -c 'import poc; poc.prepare_environment()'
    Invoke-Docker compose config --quiet
    Invoke-Docker compose up -d --wait postgres redis
    $schema = & docker compose exec -T postgres psql -U keygen -d keygen -tAc "SELECT to_regclass('public.accounts') IS NOT NULL"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect database schema.' }
    if (($schema -join '').Trim() -eq 'f') {
        # Upstream setup output contains credentials; never print it to the terminal.
        $ErrorActionPreference = 'Continue'
        try {
            & docker compose --profile setup run --rm -T setup *> .runtime/setup.log
            $setupExit = $LASTEXITCODE
        } finally { $ErrorActionPreference = 'Stop' }
        if ($setupExit -ne 0) { throw 'Setup failed. Inspect .runtime/setup.log locally (contains secrets).' }
    } else {
        $count = & docker compose exec -T postgres psql -U keygen -d keygen -tAc 'SELECT count(*) FROM accounts'
        if ($LASTEXITCODE -ne 0 -or [int](($count -join '').Trim()) -eq 0) {
            throw 'Schema exists without a usable account. Inspect .runtime/setup.log before recovery.'
        }
    }
    Invoke-Docker compose build portal
    Invoke-Docker compose up -d --wait --wait-timeout 180 web worker portal gateway
    Invoke-Docker compose cp gateway:/data/caddy/pki/authorities/local/root.crt .runtime/root.crt
}
$script:Gateway = & docker compose ps -q gateway
if ($LASTEXITCODE -ne 0 -or -not $script:Gateway) { throw 'Gateway is not running.' }
$script:Gateway = ($script:Gateway -join '').Trim()
Invoke-Tools poc.py check
if ($Action -eq 'up') {
    Invoke-Tools product.py init
    Write-Host 'Portal: https://localhost:8443'
    Write-Host 'Credentials: .env (KEYGEN_ADMIN_EMAIL / KEYGEN_ADMIN_PASSWORD)'
    Write-Host 'Local CA: .runtime/root.crt'
}
