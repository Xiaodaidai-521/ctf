$ErrorActionPreference = "Continue"
$BackendDir = $PSScriptRoot
Set-Location -LiteralPath $BackendDir
$env:PYTHONWARNINGS = "ignore"

$PythonExe = Join-Path $BackendDir "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
  $PythonExe = "python"
}

& $PythonExe "manage.py" "runserver" "127.0.0.1:8000" "--noreload" *>> "django-dev.log"
