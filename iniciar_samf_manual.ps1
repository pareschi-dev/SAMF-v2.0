$ErrorActionPreference = 'Stop'
$Raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Raiz

Write-Host "==============================" -ForegroundColor Cyan
Write-Host "SAMF - Inicializacao manual" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan
Write-Host ""

# Corrige execucao de scripts no PowerShell da sessao atual
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

if (-not (Test-Path (Join-Path $Raiz '.venv\Scripts\Activate.ps1'))) {
    Write-Host "Ambiente virtual .venv nao encontrado. Criando..." -ForegroundColor Yellow
    python -m venv .venv
}

Write-Host "Ativando ambiente virtual..." -ForegroundColor Yellow
. (Join-Path $Raiz '.venv\Scripts\Activate.ps1')

Write-Host "Instalando dependencias..." -ForegroundColor Yellow
python -m pip install --upgrade pip
python -m pip install -r "Interface_Web\backend\requirements.txt"
python -m pip install -r "Scripts\requirements.txt"

Write-Host "Iniciando API e servico automatico..." -ForegroundColor Yellow
$api = Start-Process -FilePath (Join-Path $Raiz '.venv\Scripts\python.exe') -ArgumentList @('Interface_Web\backend\app.py') -WorkingDirectory $Raiz -PassThru -WindowStyle Normal
$monitor = Start-Process -FilePath (Join-Path $Raiz '.venv\Scripts\python.exe') -ArgumentList @('Scripts\servico_automatico.py') -WorkingDirectory $Raiz -PassThru -WindowStyle Normal

Write-Host "Aguardando a API responder..." -ForegroundColor Yellow
for ($i = 1; $i -le 40; $i++) {
    try {
        $status = Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/auth/status' -Method Get -TimeoutSec 5
        if ($status) {
            Write-Host "API respondendo em http://127.0.0.1:5000" -ForegroundColor Green
            break
        }
    }
    catch {
        Start-Sleep -Seconds 1
    }
}

Write-Host ""
Write-Host "SAMF iniciado com sucesso." -ForegroundColor Green
Write-Host "Acesse: http://127.0.0.1:5000" -ForegroundColor Green
Write-Host ""
Read-Host "Pressione Enter para encerrar este terminal"
