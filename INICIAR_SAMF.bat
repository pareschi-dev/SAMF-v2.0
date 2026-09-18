@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo        SAMF PRO - INICIALIZACAO
echo ========================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0RODAR_SAMF_COMPLETO.ps1"

if errorlevel 1 (
    echo.
    echo ERRO: o SAMF nao foi iniciado.
    pause
    exit /b 1
)

echo.
echo SAMF iniciado com sucesso.
echo Acesse: http://127.0.0.1:5000
pause
