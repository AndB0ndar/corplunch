# Run from any directory. Foreground API; Ctrl+C stops the demo server.
$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
$priorBind = $env:DB_BIND
try {
    $env:DB_BIND = '127.0.0.1:15433'
    $fixtureApi = (Resolve-Path tests/defense_api.py).Path
    docker compose -p corplunch-defense --env-file tests/.env.test run --rm --build --publish 127.0.0.1:18001:8000 --volume "${fixtureApi}:/app/defense_api.py:ro" --entrypoint python api /app/defense_api.py
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось запустить стенд защиты' }
} finally {
    $env:DB_BIND = $priorBind
    Pop-Location
}
