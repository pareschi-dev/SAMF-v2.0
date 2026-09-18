@echo off
setlocal
cd /d "%~dp0"

REM ===============================
REM SAMF PRO - comandos para iniciar
REM ===============================

where powershell >nul 2>nul
if errorlevel 1 (
    echo PowerShell nao encontrado no PATH.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

python -m pip install --upgrade pip >nul
python -m pip install -r "Interface_Web\backend\requirements.txt"

start "SAMF API" powershell -NoProfile -ExecutionPolicy Bypass -Command "cd /d '%~dp0'; .\.venv\Scripts\python.exe 'Interface_Web\backend\app.py'"
start "SAMF Monitor" powershell -NoProfile -ExecutionPolicy Bypass -Command "cd /d '%~dp0'; .\.venv\Scripts\python.exe 'Scripts\servico_automatico.py'"

ping -n 4 127.0.0.1 >nul

curl -sS http://127.0.0.1:5000/api/auth/status

echo.
echo SAMF inicializado.
echo Acesse: http://127.0.0.1:5000
pause
