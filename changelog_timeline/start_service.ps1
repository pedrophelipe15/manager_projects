<#
.SYNOPSIS
    Sobe o servidor DESTE projeto (changelog_timeline) da forma mais simples.

.DESCRIPTION
    Equivalente a rodar no terminal:

        python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload

    O script apenas:
      - resolve o proprio diretorio (roda de qualquer lugar);
      - usa o Python do venv local (.venv) se existir, senao o Python do PATH;
      - confere se o uvicorn esta instalado (avisa como instalar se faltar);
      - inicia o servidor em primeiro plano (Ctrl+C encerra).

    Nao mata processos, nao altera arquivos, nao mexe em git. Para PARAR o
    servidor, use stop_services.ps1 (ou Ctrl+C nesta janela).

.PARAMETER Port
    Porta do servidor. Padrao: 8000 (mesma usada pelo stop_services.ps1).

.PARAMETER BindHost
    Endereco de bind. Padrao: 0.0.0.0 (aceita conexoes da rede local).
    Use 127.0.0.1 para restringir ao proprio computador.

.PARAMETER NoReload
    Desativa o auto-reload (util para uso "producao local" / mais estavel).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\start_service.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\start_service.ps1 -Port 8080 -BindHost 127.0.0.1

.NOTES
    Rode a partir da pasta changelog_timeline (ou de qualquer lugar; o script
    resolve o proprio diretorio). Acesso: http://localhost:<Port>
#>

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [string]$BindHost = "0.0.0.0",
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"

function Write-Ok   ($m) { Write-Host "[OK]   $m" -ForegroundColor Green }
function Write-Info ($m) { Write-Host "[..]   $m" -ForegroundColor Cyan }
function Write-Warn ($m) { Write-Host "[!]    $m" -ForegroundColor Yellow }
function Write-Fail ($m) { Write-Host "[FALHA] $m" -ForegroundColor Red }

# Diretorio deste projeto = pasta onde o script reside
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== Iniciando servidor do projeto ===" -ForegroundColor White
Write-Info "Diretorio do projeto: $projectDir"

# --- Verifica que api.py existe (garante que estamos no lugar certo) ---
$apiFile = Join-Path $projectDir "api.py"
if (-not (Test-Path $apiFile)) {
    Write-Fail "api.py nao encontrado em $projectDir. Rode o script de dentro do projeto."
    exit 1
}

# --- Escolhe o Python: venv local (.venv) se existir, senao o do PATH ---
$venvPython = Join-Path $projectDir ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
    Write-Ok "Usando Python do venv: .venv"
} else {
    $python = "python"
    Write-Info "venv (.venv) nao encontrado. Usando Python do PATH."
}

# --- Confere se o Python responde ---
try {
    $pyVersion = & $python --version 2>&1
    Write-Ok "Python detectado: $pyVersion"
} catch {
    Write-Fail "Python nao encontrado. Instale o Python 3.12+ ou crie o venv (.venv)."
    exit 1
}

# --- Confere se o uvicorn esta instalado (dependencia minima para subir) ---
& $python -c "import uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Fail "uvicorn nao esta instalado neste Python."
    Write-Info "Instale as dependencias com:"
    Write-Host  "    $python -m pip install -r requirements.txt" -ForegroundColor DarkGray
    exit 1
}
Write-Ok "uvicorn disponivel."

# --- Monta os argumentos e sobe o servidor ---
$uvicornArgs = @("-m", "uvicorn", "api:app", "--host", $BindHost, "--port", "$Port")
if (-not $NoReload) { $uvicornArgs += "--reload" }

Write-Host ""
Write-Ok   "Servidor subindo em http://localhost:$Port  (Ctrl+C para parar)"
Write-Info "Comando: $python $($uvicornArgs -join ' ')"
Write-Host ""

# Executa em primeiro plano na pasta do projeto (igual rodar no terminal).
Push-Location $projectDir
try {
    & $python @uvicornArgs
} finally {
    Pop-Location
}
