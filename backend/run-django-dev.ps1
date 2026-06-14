$ErrorActionPreference = "Continue"
$BackendDir = "E:\c4\6.14\ctf-platform-export-20260315_184335\project-code\backend"
Set-Location -LiteralPath $BackendDir
$env:PYTHONWARNINGS = "ignore"
& ".\.venv-local\Scripts\python.exe" "manage.py" "runserver" "127.0.0.1:8000" "--noreload" *>> "django-dev.log"
