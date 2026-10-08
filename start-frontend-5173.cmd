@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "FRONTEND_DIR=%PROJECT_ROOT%frontend"
set "NPM_CMD=D:\nodejs\npm.cmd"

cd /d "%FRONTEND_DIR%"
"%NPM_CMD%" run dev -- --host 127.0.0.1 --port 5173
