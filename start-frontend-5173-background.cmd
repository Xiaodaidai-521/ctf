@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "FRONTEND_DIR=%PROJECT_ROOT%frontend"
set "NPM_CMD=D:\nodejs\npm.cmd"
set "OUT_LOG=%PROJECT_ROOT%logs\frontend-vite.out.log"
set "ERR_LOG=%PROJECT_ROOT%logs\frontend-vite.err.log"

echo [%date% %time%] Starting frontend on 127.0.0.1:5173>"%OUT_LOG%"
echo [%date% %time%] Starting frontend on 127.0.0.1:5173>"%ERR_LOG%"

cd /d "%FRONTEND_DIR%"
"%NPM_CMD%" run dev -- --host 127.0.0.1 --port 5173 >>"%OUT_LOG%" 2>>"%ERR_LOG%"

echo [%date% %time%] Frontend process exited with code %errorlevel%>>"%ERR_LOG%"
