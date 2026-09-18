# SAMF PRO - inicializacao completa no Windows PowerShell
# Execute na raiz do projeto:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\RODAR_SAMF_COMPLETO.ps1
#
# Para somente preparar o ambiente, sem iniciar os servicos:
#   .\RODAR_SAMF_COMPLETO.ps1 -PrepararApenas
#
# Para recriar/popular tabelas e dados padrao do SQLite (altera dados de referencia):
#   .\RODAR_SAMF_COMPLETO.ps1 -InicializarBanco

[CmdletBinding()]
param(
    [switch]$PrepararApenas,
    [switch]$InicializarBanco,
    [int]$Porta = 5000
)

$ErrorActionPreference = 'Stop'
$Raiz = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ((Split-Path -Leaf $PSScriptRoot) -eq 'Backups') {
    $Raiz = (Resolve-Path $PSScriptRoot).Path
}
Set-Location $Raiz

$Python = Join-Path $Raiz '.venv\Scripts\python.exe'
$Pip = Join-Path $Raiz '.venv\Scripts\pip.exe'
$Backend = Join-Path $Raiz 'Interface_Web\backend\app.py'
$Monitor = Join-Path $Raiz 'Scripts\servico_automatico.py'
$Requirements = Join-Path $Raiz 'Interface_Web\backend\requirements.txt'
$Pastas = @('Backups', 'Compartilhadas', 'Duplicados', 'Erro', 'Exclusivas', 'Faturas_entrada', 'Processados', 'Relatorios', 'Revisao', 'Processamento')

Write-Host '=== SAMF PRO: preparacao do ambiente ===' -ForegroundColor Cyan

if (-not (Test-Path $Python)) {
    Write-Host 'Criando ambiente virtual .venv...'
    python -m venv .venv
}

Write-Host 'Atualizando pip e instalando dependencias...'
& $Python -m pip install --upgrade pip
& $Pip install -r $Requirements

foreach ($Pasta in $Pastas) {
    $Caminho = Join-Path $Raiz $Pasta
    New-Item -ItemType Directory -Force -Path $Caminho | Out-Null
}

if (-not (Test-Path (Join-Path $Raiz 'Configuracoes\samf_config.json'))) {
    throw 'Configuracoes\samf_config.json nao foi encontrado.'
}

if ($InicializarBanco) {
    Write-Host 'Inicializando e populando o banco SQLite...'
    & $Python (Join-Path $Raiz 'Scripts\seed_db.py')
}
else {
    Write-Host 'Banco preservado. Use -InicializarBanco somente quando desejar recriar os dados padrao.' -ForegroundColor Yellow
}

Write-Host 'Validando sintaxe dos pontos de entrada...'
& $Python -m py_compile $Backend $Monitor

if ($PrepararApenas) {
    Write-Host 'Preparacao concluida.' -ForegroundColor Green
    exit 0
}

Write-Host '=== SAMF PRO: iniciando servicos ===' -ForegroundColor Cyan
$env:PYTHONPATH = Join-Path $Raiz 'Scripts'
$env:FLASK_PORT = [string]$Porta

$ApiExistente = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -like '*Interface_Web*backend*app.py*' }
if ($ApiExistente) {
    Write-Host 'API ja esta em execucao; nenhum novo processo foi criado.' -ForegroundColor Yellow
}
else {
    Start-Process -FilePath $Python -ArgumentList @($Backend) -WorkingDirectory $Raiz -WindowStyle Normal
    Write-Host "API iniciada em http://127.0.0.1:$Porta"
}

$MonitorExistente = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -like '*Scripts*servico_automatico.py*' }
if ($MonitorExistente) {
    Write-Host 'Monitor automatico ja esta em execucao; nenhum novo processo foi criado.' -ForegroundColor Yellow
}
else {
    Start-Process -FilePath $Python -ArgumentList @($Monitor) -WorkingDirectory $Raiz -WindowStyle Normal
    Write-Host 'Monitor automatico iniciado.'
}

Write-Host 'Aguardando a API responder...'
$Uri = "http://127.0.0.1:$Porta/api/auth/status"
$Saude = $null
for ($Tentativa = 1; $Tentativa -le 15; $Tentativa++) {
    try {
        $Saude = Invoke-RestMethod -Uri $Uri -Method Get
        break
    }
    catch {
    }
}

if (-not $Saude -or $Saude.status -ne 'OK') {
    Write-Warning "API iniciou, mas ainda nao respondeu ao healthcheck: $Uri"
    Write-Host 'Verifique novamente com Invoke-RestMethod quando o Flask terminar o reload.' -ForegroundColor Yellow
}
else {
    Write-Host "Healthcheck OK: $Uri" -ForegroundColor Green
}

Write-Host "Interface: http://127.0.0.1:$Porta" -ForegroundColor Green
