<#
.SYNOPSIS
    Valida o requirements.txt do projeto changelog_timeline.

.DESCRIPTION
    1. Verifica se o requirements.txt existe.
    2. Confere, via 'pip', se cada pacote esta instalado na versao exata pinada.
    3. Faz um "dry-run" do pip para garantir que as dependencias sao resolviveis.
    4. Valida que os imports de terceiros usados pelo projeto realmente carregam.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\validate_requirements.ps1

.NOTES
    Rode a partir da pasta changelog_timeline. Codigo de saida 0 = OK, 1 = falha.
#>

[CmdletBinding()]
param(
    [string]$RequirementsFile = "requirements.txt",
    # Comando Python a usar (ajuste para 'py' ou caminho do venv se necessario)
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$script:HasError = $false

function Write-Ok   ($m) { Write-Host "[OK]   $m" -ForegroundColor Green }
function Write-Fail ($m) { Write-Host "[FALHA] $m" -ForegroundColor Red; $script:HasError = $true }
function Write-Info ($m) { Write-Host "[..]   $m" -ForegroundColor Cyan }

# Resolve o caminho relativo a localizacao do script
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$reqPath = Join-Path $scriptDir $RequirementsFile

Write-Host "=== Validacao do $RequirementsFile ===" -ForegroundColor White

# --- 1. Arquivo existe ---
if (-not (Test-Path $reqPath)) {
    Write-Fail "Arquivo nao encontrado: $reqPath"
    exit 1
}
Write-Ok "Arquivo encontrado: $reqPath"

# --- Python disponivel ---
try {
    $pyVersion = & $Python --version 2>&1
    Write-Ok "Python detectado: $pyVersion"
} catch {
    Write-Fail "Python nao encontrado (comando '$Python'). Ajuste o parametro -Python."
    exit 1
}

# --- Le e faz parse do requirements (ignora comentarios e linhas vazias) ---
$lines = Get-Content $reqPath | ForEach-Object { $_.Trim() } |
    Where-Object { $_ -ne "" -and -not $_.StartsWith("#") }

if ($lines.Count -eq 0) {
    Write-Fail "Nenhuma dependencia encontrada no arquivo."
    exit 1
}
Write-Info "Dependencias declaradas: $($lines.Count)"

# --- 2. Cada pacote instalado na versao pinada ---
Write-Host "`n--- Conferindo pacotes instalados ---" -ForegroundColor White

# Monta um dicionario nome->versao a partir do 'pip freeze' (case-insensitive)
$freeze = & $Python -m pip freeze 2>$null
$installed = @{}
foreach ($f in $freeze) {
    if ($f -match "^([A-Za-z0-9_.\-]+)==(.+)$") {
        $installed[$matches[1].ToLower()] = $matches[2]
    }
}

foreach ($line in $lines) {
    if ($line -match "^([A-Za-z0-9_.\-]+)==(.+)$") {
        $name = $matches[1]
        $wantVersion = $matches[2]
        $key = $name.ToLower()
        if ($installed.ContainsKey($key)) {
            $haveVersion = $installed[$key]
            if ($haveVersion -eq $wantVersion) {
                Write-Ok "$name==$wantVersion"
            } else {
                Write-Fail "${name}: esperado $wantVersion, instalado $haveVersion"
            }
        } else {
            Write-Fail "$name nao esta instalado (esperado $wantVersion)"
        }
    } else {
        Write-Info "Linha sem versao pinada (nao validada estritamente): $line"
    }
}

# --- 3. Dry-run do pip: dependencias sao resolviveis? ---
Write-Host "`n--- pip dry-run (resolucao de dependencias) ---" -ForegroundColor White
# stderr do pip nao deve abortar o script; capturamos e avaliamos pelo exit code.
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$dryRun = & $Python -m pip install --dry-run -r $reqPath 2>&1
$dryRunExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP
if ($dryRunExit -eq 0) {
    Write-Ok "pip resolveu todas as dependencias sem conflito."
} else {
    Write-Fail "pip reportou problema ao resolver as dependencias:"
    $dryRun | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkYellow }
}

# --- 4. Imports de terceiros usados pelo projeto ---
Write-Host "`n--- Validando imports do projeto ---" -ForegroundColor White
$importCheck = @"
import importlib, sys
mods = ['fastapi', 'starlette', 'pydantic', 'uvicorn', 'yaml', 'dotenv', 'requests']
falhas = []
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:
        falhas.append(f'{m}: {e}')
if falhas:
    print('IMPORT_FAIL:' + '; '.join(falhas))
    sys.exit(1)
print('IMPORT_OK')
"@
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$importResult = & $Python -c $importCheck 2>&1
$importExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP
if ($importExit -eq 0 -and $importResult -match "IMPORT_OK") {
    Write-Ok "Todos os imports de terceiros carregaram (fastapi, starlette, pydantic, uvicorn, yaml, dotenv, requests)."
} else {
    Write-Fail "Falha ao importar dependencias: $importResult"
}

# --- Resultado final ---
Write-Host "`n=== Resultado ===" -ForegroundColor White
if ($script:HasError) {
    Write-Host "Validacao FALHOU. Verifique os itens marcados como [FALHA]." -ForegroundColor Red
    Write-Host "Dica: instale/atualize com 'pip install -r $RequirementsFile'." -ForegroundColor DarkGray
    exit 1
} else {
    Write-Host "requirements.txt VALIDADO com sucesso." -ForegroundColor Green
    exit 0
}
