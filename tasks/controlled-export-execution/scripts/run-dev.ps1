$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Create .venv and install requirements.txt before starting the service.'
}

Push-Location $projectRoot
try {
    & $python manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python manage.py runserver 127.0.0.1:8010
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
