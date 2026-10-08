@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "BACKEND_DIR=%PROJECT_ROOT%backend"
set "VENV_PYTHON=%BACKEND_DIR%\venv\Scripts\python.exe"
set "LOCAL_VENV_PYTHON=%BACKEND_DIR%\.venv-local\Scripts\python.exe"
set "PYTHON_EXE=python"

if exist "%LOCAL_VENV_PYTHON%" (
  "%LOCAL_VENV_PYTHON%" -c "import django" >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=%LOCAL_VENV_PYTHON%"
)

if "%PYTHON_EXE%"=="python" if exist "%VENV_PYTHON%" (
  "%VENV_PYTHON%" -c "import django" >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=%VENV_PYTHON%"
)

cd /d "%BACKEND_DIR%"
"%PYTHON_EXE%" manage.py migrate --noinput
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" manage.py runserver 127.0.0.1:8000 --noreload
