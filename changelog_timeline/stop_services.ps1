<#
.SYNOPSIS
    Para (mata) somente os processos do servidor DESTE projeto (changelog_timeline).

.DESCRIPTION
    Identifica os processos que pertencem a este projeto de forma precisa,
    inspecionando a linha de comando e o diretorio de trabalho de cada
    processo Python. Um processo so e considerado alvo quando:

      - roda uvicorn com 'api:app', E
      - sua linha de comando ou seu diretorio atual apontam para a pasta
        deste projeto (onde este script esta: changelog_timeline).

    Portas so sao usadas como confirmacao: o PID que escuta a porta so e
    finalizado se ja tiver sido identificado como pertencente ao projeto.
    Assim, um outro servidor de terceiros usando a mesma porta NAO e afetado.

.PARAMETER Ports
    Portas verificadas para confirmar/priorizar alvos. Padrao: 8000..8013.

.PARAMETER WhatIf
    Apenas lista o que seria finalizado, sem matar nada.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\stop_services.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\stop_services.ps1 -WhatIf

.NOTES
    Rode a partir da pasta changelog_timeline (ou de qualquer lugar; o script
    resolve o proprio diretorio). Codigo de saida sempre 0 quando concluido.
#>

[CmdletBinding()]
param(
    [int[]]$Ports = (8000..8013),
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

function Write-Ok   ($m) { Write-Host "[OK]   $m" -ForegroundColor Green }
function Write-Info ($m) { Write-Host "[..]   $m" -ForegroundColor Cyan }
function Write-Warn ($m) { Write-Host "[!]    $m" -ForegroundColor Yellow }

# Diretorio deste projeto = pasta onde o script reside (normalizado)
$projectDir = (Split-Path -Parent $MyInvocation.MyCommand.Path).TrimEnd('\')
$projectDirLower = $projectDir.ToLower()

Write-Host "=== Parando servicos do projeto ===" -ForegroundColor White
Write-Info "Diretorio do projeto: $projectDir"

# Guarda motivo de cada PID selecionado (para relatorio)
$targets = @{}

function Add-Target([int]$procId, [string]$reason) {
    if ($procId -le 0) { return }
    if (-not $targets.ContainsKey($procId)) { $targets[$procId] = $reason }
}

# --- 1. Processos Python cujo comando/CWD pertencem a este projeto ---
Write-Info "Procurando processos do projeto (uvicorn api:app + caminho do projeto)..."
$cim = $null
try {
    $cim = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction Stop
} catch {
    Write-Warn "Nao foi possivel inspecionar processos (CIM): $($_.Exception.Message)"
}

# Guarda os candidatos 'uvicorn api:app' (PID -> linha de comando) para
# cruzar depois com as portas do projeto.
$appServers = @{}

foreach ($p in $cim) {
    $cmd = if ($p.CommandLine) { $p.CommandLine.ToLower() } else { "" }
    if (-not $cmd) { continue }

    $isAppServer = ($cmd -match "uvicorn" -and $cmd -match "api:app")
    if (-not $isAppServer) { continue }

    $appServers[[int]$p.ProcessId] = $cmd

    # Confirmacao direta: o caminho do projeto aparece na linha de comando.
    if ($cmd.Contains($projectDirLower)) {
        Add-Target ([int]$p.ProcessId) "uvicorn api:app (caminho do projeto no comando)"
        Write-Info "  match PID $($p.ProcessId) (caminho do projeto na linha de comando)"
    }
}

# --- 2. Portas do projeto: confirmam quem e 'uvicorn api:app' deste projeto ---
# Um processo que roda 'uvicorn api:app' E escuta numa porta do projeto e,
# com seguranca, o servidor deste projeto (api:app e o entrypoint local).
Write-Info "Conferindo portas do projeto: $($Ports -join ', ')"
foreach ($port in $Ports) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            $procId = [int]$c.OwningProcess
            if ($procId -le 0) { continue }
            if ($targets.ContainsKey($procId)) {
                Write-Info "  porta $port confirmada no PID $procId (do projeto)"
            } elseif ($appServers.ContainsKey($procId)) {
                Add-Target $procId "uvicorn api:app na porta $port do projeto"
                Write-Info "  match PID $procId (uvicorn api:app escutando porta $port)"
            } else {
                $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
                $name = if ($proc) { $proc.ProcessName } else { "desconhecido" }
                Write-Warn "  porta $port em uso pelo PID $procId ($name) - NAO e o servidor do projeto, sera ignorado"
            }
        }
    } catch {
        Write-Warn "Falha ao consultar porta ${port}: $($_.Exception.Message)"
    }
}

# --- Resultado da coleta ---
if ($targets.Count -eq 0) {
    Write-Ok "Nenhum processo deste projeto em execucao. Nada a fazer."
    exit 0
}

Write-Host "`n--- Processos do projeto ($($targets.Count)) ---" -ForegroundColor White
foreach ($procId in $targets.Keys) {
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    $name = if ($proc) { $proc.ProcessName } else { "(ja finalizado)" }
    Write-Host ("    PID {0,-6} {1,-10} [{2}]" -f $procId, $name, $targets[$procId])
}

if ($WhatIf) {
    Write-Warn "`nModo -WhatIf: nenhum processo foi finalizado."
    exit 0
}

# --- Finaliza os processos ---
Write-Host "`n--- Finalizando ---" -ForegroundColor White
$killed = 0
foreach ($procId in @($targets.Keys)) {
    try {
        Stop-Process -Id $procId -Force -ErrorAction Stop
        Write-Ok "PID $procId finalizado."
        $killed++
    } catch {
        Write-Warn "Nao foi possivel finalizar PID ${procId}: $($_.Exception.Message)"
    }
}

Write-Host "`n=== Resultado ===" -ForegroundColor White
Write-Ok "$killed processo(s) do projeto finalizado(s)."
exit 0
