@echo off
setlocal

set "PROJECT_ROOT=%~dp0"

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if errorlevel 1 (
  start "CTF backend 8000" cmd /d /k call "%PROJECT_ROOT%start-backend-8000.cmd"
) else (
  echo Backend already listening on 127.0.0.1:8000
)

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if errorlevel 1 (
  start "CTF frontend 5173" cmd /d /k call "%PROJECT_ROOT%start-frontend-5173.cmd"
) else (
  echo Frontend already listening on 127.0.0.1:5173
)

echo.
echo Open http://127.0.0.1:5173/challenges
