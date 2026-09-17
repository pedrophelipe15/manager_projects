# DATASHEET - Changelog Timeline

> **Versao:** v2.1.0 · **Status:** produtivo · **Atualizado:** 2026-09-15
>
> A v2.0.0 consolidou uma revisao de UX (4 ondas) que adicionou a tela **Minha Visao**
> (home), a tela **Compromisso de Prazo** (Wave 5 / due date slippage), um **design
> system** compartilhado (`tokens.css`, `nav.*`, `ui.*`, `context.js`) e uma navegacao
> unica agrupada por pergunta.
>
> A **v2.1.0** aprofundou a home Minha Visao: indicadores clicaveis abrem um **painel
> de detalhe inline** (ordenacao, filtros dropdown-checkbox cascateantes, paginacao,
> coluna Due Date), o seletor de projetos ganhou "Selecionar todos" + "Limpar filtro",
> e o commitment score tem um **tooltip explicativo** que mostra a conta. O tooltip
> virou componente reutilizavel do design system (`CTUI.infoTooltip` + `.ct-tip`).
> Ver a secao *Revisao de UX* ao final e o guia `docs/GUIA-DESIGN-DASHBOARD.md`.

## Visao Geral

O **Changelog Timeline** e um sistema de gestao de fluxo e metricas que extrai dados do Jira (issues + changelog de transicoes de status), persiste em banco SQLite local e oferece:

- **Minha Visao** (home) — visao consolidada dos projetos do gestor; indicadores clicaveis abrem detalhe inline
- **Compromisso de Prazo (Wave 5)** — commitment score + reprogramacoes de due date (a equipe cumpre prazo ou empurra a data?)
- **Dashboard operacional** — KPIs de ritmo (Done semanal, Em andamento, Bloqueado, paradas)
- **Wave 1: Gargalo e Fluxo** — percentis, flow efficiency, CFD, aging WIP, timeline semanal
- **Wave 2: Previsibilidade** — throughput, Monte Carlo forecast, aging backlog
- **Wave 3: Pessoas e Qualidade** — WIP por pessoa, distribuicao de carga, handoffs, retrabalho
- **Wave 4: Portfolio** — epic health, benchmarking cross-project, throughput consolidado
- **Maturidade** — report de acoes pendentes por responsavel
- **Inconsistencias** — validacoes de dados (due date, assignee, metricas)
- **Insights** — 24 regras de diagnostico automatico (arquivado da navegacao; arquivos preservados)

---

## Arquitetura

```
Jira API (Cloud)
     |
     | REST API v3 (paginado, retry robusto com backoff)
     v
export_jira.py (extrator) ---> output/{PROJECT_KEY}/ (JSONL)
     |                          [expand=changelog, cache hit/miss, --skip-test]
     v
ingest_to_db.py (ingestao) ---> issues.db (SQLite)
     |                               |
     | metrics/base.py               | metrics/wave1_bottleneck/
     | (lead time, cycle time)       | (tempo por status, percentis, flow eff, CFD, aging WIP)
     v                               v
api.py (FastAPI + uvicorn) ---> Browser (HTML/JS/CSS)
     |
     ├── /dashboard.html    (KPIs operacionais + tabela)
     ├── /wave1.html        (Gargalo e Fluxo)
     ├── /wave2.html        (Previsibilidade + Monte Carlo)
     ├── /wave3.html        (Pessoas e Qualidade)
     ├── /wave4.html        (Portfolio cross-project)
     ├── /insights.html     (Diagnostico automatico + alertas)
     ├── /inconsistencies   (Validacoes de dados)
     └── /settings.html     (Configuracoes)
```

### Componentes

| Componente | Arquivo | Funcao |
|-----------|---------|--------|
| API Backend | `api.py` | FastAPI servindo endpoints REST + arquivos estaticos |
| Extrator Jira | `exporter_jira/export_jira.py` | Extrai issues e changelogs do Jira via API |
| Cliente Jira | `exporter_jira/jira_client.py` | Conexao, autenticacao, paginacao, retry |
| Mapper | `exporter_jira/jira_mapper.py` | Transforma payload bruto Jira em formato flat |
| Ingestao | `ingest_to_db.py` | Le JSONL, popula SQLite, orquestra calculo de metricas |
| Metricas Base | `metrics/base.py` | Calcula lead time e cycle time |
| Wave 1 | `metrics/wave1_bottleneck/` | 5 sub-metricas de gargalo e fluxo |
| Pipeline | `run_pipeline.py` | Orquestrador CLI (legado, funcional) |
| Dashboard | `dashboard.html/js/css` | KPIs operacionais (Done semanal, WIP, paradas) + tabela de issues |
| Wave 1 UI | `wave1.html/js/css` | Metricas avancadas de gargalo |
| Timeline | `index.html`, `app.js`, `style.css` | Timeline visual de uma issue especifica |
| Inconsistencias | `inconsistencies.html/js/css` | Validacoes de dados por projeto |
| Configuracoes | `settings.html/js/css` | UI de gestao: projetos, blacklist, expurgo |
| Configuracao | `projects.yaml` | Definicao de projetos e pipelines |
| Banco | `issues.db` | SQLite com issues, changelogs, metrics, configs |

---

## Como Subir o Projeto

### Pre-requisitos

- Python 3.12+
- Pacotes: `fastapi`, `uvicorn`, `starlette`, `pydantic`, `pyyaml`, `python-dotenv`, `requests` (ver `requirements.txt`)
- Arquivo `.env` em `exporter_jira/` com credenciais Jira

### Instalacao

```powershell
cd C:\Pedro_Github\manager_projects\changelog_timeline
pip install -r requirements.txt
```

### Subir o Servidor

```powershell
cd C:\Pedro_Github\manager_projects\changelog_timeline
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Acesso: `http://localhost:8000`

---

## Navegacao

A partir da v2.0.0 a nav e **injetada por `nav.js`** (estilo em `nav.css`) num placeholder
`<nav id="main-nav" class="nav-bar">`, substituindo as barras duplicadas por pagina. E
**agrupada por pergunta do gestor** (a ordem/abas vivem no array `GROUPS` de `nav.js`):

| Grupo | Abas | Pergunta |
|-------|------|----------|
| Minha Visao | Minha Visao | O que preciso fazer hoje? |
| Prazos | Compromisso, Previsibilidade | Vamos entregar? |
| Pessoas | Maturidade, Pessoas | Quem precisa de ajuda? |
| Fluxo | Gargalo e Fluxo, Portfolio, Dashboard | Onde trava? |
| Hierarquia | Hierarquia | Como esta a iniciativa? |
| Dados | Inconsistencias, Configuracoes | Da pra confiar no numero? |

Insights foi **removida da nav** (arquivada em 21/08/2026); o arquivo continua acessivel por URL direta.

---

## Paginas

| URL | Descricao |
|-----|-----------|
| `/minha-visao.html` | **Home**: cards por projeto — commitment score (com tooltip da conta), indicadores clicaveis que abrem painel de detalhe inline (ordenavel, filtravel, paginado) |
| `/compromisso.html` | **Compromisso de Prazo (Wave 5)**: score, por assignee, issues com prazo empurrado |
| `/dashboard.html` | Dashboard operacional: KPIs (Done semanal, Em andamento, Bloqueado, Paradas >7d) + tabela |
| `/wave1.html` | Wave 1: Metricas de gargalo e fluxo (percentis, CFD, aging WIP) |
| `/wave2.html` | Wave 2: Previsibilidade (throughput, Monte Carlo forecast, aging backlog) |
| `/wave3.html` | Wave 3: Pessoas e Qualidade (WIP, distribuicao, handoff, retrabalho) |
| `/wave4.html` | Wave 4: Portfolio (epic health, benchmarking, throughput consolidado) |
| `/maturidade.html` | Report de acoes pendentes por responsavel |
| `/insights.html` | Insights: Diagnostico automatico (fora da nav; acessivel por URL) |
| `/?issue=KEY` | Timeline completa de uma issue (ex: `/?issue=BKA-6632`) |
| `/inconsistencies.html` | Validacoes de dados por projeto |
| `/settings.html` | Configuracoes: projetos, blacklist, expurgo |

---

## Metricas Avancadas — Sistema de Waves

O projeto utiliza um sistema modular de metricas organizado por **Waves** (fases de implementacao). Cada wave agrupa sub-metricas relacionadas.

### Arquitetura de Metricas

```
metrics/
├── __init__.py
├── base.py                          # Lead Time + Cycle Time (metricas fundamentais)
├── changelog_cache.py               # Cache compartilhado de changelogs de status
├── wave1_bottleneck/                # Wave 1: Gargalo e Fluxo
│   ├── __init__.py                  # run_wave1() — orquestra as 5 sub-metricas
│   ├── time_per_status.py           # 1.1 Tempo medio/P85 por status
│   ├── percentiles.py               # 1.2 Percentis de Lead/Cycle Time
│   ├── flow_efficiency.py           # 1.3 Flow Efficiency
│   ├── cfd.py                       # 1.4 Cumulative Flow Diagram
│   └── aging_wip.py                 # 1.5 Aging WIP Report
├── wave2_predictability/            # Wave 2: Previsibilidade
│   ├── __init__.py
│   ├── throughput.py                # Throughput semanal (total + por tipo)
│   ├── forecast.py                  # Monte Carlo Forecast + open parents
│   └── aging_backlog.py             # Issues inativas
├── wave3_people/                    # Wave 3: Pessoas e Qualidade
│   ├── __init__.py
│   ├── wip.py                       # WIP por pessoa
│   ├── workload.py                  # Distribuicao de carga (Gini + bus factor)
│   ├── handoff.py                   # Handoff time
│   └── rework.py                    # Retrabalho
├── wave4_portfolio/                 # Wave 4: Cross-time e Portfolio
│   ├── __init__.py
│   ├── epic_health.py               # Saude de issues-pai
│   ├── benchmarking.py              # Comparacao entre projetos
│   └── cross_project.py             # Throughput consolidado
└── insights/                        # Engine de diagnostico automatico
    ├── __init__.py                  # run_insights() entry point
    ├── engine.py                    # InsightsEngine (registro + execucao)
    ├── rules_flow.py                # 8 regras de fluxo
    ├── rules_throughput.py          # 4 regras de previsibilidade
    ├── rules_people.py              # 4 regras de pessoas
    ├── rules_portfolio.py           # 3 regras de portfolio
    └── rules_alerts.py              # 5 alertas proativos
```

### Resumo de Waves

| Wave | Tema | Pagina | Regras Insight |
|------|------|--------|---------------|
| 1 | Gargalo e Fluxo | `/wave1.html` | 8 (fluxo) |
| 2 | Previsibilidade | `/wave2.html` | 4 (throughput) |
| 3 | Pessoas e Qualidade | `/wave3.html` | 4 (pessoas) |
| 4 | Cross-time e Portfolio | `/wave4.html` | 3 (portfolio) |
| — | Alertas Proativos | `/insights.html` | 5 (alertas) |
| **Total** | | | **24 regras** |

### Contrato dos modulos

Cada modulo de metrica segue o padrao:

```python
def setup_table(conn):       # Cria tabela se nao existir
def calculate_X(conn, only_keys=None) -> int:  # Calcula e persiste. Retorna count.
```

### Quando sao calculadas

Na ingestao (`ingest_to_db.py`), apos inserir issues e changelogs:

```
[4/5] Metricas base (lead/cycle time)  → metrics/base.py
[5/5] Wave 1 (gargalo e fluxo)         → metrics/wave1_bottleneck/
```

### Tabelas de metricas

| Tabela | Wave | Descricao |
|--------|------|-----------|
| `metrics` | Base | Lead time e cycle time por issue |
| `metrics_per_status` | 1.1 | Tempo gasto em cada status por issue (intervalos) |
| `metrics_percentiles` | 1.2 | P50/P70/P85/P95 de lead e cycle por projeto |
| `metrics_flow` | 1.3 | Work time, wait time e flow efficiency por issue |
| `metrics_cfd` | 1.4 | Snapshot diario de contagem por status (90 dias) |

---

## Wave 1: Gargalo e Fluxo

### 1.1 Tempo por Status

Calcula quanto tempo cada issue ficou em cada status. Identifica gargalo pelo P85.

- **Tabela:** `metrics_per_status` (issue_key, project_key, status, duration_ms, entered_at, exited_at)
- **Endpoint:** `GET /api/metrics/wave1/time-per-status?project_key=X`
- **Filtro de issues:** Apenas issues Done (ciclo completo)
- **Filtro de status exibidos:** Exclui status de espera que nao representam etapa ativa: `Open, Backlog, To do, Canceled, Reject, Removed, Done`

#### Como o status e coletado

O valor do status vem do **changelog do Jira** (campo `to_value` das transicoes). Toda vez que alguem move uma issue no board do Jira, a transicao e registrada:

```
from_value: "In Progress"
to_value: "Blocked"  
event_date: "2026-08-05T10:00:00"
```

O sistema registra TODAS as transicoes na tabela `parsed_changelogs`.

#### Como o tempo e calculado

Para cada issue, percorre as transicoes cronologicamente e calcula:

```
duracao_em_status = timestamp_da_saida - timestamp_da_entrada
```

Exemplo concreto:
```
Issue BKA-100:
  01/08 10:00 → Entrou em "In Progress"
  05/08 10:00 → Saiu de "In Progress" (foi para "Blocked")
  Resultado: ficou 4 dias em "In Progress"
  
  05/08 10:00 → Entrou em "Blocked"
  07/08 14:00 → Saiu de "Blocked" (foi para "Done")
  Resultado: ficou 2.2 dias em "Blocked"
```

Cada intervalo e gravado como um registro em `metrics_per_status`. O endpoint agrega por status e calcula media/percentis.

#### Fluxo completo do dado

```
Jira Board (usuario move card)
  → Jira API changelog (/rest/api/3/issue/{key}/changelog)
  → export_jira.py (extrai e grava em changelogs.jsonl)
  → ingest_to_db.py (grava em parsed_changelogs)
  → time_per_status.py (calcula duracao por status, grava em metrics_per_status)
  → api.py endpoint (agrupa, filtra, calcula percentis)
  → wave1.js (renderiza tabela com barras proporcionais)
```

#### Status exibidos vs ocultos

O endpoint filtra status que nao representam trabalho ativo. Configuravel em `api.py`:

```python
EXCLUDED_STATUSES = {"Open", "Backlog", "To do", "Canceled", "Reject", "Removed", "Done"}
```

Status customizados do Jira (ex: "Refinement", "Waiting for Delivery", "Review", "Test") aparecem automaticamente se a issue passar por eles.

### 1.2 Percentis

P50, P70, P85, P95 de Lead Time e Cycle Time por projeto.

- **Tabela:** `metrics_percentiles` (project_key, metric_type, p50/p70/p85/p95, avg, count)
- **Logica:** Agrega da tabela `metrics` existente
- **Endpoint:** `GET /api/metrics/wave1/percentiles?project_key=X`

### 1.3 Flow Efficiency

Percentual do lead time em que a issue estava sendo ativamente trabalhada.

```
flow_efficiency = tempo_em_In_Progress / lead_time * 100
```

- **Tabela:** `metrics_flow` (issue_key, project_key, work_time_ms, wait_time_ms, lead_time_ms, flow_efficiency)
- **Logica:** Conta apenas tempo em "In Progress" (sem Blocked/Test/Waiting) vs lead time total
- **Endpoint:** `GET /api/metrics/wave1/flow-efficiency?project_key=X`
- **Referencia:** <15% baixa | 15-25% tipica | 25-40% boa | >40% excelente
- **UI:** Integrado na secao de Percentis com semaforo de cores (vermelho/amarelo/ciano/verde)

### 1.4 Cumulative Flow Diagram (CFD)

Snapshot diario: quantas issues estavam em cada status por dia (ultimos 90 dias).

- **Tabela:** `metrics_cfd` (project_key, snapshot_date, status, count)
- **Logica:** Reconstroi estado de cada issue por dia a partir do changelog
- **Endpoint:** `GET /api/metrics/wave1/cfd?project_key=X`
- **Visualizacao:** Grafico de area empilhada (Chart.js line stacked)
- **"Barrigas"** (acumulo crescente numa coluna) = gargalo

### 1.5 Aging WIP Report

Issues ativas com cycle time acima do P85 historico — precisam de atencao.

- **Sem tabela propria** — calcula on-the-fly (volume baixo: so issues ativas)
- **Logica:** Compara `metrics.cycle_time_ms` de issues ativas vs `metrics_percentiles.p85_ms`
- **Endpoint:** `GET /api/metrics/wave1/aging-wip?project_key=X`

### Frontend Wave 1

- **Pagina:** `/wave1.html`
- **JS:** `wave1.js` — carrega 5 endpoints em paralelo, renderiza seções
- **CSS:** `wave1.css`
- **Componentes visuais:**
  - Percentis + Flow Efficiency unificados (com descricoes inline e semaforo)
  - Timeline semanal de percentis (grafico de linha P50/P85 Lead e Cycle)
  - Tabela de gargalo com barras proporcionais (P85 descendente)
  - Grafico CFD (area empilhada 90 dias)
  - Tabela de Aging WIP (issues acima do P85 de Cycle Time)

---

## Configuracao de Projetos (`projects.yaml`)

### Estrutura

```yaml
projects:
  - key: BKA
    name: "PS - San Ignacio"
    exclude_statuses: ["Canceled", "Reject", "Open", "To do", "Backlog", "Refinement"]
    pipelines:
      active:
        name: "Trabalho ativo"
        jql: 'project = "PS - San Ignacio" AND status in ("In Progress", "Blocked", "Test", "Waiting for Delivery")'
      done:
        name: "Done (6 meses)"
        jql: 'project = "PS - San Ignacio" AND status = Done AND resolved >= -26w'
      delta:
        name: "Delta (10 dias)"
        jql: 'project = "PS - San Ignacio" AND updated >= -10d'
```

### Pipelines por Projeto

Cada projeto tem 3 pipelines executadas sequencialmente:

| Pipeline | O que busca | Volume | Quando importa |
|----------|------------|--------|----------------|
| **active** | Issues In Progress + Blocked + Test + Waiting for Delivery (full) | Pequeno (~10-50) | Cycle time aberto |
| **done** | Issues Done resolvidas nos ultimos 6 meses | Moderado | Metricas historicas |
| **delta** | Qualquer issue atualizada nos ultimos 10 dias | Variavel | Captura mudancas recentes (incluindo cancelamentos) |

### Delta sem filtro de status

O delta **nao filtra por status** propositalmente. Se uma issue foi cancelada, o delta a traz e o processo de ingestao a remove do banco (via `--exclude-statuses`). Isso evita que issues canceladas fiquem "presas" eternamente.

---

## Banco de Dados (SQLite)

### Tabelas

| Tabela | Descricao |
|--------|-----------|
| `issues` | Issues do Jira (key, summary, status, dates, assignee, etc.) |
| `parsed_changelogs` | Eventos de changelog (transicoes de campo) |
| `metrics` | Lead time e cycle time calculados por issue |
| `metrics_per_status` | Tempo gasto em cada status por issue (Wave 1.1) |
| `metrics_percentiles` | Percentis P50/P70/P85/P95 por projeto (Wave 1.2) |
| `metrics_flow` | Flow efficiency por issue (Wave 1.3) |
| `metrics_cfd` | CFD snapshots diarios (Wave 1.4) |
| `blacklist_rules` | Regras de blacklist (autores/campos a ignorar) |
| `sync_history` | Historico de sincronizacoes |
| `purge_history` | Historico de expurgos |

### Schema: `issues`

| Campo | Tipo | Descricao |
|-------|------|-----------|
| key | TEXT PK | Chave da issue (ex: BKA-123) |
| summary | TEXT | Titulo |
| issuetype_name | TEXT | Tipo (Story, Task, Bug, Sub-task) |
| status | TEXT | Status atual |
| project_key | TEXT | Chave do projeto (derivada da issue key) |
| project_name | TEXT | Nome do projeto |
| parent_key | TEXT | Key da issue pai (para subtasks) |
| assignee_name | TEXT | Responsavel |
| created_at | TEXT | Data de criacao (ISO) |
| updated_at | TEXT | Ultima atualizacao (ISO) |
| due_date | TEXT | Data de entrega |
| resolved_at | TEXT | Data de resolucao |

### Schema: `parsed_changelogs`

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | INTEGER PK | Auto-incremento |
| issue_key | TEXT FK | Referencia a issue |
| author_name | TEXT | Quem fez a mudanca |
| event_date | TEXT | Data/hora do evento |
| field | TEXT | Campo alterado (status, assignee, etc.) |
| from_value | TEXT | Valor anterior |
| to_value | TEXT | Valor novo |
| is_cycle_time_interval | BOOLEAN | Se eh transicao de cycle time |

### Schema: `metrics`

| Campo | Tipo | Descricao |
|-------|------|-----------|
| issue_key | TEXT PK | Referencia a issue |
| lead_time_ms | INTEGER | Tempo total: created -> resolved (ms) |
| cycle_time_ms | INTEGER | Tempo em estados ativos (ms) |

### Schema: `metrics_per_status`

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | INTEGER PK | Auto-incremento |
| issue_key | TEXT | Referencia a issue |
| project_key | TEXT | Projeto |
| status | TEXT | Status em que ficou |
| duration_ms | INTEGER | Tempo nesse status (ms) |
| entered_at | TEXT | Quando entrou |
| exited_at | TEXT | Quando saiu (NULL = atual) |

### Schema: `metrics_percentiles`

| Campo | Tipo | Descricao |
|-------|------|-----------|
| project_key | TEXT | Projeto |
| metric_type | TEXT | 'lead_time' ou 'cycle_time' |
| p50_ms / p70_ms / p85_ms / p95_ms | INTEGER | Percentis |
| avg_ms | INTEGER | Media |
| count | INTEGER | Qtd issues analisadas |

### Schema: `metrics_flow`

| Campo | Tipo | Descricao |
|-------|------|-----------|
| issue_key | TEXT PK | Referencia a issue |
| project_key | TEXT | Projeto |
| work_time_ms | INTEGER | Tempo em In Progress |
| wait_time_ms | INTEGER | Tempo de espera (lead - work) |
| lead_time_ms | INTEGER | Lead time total |
| flow_efficiency | REAL | Percentual (0-100) |

### Schema: `metrics_cfd`

| Campo | Tipo | Descricao |
|-------|------|-----------|
| project_key | TEXT | Projeto |
| snapshot_date | TEXT | Data (YYYY-MM-DD) |
| status | TEXT | Status |
| count | INTEGER | Qtd issues nesse status nesse dia |

---

## Regras de Calculo de Metricas

### Lead Time

```
lead_time = resolved_at - created_at
```

- So calculado para issues com `resolved_at` preenchido (Done)
- Resultado em milissegundos
- **Arquivo:** `metrics/base.py`

### Cycle Time

```
cycle_time = soma dos intervalos em estados ATIVOS
```

**Estados ativos (clock rodando):** `In Progress`, `Blocked`, `Test`, `Waiting for Delivery`

| Cenario | Comportamento |
|---------|--------------|
| Issue entra em In Progress | Clock inicia |
| Issue vai de In Progress para Blocked | Clock **continua** (transicao entre ativos) |
| Issue vai de In Progress para Test | Clock **continua** (transicao entre ativos) |
| Issue vai de Test para Waiting for Delivery | Clock **continua** (transicao entre ativos) |
| Issue vai de Waiting for Delivery para Done | Clock para, intervalo fechado |
| Issue vai de Blocked para Done | Clock para, intervalo fechado |
| Issue vai de In Progress para To do | Clock para, intervalo fechado |
| Issue ainda em estado ativo | Intervalo aberto contabilizado ate momento da ingestao |
| Issue vai de Open direto para Done | Cycle time = 0 (nunca esteve em estado ativo) |

- **Arquivo:** `metrics/base.py`

### Flow Efficiency

```
flow_efficiency = tempo_em_In_Progress / lead_time * 100
```

- Apenas "In Progress" conta como trabalho ativo (Blocked = espera)
- So issues Done com lead_time > 0
- **Arquivo:** `metrics/wave1_bottleneck/flow_efficiency.py`

---

## Blacklist do Changelog

Remove eventos irrelevantes da timeline. Gerenciada via UI em `/settings.html`.

### Tipos

| Tipo | Efeito |
|------|--------|
| `author` | Ignora todos os eventos deste autor |
| `field` | Ignora eventos que alteram este campo |

### Regras padrao

- **Autores:** `Checklists for Jira (Pro) by HeroCoders`
- **Campos:** `Attachment`, `labels`, `IssueParentAssociation`, `Checklist Text`, `Checklist Completed`, `Checklist Text (view only)`

### Onde esta a logica

- **Tabela:** `blacklist_rules` (type, value, enabled)
- **Aplicacao:** `api.py` endpoint `GET /api/issues/{key}/timeline` filtra server-side
- **CRUD:** `GET/POST/PUT/DELETE /api/settings/blacklist`

---

## Sincronizacao (Sync)

### Como funciona

1. Le `projects.yaml`
2. Para cada projeto, executa 3 pipelines sequencialmente (active, done, delta)
3. Cada pipeline: extrai issues do Jira + changelog de cada issue
4. Combina JSONLs das 3 pipelines (dedup por issue key)
5. Ingere no SQLite (INSERT OR REPLACE)
6. Remove issues com status excluido (`--exclude-statuses`)
7. Calcula metricas base (lead/cycle)
8. Calcula Wave 1 (tempo por status, percentis, flow, CFD, aging)
9. Registra resultado em `sync_history`

### Cache de Changelog

Para evitar re-extrair changelogs de issues que nao mudaram:

- Parametro `--db-cache` no `export_jira.py`
- Compara `updated_at` do Jira com `updated_at` no banco
- Se igual: carrega changelog do banco local (0 API calls)
- Se diferente: busca da API normalmente

### Como executar

**Via UI:** `http://localhost:8000/settings.html` > botao "Atualizar"

**Via CLI:**
```powershell
cd C:\Pedro_Github\manager_projects\changelog_timeline\exporter_jira
python export_jira.py --jql query_file.txt --output-dir ../output/KEY --with-changelog --db-cache ../issues.db
cd ..
python ingest_to_db.py --input-dir output/KEY --exclude-statuses "Canceled,Reject"
```

### Cancelamento

- Botao "Cancelar" na UI durante execucao
- Endpoint: `POST /api/settings/projects/sync/cancel`
- Cancelamento graceful (espera etapa atual terminar)

---

## Expurgo (Manutencao)

Remove issues Done com `resolved_at` superior a 6 meses. Evita crescimento indefinido do banco.

### Regra

```sql
DELETE FROM issues WHERE status = 'Done' AND resolved_at < (now - 26 semanas)
```

Tambem remove changelogs e metricas associados.

### Frequencia recomendada

Semanal. A UI mostra badge "Recomendado" quando ultimo expurgo > 7 dias.

### Onde esta a logica

- **Endpoint:** `GET /api/settings/purge/status` (estimativa), `POST /api/settings/purge` (executa)
- **UI:** Secao "Manutencao do Banco" em `/settings.html`

---

## Inconsistencias

Validacoes de qualidade de dados, acessiveis em `/inconsistencies.html`.

| # | Validacao | Filtro de status | Descricao |
|---|-----------|-----------------|-----------|
| 1 | Due date parent < subtask | In Progress, Blocked | Story com due date anterior ao due date das subtasks |
| 2 | Due date vazio | In Progress, Blocked | Issues ativas sem due date |
| 3 | Done sem metricas | Done | Issues concluidas sem lead time E cycle time |
| 4 | Sem cycle time | In Progress, Blocked | Issues ativas sem cycle time calculado |
| 5 | Sem assignee | In Progress, Blocked | Issues ativas sem responsavel |

### Onde esta a logica

- **Endpoint:** `GET /api/inconsistencies?project_key=KEY`
- **UI:** `inconsistencies.html/js`

---

## Nota na Timeline (Transicao Nao Recomendada)

Quando uma issue vai para Blocked ou Done **sem passar por In Progress**, a timeline exibe aviso amarelo:

> "Esta issue foi movida para Open -> Blocked sem passar por In Progress. Por esse motivo, o Cycle Time nao foi computado nos calculos."

### Onde esta a logica

- **Frontend:** `app.js` funcao `detectIntervalsAndWarnings()` (variavel `skippedTransitions`)

---

## Credenciais Jira

Arquivo: `exporter_jira/.env`

```env
JIRA_BASE_URL="https://seu-dominio.atlassian.net"
JIRA_EMAIL="seu-email@empresa.com"
JIRA_API_TOKEN="seu-token-aqui"
JIRA_PAGE_SIZE=100
JIRA_REQUEST_TIMEOUT_SECONDS=30
```

**Nunca commitar este arquivo.** Esta no `.gitignore`.

---

## Endpoints da API

### Issues e Timeline

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/issues` | Lista todas issues com metricas (JOIN metrics) |
| GET | `/api/issues/{key}/timeline` | Timeline filtrada pela blacklist + metricas do banco |

### Wave 1: Metricas de Gargalo

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/metrics/wave1/time-per-status?project_key=X` | Tempo medio e percentis por status |
| GET | `/api/metrics/wave1/percentiles?project_key=X` | P50/P70/P85/P95 de lead e cycle |
| GET | `/api/metrics/wave1/percentiles-weekly?project_key=X` | Evolucao semanal dos percentis (timeline) |
| GET | `/api/metrics/wave1/flow-efficiency?project_key=X` | Flow efficiency agregado e por issue |
| GET | `/api/metrics/wave1/cfd?project_key=X` | CFD (snapshots diarios por status) |
| GET | `/api/metrics/wave1/aging-wip?project_key=X` | Issues ativas acima do P85 |

### Projetos e Sync

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/settings/projects` | Lista projetos com pipelines e ultima sync |
| POST | `/api/settings/projects/sync` | Inicia sync (body: `{project_keys, mode}`) |
| GET | `/api/settings/projects/sync/status` | Status da sync em andamento (polling) |
| POST | `/api/settings/projects/sync/cancel` | Cancela sync em andamento |

### Blacklist

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/settings/blacklist` | Lista regras |
| POST | `/api/settings/blacklist` | Cria regra `{type, value}` |
| PUT | `/api/settings/blacklist/{id}` | Atualiza `{value, enabled}` |
| DELETE | `/api/settings/blacklist/{id}` | Remove regra |

### Expurgo

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/settings/purge/status` | Estimativa e ultimo expurgo |
| POST | `/api/settings/purge` | Executa expurgo |

### Wave 2: Previsibilidade

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/metrics/wave2/throughput?project_key=X&weeks=26` | Throughput semanal (total + por tipo) |
| GET | `/api/metrics/wave2/forecast?project_key=X&remaining_items=N` | Monte Carlo Forecast (P50/P70/P85/P95) |
| GET | `/api/metrics/wave2/open-epics?project_key=X` | Epicos abertos com itens restantes |
| GET | `/api/metrics/wave2/aging-backlog?project_key=X&min_days=30` | Issues inativas (candidatas a cancelamento) |

### Wave 4: Cross-time e Portfolio

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/metrics/wave4/epic-health?project_key=X` | Saude dos epicos (progresso, forecast, risco) |
| GET | `/api/metrics/wave4/benchmarking` | Benchmarking entre todos os projetos |
| GET | `/api/metrics/wave4/cross-project-throughput?weeks=26` | Throughput consolidado multi-projeto |

### Wave 3: Pessoas e Qualidade

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/metrics/wave3/wip?project_key=X` | WIP por pessoa (issues ativas simultaneas) |
| GET | `/api/metrics/wave3/workload?project_key=X&weeks=12` | Distribuicao de carga (Gini + bus factor) |
| GET | `/api/metrics/wave3/handoff?project_key=X` | Handoffs (mudancas de assignee) |
| GET | `/api/metrics/wave3/rework?project_key=X` | Retrabalho (transicoes para tras) |

### Insights

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/insights?project_key=KEY` | Diagnostico automatico — insights por severidade |
| GET | `/api/insights/alert-count` | Contagem de alertas proativos (todos os projetos, para badge nav) |

### Inconsistencias

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/inconsistencies?project_key=KEY` | Retorna 5 validacoes |

---

## Estrutura de Arquivos

```
changelog_timeline/
├── api.py                    # Backend FastAPI (endpoints + sync)
├── ingest_to_db.py           # Ingestao JSONL -> SQLite + orquestra metricas
├── run_pipeline.py           # Orquestrador CLI (legado)
├── projects.yaml             # Configuracao de projetos e pipelines
├── issues.db                 # Banco SQLite (gerado)
│
├── metrics/                  # Pacote de metricas (Python)
│   ├── __init__.py
│   ├── base.py              # Lead time + Cycle time
│   ├── changelog_cache.py   # Cache compartilhado de changelogs de status
│   ├── wave1_bottleneck/    # Wave 1: Gargalo e Fluxo
│   │   ├── __init__.py      # run_wave1() orquestrador
│   │   ├── time_per_status.py
│   │   ├── percentiles.py
│   │   ├── flow_efficiency.py
│   │   ├── cfd.py
│   │   └── aging_wip.py
│   ├── wave2_predictability/ # Wave 2: Previsibilidade
│   │   ├── __init__.py
│   │   ├── throughput.py    # Throughput semanal
│   │   ├── forecast.py     # Monte Carlo + open epics
│   │   └── aging_backlog.py # Issues inativas
│   ├── wave3_people/        # Wave 3: Pessoas e Qualidade
│   │   ├── __init__.py
│   │   ├── wip.py           # WIP por pessoa
│   │   ├── workload.py     # Distribuicao de carga
│   │   ├── handoff.py      # Handoff time
│   │   └── rework.py       # Retrabalho
│   ├── wave4_portfolio/     # Wave 4: Cross-time e Portfolio
│   │   ├── __init__.py
│   │   ├── epic_health.py  # Saude de epicos
│   │   ├── benchmarking.py # Comparacao entre projetos
│   │   └── cross_project.py # Throughput consolidado
│   └── insights/            # Engine de diagnostico automatico
│       ├── __init__.py      # run_insights() entry point
│       ├── engine.py        # InsightsEngine (registro + execucao de regras)
│       ├── rules_flow.py    # 8 regras de diagnostico de fluxo
│       ├── rules_throughput.py # 4 regras de previsibilidade
│       ├── rules_people.py  # 4 regras de pessoas
│       └── rules_portfolio.py # 3 regras de portfolio
│       └── rules_alerts.py  # 5 alertas proativos
│
├── dashboard.html/js/css     # Dashboard operacional (KPIs + tabela)
├── wave1.html/js/css         # Wave 1: Gargalo e Fluxo
├── insights.html             # Insights: Diagnostico automatico
├── insights-page.js          # JS da pagina de insights
├── insights.css              # CSS da pagina de insights
├── nav-alerts.js             # Badge de alertas na nav bar (carrega em todas as paginas)
├── wave2.html                # Wave 2: Previsibilidade
├── wave2.js                  # JS da Wave 2
├── wave2.css                 # CSS da Wave 2
├── wave3.html                # Wave 3: Pessoas e Qualidade
├── wave3.js                  # JS da Wave 3
├── wave3.css                 # CSS da Wave 3
├── wave4.html                # Wave 4: Portfolio
├── wave4.js                  # JS da Wave 4
├── wave4.css                 # CSS da Wave 4
├── index.html                # Timeline standalone
├── app.js / style.css        # JS/CSS da timeline
├── inconsistencies.html/js/css  # Pagina de inconsistencias
├── settings.html/js/css      # Pagina de configuracoes
│
├── exporter_jira/            # Modulo de extracao do Jira
│   ├── export_jira.py        # CLI principal de extracao
│   ├── jira_client.py        # Cliente Jira (auth, paginacao, retry)
│   ├── jira_mapper.py        # Mapeamento de campos
│   ├── jira_comments.py      # Normalizacao de comentarios
│   ├── .env                  # Credenciais (NAO commitar)
│   └── requirements.txt      # Dependencias do extrator
│
├── output/                   # Diretorio de saida das extracoes (JSONL)
│   ├── REYK/ STN/ BKA/ BLZ/
│
├── mock_full_load.py         # Script de carga mock (para testes)
├── mock_delta_sync.py        # Script de delta mock (para testes)
└── schema.py                 # Schema de referencia
```

---

## Adicionar Novo Projeto

1. Editar `projects.yaml` adicionando nova entrada com key, name, exclude_statuses e pipelines
2. Acessar `/settings.html` e clicar "Atualizar" no novo projeto
3. Primeira execucao sera mais lenta (extrai todos os changelogs)
4. Execucoes seguintes usam cache (rapido)

### Template para novo projeto

```yaml
  - key: NOVO
    name: "Nome do Projeto no Jira"
    exclude_statuses: ["Canceled", "Reject", "Open", "To do", "Backlog", "Refinement"]
    pipelines:
      active:
        name: "Trabalho ativo"
        jql: 'project = "Nome do Projeto no Jira" AND status in ("In Progress", "Blocked", "Test", "Waiting for Delivery")'
      done:
        name: "Done (6 meses)"
        jql: 'project = "Nome do Projeto no Jira" AND status = Done AND resolved >= -26w'
      delta:
        name: "Delta (10 dias)"
        jql: 'project = "Nome do Projeto no Jira" AND updated >= -10d'
```

---

## Wave 2: Previsibilidade

### Arquitetura

```
metrics/wave2_predictability/
├── __init__.py              # Exports principais
├── throughput.py            # Throughput semanal (total + por tipo)
├── forecast.py              # Monte Carlo Forecast + open epics
└── aging_backlog.py         # Issues inativas candidatas a cancelamento
```

### 2.1 Throughput Semanal

Quantas issues foram concluidas por semana, agrupadas por data de resolucao (semana ISO).

- **Endpoint:** `GET /api/metrics/wave2/throughput?project_key=X&weeks=26`
- **Retorna:** weekly (lista com total + by_type por semana), summary (avg, stddev, min, max)
- **Frontend:** Grafico de barras + linha de media

### 2.2 Monte Carlo Forecast

Simulacao probabilistica para prever conclusao de N itens restantes.

- **Endpoint:** `GET /api/metrics/wave2/forecast?project_key=X&remaining_items=N`
- **Algoritmo:** 10.000 simulacoes sorteando semanas aleatorias do throughput historico
- **Retorna:** percentiles (P50/P70/P85/P95 em semanas), histogram, throughput_used
- **Frontend:** Tabela de epicos abertos + botao "Simular" + histograma colorido

### 2.3 Epicos Abertos

Lista parents com subtasks nao-Done para alimentar o forecast.

- **Endpoint:** `GET /api/metrics/wave2/open-epics?project_key=X`
- **Retorna:** lista de epicos com key, summary, total, done, remaining, progress_pct

### 2.4 Aging Backlog

Issues abertas ha mais de N dias sem atividade — candidatas a revisao ou cancelamento.

- **Endpoint:** `GET /api/metrics/wave2/aging-backlog?project_key=X&min_days=30`
- **Retorna:** total, brackets (30-60d, 60-90d, 90-180d, 180d+), issues (top 100)

### Frontend Wave 2

- **Pagina:** `/wave2.html`
- **JS:** `wave2.js`
- **CSS:** `wave2.css`
- **Componentes:** Throughput chart (barras + media), Forecast (tabela epicos + simulacao + histograma), Aging Backlog (brackets + tabela)

### Regras de Insight (Previsibilidade)

| # | Regra | Detecta |
|---|-------|---------|
| T1 | Throughput estavel | CV < 0.3 (forecast confiavel) |
| T2 | Throughput instavel | CV > 0.7 (forecast impreciso) |
| T3 | Throughput em queda | 3+ semanas consecutivas caindo |
| T4 | Throughput em alta | 3+ semanas consecutivas subindo |
| T5 | Backlog abandonado | >10 issues inativas ha >180 dias |

---

## Wave 4: Cross-time e Portfolio

### Arquitetura

```
metrics/wave4_portfolio/
├── __init__.py              # Exports principais
├── epic_health.py           # Saude de epicos (progresso + forecast + risco)
├── benchmarking.py          # Comparacao entre projetos
└── cross_project.py         # Throughput consolidado multi-projeto
```

### 4.1 Epic Health

Progresso, forecast e risco por epico/parent.

- **Endpoint:** `GET /api/metrics/wave4/epic-health?project_key=X`
- **Risco:** Composto de due_date vs forecast, progresso baixo, e forecast longo
- **Niveis:** low, medium, high, critical
- **Retorna:** epics (lista com progress, forecast_p85_weeks, risk), summary (at_risk, on_track, done)

### 4.2 Benchmarking

Comparacao de metricas entre todos os projetos.

- **Endpoint:** `GET /api/metrics/wave4/benchmarking` (sem project_key — retorna todos)
- **Metricas por projeto:** Lead/Cycle P50/P85, throughput medio, flow efficiency, rework rate, issues ativas
- **Retorna:** projects (lista ordenada por cycle_time_p85)

### 4.3 Cross-project Throughput

Throughput semanal consolidado de todos os projetos.

- **Endpoint:** `GET /api/metrics/wave4/cross-project-throughput?weeks=26`
- **Retorna:** weekly (lista com total + by_project por semana), projects (lista de project_keys)

### Frontend Wave 4

- **Pagina:** `/wave4.html`
- **JS:** `wave4.js`
- **CSS:** `wave4.css`
- **Nota:** Nao usa filtro de projeto — carrega dados de todos automaticamente
- **Componentes:** Benchmarking table, Cross-project stacked bar chart, Epic Health table com risk badges

### Regras de Insight (Portfolio)

| # | Regra | Detecta |
|---|-------|---------|
| PF1 | Epics at risk | Due date vencida ou <14d com progresso baixo |
| PF2 | Epic stalled | Sem conclusao de subtask ha 3+ semanas |
| PF3 | Cross-project imbalance | Throughput >4x diferenca entre projetos |

---

## Wave 3: Pessoas e Qualidade

### Arquitetura

```
metrics/wave3_people/
├── __init__.py              # Exports principais
├── wip.py                   # WIP por pessoa (issues ativas simultaneas)
├── workload.py              # Distribuicao de carga (Gini + bus factor)
├── handoff.py               # Handoff time (mudancas de assignee)
└── rework.py                # Taxa de reabertura/retrabalho
```

### 3.1 WIP por Pessoa

Quantas issues cada pessoa tem em estados ativos simultaneamente.

- **Endpoint:** `GET /api/metrics/wave3/wip?project_key=X`
- **Estados ativos (WIP):** In Progress, Test (Blocked e Waiting for Delivery nao contam como WIP individual)
- **Risk levels:** low (1-3), medium (4-5), high (6+)
- **Retorna:** people (lista com name, wip_count, issues, risk), summary (avg_wip, overloaded, max_wip)

### 3.2 Distribuicao de Carga

Issues Done por pessoa — identifica concentracao de conhecimento.

- **Endpoint:** `GET /api/metrics/wave3/workload?project_key=X&weeks=12`
- **Metricas:** Gini coefficient (0=igual, 1=concentrado), bus factor (min pessoas para 50%+ entregas)
- **Retorna:** people (name, done_count, percentage, cumulative_pct), summary (gini, bus_factor, top_contributor_pct)

### 3.3 Handoff Time

Transferencias de responsabilidade entre pessoas.

- **Endpoint:** `GET /api/metrics/wave3/handoff?project_key=X`
- **Retorna:** pairs (pares mais frequentes), top_issues (issues com mais handoffs), summary (total, avg_per_issue, avg_time)

### 3.4 Retrabalho

Issues com transicoes "para tras" no fluxo.

- **Endpoint:** `GET /api/metrics/wave3/rework?project_key=X`
- **Logica:** Transicao e "para tras" quando status de destino tem ordem inferior ao de origem
- **Retorna:** issues (top 30 com mais retrabalho), top_rework_types, summary (rework_rate_pct, total_rework_transitions)

### Frontend Wave 3

- **Pagina:** `/wave3.html`
- **JS:** `wave3.js`
- **CSS:** `wave3.css`
- **Componentes:** WIP table com risk colors + issue pills, Workload horizontal bar chart + Gini/bus factor KPIs, Handoff pairs + top issues, Rework types + issues

### Regras de Insight (Pessoas)

| # | Regra | Detecta |
|---|-------|---------|
| P1 | WIP overload | Pessoas com 4+ ou 6+ itens simultaneos |
| P2 | Bus factor risk | 1-2 pessoas fazendo 50%+ das entregas |
| P3 | High rework rate | >30% das issues com transicoes para tras |
| P4 | Handoff excessivo | Media >2 handoffs por issue |

### Nota etica

Estas metricas SAO para riscos organizacionais. NAO para ranking individual.

---

## Insights — Diagnostico Automatico

### Arquitetura

```
metrics/insights/
├── __init__.py              # run_insights(conn, project_key) -> dict
├── engine.py                # InsightsEngine: registra rules, executa, categoriza
├── rules_flow.py            # 8 regras de diagnostico de fluxo (Wave 1)
└── (futuro) rules_throughput.py, rules_people.py, rules_portfolio.py
```

### Como funciona

A engine e modular: cada arquivo `rules_*.py` registra funcoes de deteccao. Cada funcao recebe `(conn, project_key)` e retorna uma lista de `Insight` objects com:

- `category`: "flow", "throughput", "people", "portfolio", "alert"
- `severity`: "critical", "warning", "info", "healthy"
- `title`: titulo curto
- `description`: explicacao detalhada
- `recommendation`: acao sugerida (opcional)
- `metric`/`value`/`threshold`: dados quantitativos (opcional)

### Regras implementadas (Fluxo)

| # | Regra | Detecta |
|---|-------|---------|
| 1.1 | Picos Lead Time | P85 semanal > 3x mediana historica |
| 1.2 | Tendencia Lead Time | P85 crescente 3+ semanas |
| 1.3 | Tendencia Cycle Time | P85 crescente 3+ semanas |
| 1.4 | Gap Lead/Cycle | Ratio > 5x (espera excessiva em filas) |
| 1.5 | Volatilidade Lead Time | Coeficiente de variacao > 1.0 |
| 1.6 | Estabilidade Cycle Time | CV < 0.3 por 4+ semanas (positivo) |
| 1.7 | Flow Efficiency baixa | Media < 15% |
| 1.8 | Gargalo por status | P85 do top status > 2x o segundo |

### Endpoint

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/insights?project_key=X` | Retorna insights categorizados por severidade |

### Resposta da API

```json
{
  "project_key": "STN",
  "total": 3,
  "severity_counts": {"critical": 0, "warning": 1, "info": 1, "healthy": 1},
  "by_category": {"flow": [...]},
  "insights": [
    {"category": "flow", "severity": "warning", "title": "...", "description": "...", "recommendation": "..."},
    ...
  ]
}
```

### Frontend

- **Pagina:** `/insights.html`
- **JS:** `insights-page.js`
- **CSS:** `insights.css`
- **Layout:** Cards agrupados por severidade (Alertas > Observacoes > Saudavel), com icones coloridos, descricao e recomendacao

### Adicionar novas regras

1. Criar `metrics/insights/rules_NOME.py` com funcoes `rule_*(conn, project_key) -> list[Insight]`
2. Criar funcao `register_NOME_rules(engine)` que chama `engine.register(name, fn)` para cada regra
3. Importar e chamar em `engine.py` → `get_engine()`
4. As regras aparecem automaticamente na pagina de Insights

### Alertas Proativos

Alertas usam `category="alert"` e sao exibidos em banner destacado no topo da pagina de Insights.
Um badge dinamico na nav bar mostra a contagem total de alertas em todas as paginas.

| # | Regra | Detecta | Severidade |
|---|-------|---------|-----------|
| A1 | Stale issues | Issues ativas sem atualizacao ha 14+ dias | critical (5+) ou warning (2+) |
| A2 | No assignee | Issues ativas sem responsavel | critical (4+) ou warning |
| A3 | Throughput dropping | Queda >30-50% nas ultimas 2 semanas vs media | critical (50%+) ou warning (30%+) |
| A4 | Epic overdue | Epicos com due date vencida e itens pendentes | critical |
| A5 | WIP explosion | WIP total >3x throughput semanal | warning |

**Endpoint badge:** `GET /api/insights/alert-count` — retorna `{total, critical}` de todos os projetos.

**Frontend:** `nav-alerts.js` carrega em todas as paginas e adiciona badge vermelho/amarelo ao link Insights.

---

## Adicionar Nova Wave de Metricas

1. Criar pasta `metrics/wave2_NOME/`
2. Criar `__init__.py` com `run_wave2(conn, only_keys)`
3. Criar 1 arquivo .py por sub-metrica com `setup_table()` + `calculate_X()`
4. Registrar no `ingest_to_db.py`: `from metrics.wave2_NOME import run_wave2`
5. Criar endpoints em `api.py`: `GET /api/metrics/wave2/*`
6. Criar `wave2.html/js/css` (flat na raiz)
7. Adicionar link na navegacao
8. Atualizar este DATASHEET

---

## Performance

### Indices de banco de dados

O projeto cria indices automaticamente no `setup_db()` do `ingest_to_db.py`:

| Tabela | Indice | Proposito |
|--------|--------|-----------|
| `parsed_changelogs` | `idx_changelogs_issue_field(issue_key, field)` | Queries de metricas e timeline |
| `parsed_changelogs` | `idx_changelogs_project(project_key)` | CFD e agregacoes por projeto |
| `issues` | `idx_issues_project(project_key)` | Filtros por projeto |
| `issues` | `idx_issues_status(status)` | Inconsistencias e filtros |
| `metrics` | `idx_metrics_project(project_key)` | Percentis e Wave 1 |

### PRAGMAs SQLite

- `journal_mode=WAL` — permite leituras concorrentes durante escrita
- `synchronous=NORMAL` — seguro com WAL, reduz fsync desnecessarios
- `timeout=30` — espera ate 30s se banco estiver locked

### Deduplicacao de changelogs

Na combinacao dos JSONLs das 3 pipelines, changelogs sao deduplicados por `(issue_key, event_date, field, to_value)` para evitar inflacao da tabela.

### Historico de otimizacoes

| Metrica | Original | Onda 1 | Onda 2 | Onda 3+4 |
|---------|----------|--------|--------|----------|
| Tempo sync STN | 306.5s | 81.3s (-73%) | 17.4s (-94%) | 8.2s delta (-97%) |
| Tempo metricas BKA | >10s est. | — | — | 0.3s |
| Changelogs inseridos | 26.353 | 17.729 (-33%) | 17.734 | — |
| Cache hit rate | 0% | — | — | 99% (STN) |
| Tecnica principal | — | Indices + dedup + executemany | Session + ThreadPool(8) + fields | expand=changelog + cache normalizado + JQL unificada |

Documentos completos: `melhorias_v1.md` (performance) e `melhorias_v2.md` (features).

---

## Problemas Comuns

| Problema | Causa | Solucao |
|----------|-------|---------|
| "database is locked" | Processo de ingestao rodando simultaneamente | Aguardar conclusao ou reiniciar servidor |
| Cycle time = 0 para issue In Progress | Issue nunca saiu e voltou para In Progress | Normal se acabou de entrar; recalcular metricas |
| Delta demora muito | Primeira execucao sem cache | Normal na 1a vez; proximas serao rapidas |
| Erro de conexao na sync | VPN desconectada ou rede instavel | Verificar VPN e tentar novamente |
| Dados desatualizados no browser | Cache do browser | Ctrl+Shift+R (hard refresh) |
| Projeto nao aparece no dashboard | Nenhuma sync executada para ele | Executar "Atualizar" em /settings.html |
| Wave 1 sem dados | Precisa recalcular wave1 com issues Done | Rodar sync para popular time_per_status e flow |
| CFD vazio | Precisa recalcular wave1 | Sync inclui calculo automatico do CFD |


---

## Modulo Hierarchy — Pipeline Hierarquica (Iniciativas e Epicos)

### Visao Geral

Pipeline **completamente isolada** do projeto padrao. Extrai a hierarquia Jira (Iniciativa → Epico → Story → Sub-task) e oferece visao executiva com metricas agregadas.

- **Banco:** `hierarchy.db` (SQLite isolado — nao depende de `issues.db`)
- **Principio:** dados duplicados intencionalmente (mesmo que uma story exista em issues.db, ela tambem existe em hierarchy.db)
- **Purge:** nao tem (epicos duram 1 ano+)
- **Navegacao:** Modulo separado acessivel via aba "Hierarquia" na nav principal

### Arquitetura

```
changelog_timeline/
├── hierarchy.db                      # Banco isolado
├── hierarchy_db.py                   # Schema + setup (7 tabelas, 6 indices)
├── exporter_jira/
│   └── export_hierarchy.py           # Extrator cascata (Iniciativa→Epico→Story→Subtask)
├── metrics/
│   └── hierarchy_metrics.py          # Lead/cycle time + throughput + Monte Carlo + risk + initiative health
├── hierarchy/                        # Frontend do modulo
│   ├── dashboard-v2.html/js          # Dashboard consolidado (big numbers + initiatives + orfaos)
│   ├── epic-health.html/js           # Detalhe por epico (throughput, forecast, stories)
│   ├── initiative-health.html/js     # Detalhe por iniciativa (epicos filhos)
│   ├── roadmap.html/js               # Roadmap/Gantt (timeline mensal por hierarquia)
│   ├── settings.html/js              # CRUD config + sync + historico
│   ├── hierarchy.css                 # CSS compartilhado do modulo
│   └── nav.js                        # Navegacao interna do modulo
└── projects.yaml                     # Campo `hierarchy:` com config de extracoes
```

### Banco: hierarchy.db (Tabelas)

| Tabela | Descricao | Changelog? |
|--------|-----------|-----------|
| `h_initiatives` | Metadados de iniciativas + `children_keys` (JSON array de epics) | Nao |
| `h_epics` | Metadados de epicos + `parent_key` (→ initiative) + `children_keys` | Nao |
| `h_stories` | Stories com metadados + `parent_key` (→ epic) | Sim (via h_changelogs) |
| `h_subtasks` | Sub-tasks com metadados + `parent_key` (→ story) | Sim (via h_changelogs) |
| `h_changelogs` | Transicoes de status (field='status') de stories e subtasks | — |
| `h_metrics` | lead_time_ms e cycle_time_ms calculados por issue | — |
| `h_sync_history` | Historico de extracoes | — |

### Configuracao (projects.yaml)

```yaml
hierarchy:
  - key: GPPGI-325
    name: "Programa de Modernizacao"
    type: initiative
  - key: PSADB-1457
    name: "Migration Oracle"
    type: epic
```

### Paginas do Modulo

| URL | Descricao |
|-----|-----------|
| `/hierarchy/dashboard-v2.html` | Dashboard consolidado: big numbers + tabela iniciativas + tabela epicos orfaos |
| `/hierarchy/epic-health.html?key=X` | Detalhe de um epico: KPIs, throughput mensal, forecast Monte Carlo, tabela stories |
| `/hierarchy/initiative-health.html?key=X` | Detalhe de uma iniciativa: KPIs, throughput mensal, epicos filhos |
| `/hierarchy/roadmap.html` | Roadmap/Gantt: stories na timeline mensal agrupadas por hierarquia |
| `/hierarchy/settings.html` | CRUD de hierarquias + sincronizacao + historico |

### Navegacao Interna

```
← Portfolio | Dashboard | Roadmap | Configuracoes
```

### Endpoints da API — Hierarchy

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/hierarchy/config` | Lista hierarquias configuradas |
| POST | `/api/hierarchy/config` | Adiciona nova hierarquia `{key, name, type}` |
| PUT | `/api/hierarchy/config/{key}` | Atualiza hierarquia |
| DELETE | `/api/hierarchy/config/{key}` | Remove hierarquia |
| GET | `/api/hierarchy/tree?key=X` | Arvore completa (initiative→epics→stories→subtasks com metricas) |
| GET | `/api/hierarchy/epic-health?key=X` | Saude de um epico (ou todos se key omitido) |
| GET | `/api/hierarchy/initiative-health?key=X` | Saude de uma iniciativa (ou todas) |
| GET | `/api/hierarchy/dashboard-v2` | Dados consolidados (big numbers + initiatives + orfaos) |
| GET | `/api/hierarchy/roadmap` | Dados para roadmap (stories hierarquicas + orfaos) |
| POST | `/api/hierarchy/sync` | Dispara extracao hierarquica (initiative_key ou epic_keys) |
| GET | `/api/hierarchy/sync/status` | Status da sync em andamento |
| GET | `/api/hierarchy/sync/history` | Historico de syncs (ultimas 20) |
| GET | `/api/hierarchy/last-sync` | Ultima sync com sucesso |

### Metricas Calculadas (hierarchy_metrics.py)

| Funcao | Descricao |
|--------|-----------|
| `calculate_hierarchy_metrics(conn)` | Lead/cycle time para h_stories + h_subtasks |
| `get_epic_weekly_throughput(conn, key, weeks)` | Throughput semanal por epico |
| `get_epic_monthly_throughput(conn, key, months)` | Throughput mensal por epico |
| `monte_carlo_forecast(throughput, remaining)` | Forecast P50/P70/P85/P95 |
| `assess_epic_risk(...)` | Risco (4 fatores: due date, progresso, forecast, throughput declinante) |
| `get_epic_health_data(conn, key)` | Dados completos de saude de um epico |
| `get_all_epics_health(conn)` | Portfolio de todos os epicos |
| `get_initiative_health_data(conn, key)` | Saude de uma iniciativa (agrega epicos filhos) |
| `get_initiative_monthly_throughput(conn, key, months)` | Throughput mensal agregado |
| `get_all_initiatives_health(conn)` | Portfolio de todas as iniciativas |
| `get_dashboard_v2_data(conn)` | Dados consolidados (big numbers + initiatives + orfaos) |

### Regras de Negocio

- Status `Done` e `Canceled` sao tratados como concluidos em todos os calculos
- Throughput conta stories por mes (nao por semana) nas paginas de initiative e epic
- Risco corporativo: composicao dos riscos dos epicos (any critical → critical)
- Epicos orfaos: epicos sem `parent_key` vinculado a uma iniciativa
- Stats de conclusao nos headers do Roadmap sao FIXAS (nao mudam com filtros)
- Filtros do Roadmap sao dinamicos e cascateantes (selecionar iniciativa filtra opcoes dos dropdowns abaixo)

### Roadmap (Gantt Simplificado)

Visualizacao timeline de stories posicionadas por mes:

- **Timeline:** 6 meses (1 atras + atual + 4 a frente)
- **Data exibida:** Para Done/Canceled usa `resolved_at`; para outros usa `due_date`
- **Cores:** Blocked=vermelho, In Progress=azul, Done/Canceled=verde, outros=cinza
- **Hierarquia:** Iniciativas → Epicos → Stories (headers com stats fixas)
- **Secao separada:** Epicos Orfaos com seus proprios filtros
- **Filtros:** Dropdown com checkbox (Iniciativa, Epico, Projeto, Status, Assignee)
- **Tooltip:** Key, Summary, Projeto, Assignee, Status, Data
- **Keys:** Hyperlinks para Jira (`https://jiraps.atlassian.net/browse/{KEY}`)

### Extrator Hierarquico (export_hierarchy.py)

Cascata de JQLs:
1. Busca metadados de Iniciativa (sem changelog)
2. Busca Epicos filhos via `parent in (...)` ou `linkedissue in (...)` (sem changelog)
3. Busca Stories filhas dos Epicos (COM changelog, expand=changelog)
4. Busca Sub-tasks das Stories (COM changelog)
5. Persiste tudo em hierarchy.db
6. Calcula metricas (lead/cycle time)

---

## Padronizacao Visual (Regras Obrigatorias)

> **Nota (v2.0.0):** as regras abaixo sao a base historica. A fonte unica de estilo
> agora e `tokens.css` (cor/tipografia/espacamento/botoes) — ver *Revisao de UX (v2.0.0)*
> e `docs/GUIA-DESIGN-DASHBOARD.md`. O fundo com radial-gradients e o blur foram
> removidos em favor de superficie neutra.

### Layout

- Body: `padding: 2rem 0.5rem` + `background-color: var(--surface-0)` (sem gradiente)
- Container: `max-width: 100%; margin: 0 auto; padding: 1.5rem 0.5rem`
- Header: h1 `font-size: 2rem` (`--fs-2xl`), subtitle `font-size: 1rem` (`--fs-lg`)
- Responsivo: `@media (max-width: 768px) { padding: 1rem; }`

### Navegacao

- Injetada por `nav.js` (estilo em `nav.css`) num placeholder `<nav id="main-nav" class="nav-bar">`
- **Agrupada por pergunta** (ver secao *Navegacao* acima); ordem/abas no array `GROUPS` de `nav.js`
- NUNCA escrever links a mao por pagina, estilos inline ou onmouseover
- Adicionar/reordenar aba: editar APENAS `nav.js` (reflete em todas as paginas)

### Graficos

- Plugin `chartjs-plugin-datalabels` obrigatorio em graficos de barras
- Datalabels: font 18px bold, cor branca, centralizado na barra, ocultar zeros
- Chart container: `height: 320px; width: 100%`

### Filtros de Tabela

- Dropdown com checkboxes (NUNCA `<select multiple>` nativo)
- Filtros dinamicos e cascateantes (opcoes recalculam ao filtrar nivel superior)
- Badge com contagem `(N)`, fecha ao clicar fora, botao "Limpar"
- Referencia: `hierarchy/roadmap.js`

### Tabelas

- Cores por status: Done=verde, Canceled=vermelho, Blocked=amarelo, In Progress=azul
- Colunas de Key com hyperlink Jira
- Headers clicaveis para ordenacao (`.sortable` com indicador ↕↑↓)

### Documentacao

- Steering em `.kiro/steering/layout-rules.md` (regras) + `docs/GUIA-DESIGN-DASHBOARD.md` (racional teorico)
- Design system: `tokens.css`, `nav.*`, `ui.*`, `context.js`
- Paginas de referencia: `minha-visao.html`, `compromisso.html`, `wave1.html`, `inconsistencies.html`, `hierarchy/dashboard-v2.html`


---

## Aba Maturidade (Report por Assignee)

### Visao Geral

Report consolidado de acoes pendentes por assignee, integrando dados de WIP, Blocked, Aging, Inconsistencias e Fluxo. Projetado para copiar e colar como mensagem direta ao responsavel.

### Pagina

| URL | Descricao |
|-----|-----------|
| `/maturidade.html` | Report por assignee com acoes pendentes |

### Fontes de Dados

| Endpoint | Dados extraidos |
|----------|----------------|
| `/api/metrics/wave3/wip` | WIP por pessoa + issues bloqueadas |
| `/api/inconsistencies` | Due date vazio, sem assignee, prazo parent vs subtask, done sem metricas, ativa sem cycle |
| `/api/metrics/wave1/aging-wip` | Issues paradas acima do P85 |

### Tipos de Problema Detectados

| Tipo | Severidade | Condicao |
|------|-----------|----------|
| WIP | ATENCAO/CRITICO | >= 4 atividades simultaneas (critico >= 6) |
| BLOCKED | ATENCAO/CRITICO | >= 1 atividade bloqueada (critico >= 3) |
| DUE DATE | ATENCAO | Issue ativa sem due date |
| ASSIGNEE | CRITICO | Issue ativa sem responsavel |
| AGING | ATENCAO/CRITICO | Sem atualizacao ha > 14 dias (critico > 30 dias) |
| PRAZO | ATENCAO | Due date subtask posterior ao parent |
| METRICAS | INFORMATIVO | Done sem lead/cycle time |
| FLUXO | INFORMATIVO | Ativa sem cycle time computado |

### Funcionalidades

- Agrupamento por assignee (Sem Assignee primeiro)
- Botao "Copiar" individual por assignee (formato tabulado para Excel/Sheets)
- Botao "Copiar Todos" geral
- Modal de configuracao de regras (thresholds editaveis)
- Persistencia de regras em localStorage
- Textos com destaque em cores (valores criticos em vermelho, recomendados em amarelo, metricas em azul)
- Severidade em portugues (CRITICO / ATENCAO / INFORMATIVO)

### Configuracao de Regras (Modal)

Thresholds editaveis via botao "Regras":

| Regra | Campos | Default |
|-------|--------|---------|
| WIP | Recomendado, Atencao (>=), Critico (>=) | 3, 4, 6 |
| BLOCKED | Recomendado, Atencao (>=), Critico (>=) | 0, 1, 3 |
| AGING | Min dias sem atualizacao, Critico (> dias) | 14, 30 |

Valores persistidos em localStorage do browser.

---

## Aba Insights (ARQUIVADA)

A aba Insights foi removida da navegacao em 21/08/2026. Os endpoints e arquivos permanecem no projeto para possivel reimplementacao futura.

Documentacao completa em: `aba_arquivada_insights.md`

---

## Revisao de UX (v2.0.0)

Consolidacao de uma revisao de UX em 4 ondas. Alem das telas e nav ja citadas acima,
os pontos estruturais:

### Wave 5 — Compromisso de Prazo (Due Date Slippage)

Responde a pergunta nº1 dos gestores: a equipe cumpre prazo ou empurra a data? Consome
`parsed_changelogs WHERE field='duedate'` (evento com `from_value`/`to_value`).

- **Pacote:** `metrics/wave5_commitment/` (`due_date_slippage.py`, `commitment_score.py`, `__init__.py`)
- **Contrato:** `setup_table()` + `calculate_due_date_slippage(conn, only_keys)`; orquestrado por `run_wave5()` na ingestao (etapa `[6/6]`)
- **Tabela:** `metrics_due_date_slippage` (issue_key, project_key, assignee_name, reschedules, pushes, pulls, total_days_pushed, original_due, current_due, last_changed_at, classification)
- **Classificacao:** 0=`kept` (mantido) · 1=`replanned` · 2=`attention` · 3+=`pushing` (prazo empurrado)
- **Commitment Score:** % de issues entregues na 1a data prometida (sem reprogramar). Meta >= 70%.

### Endpoints novos

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/metrics/wave5/slippage?project_key=X` | Commitment score + por assignee + piores issues |
| GET | `/api/metrics/wave5/commitment-summary` | Score por projeto (todos), para a home |
| GET | `/api/home/overview?project_keys=A,B` | Agregados por projeto (score, `commitment_counts`/`commitment_total`, pushing, blocked, no_assignee, in_flight, stale) |
| GET | `/api/home/detail?project_key=X&metric=Y` | Issues reais de um indicador (metric: pushing/attention/blocked/no_assignee/in_flight/stale); cada issue inclui `due_date` — alimenta o painel de detalhe inline |

### Design System (frontend)

Fonte unica de estilo, substitui 9 blocos `:root` duplicados e 2 familias de variavel:

- **`tokens.css`** — cor (superficies dessaturadas, texto AA, acao, semantico `--ok/--warn/--risk`, serie de grafico `--chart-1..6` de maxima distincao), tipografia (6 degraus, piso 12px), espacamento (grade 4px), sistema de botoes (`.btn` + `--primary/secondary/ghost/danger` × `--sm/md`). Carregar antes de tudo; mantem aliases retrocompativeis.
- **`nav.css` / `nav.js`** — navegacao compartilhada agrupada por pergunta.
- **`ui.css` / `ui.js`** — densidade (compacto/confortavel, `data-density` no `<html>`, localStorage `ct.density`), `tabular-nums` global em tabelas, copiar tabela (TSV), helper `CTUI.token()` para cores de grafico via token.
- **`context.js`** — persiste o projeto selecionado entre paginas (localStorage `ct.selectedProject`), via `CTContext.bindProjectSelect()`.

Regras de uso e racional teorico (Tufte, Few, Munzner, Cleveland & McGill, WCAG):
`docs/GUIA-DESIGN-DASHBOARD.md`.

### Dashboard — KPIs

O KPI unico de "WIP" foi separado em **Em andamento** (In Progress + Test + Waiting for
Delivery) e **Bloqueado** (status Blocked, card proprio). "Done esta semana" ganhou
comparativo (delta) vs os 7 dias anteriores.

### Estados de interface

Telas novas usam estados distintos: loading (skeleton), vazio (com acao) e erro (com
"Tentar de novo"). Nav e design system tambem aplicados a `index.html` (timeline por issue).

### Incremento v2.1.0 — Home Minha Visao + tooltip reutilizavel

**Painel de detalhe inline (Minha Visao).** Clicar num indicador de um card (Prazo
empurrado, Bloqueado, Sem responsavel, Em andamento, Paradas >14d) abre, abaixo dos
cards, um painel com as issues reais daquele indicador (via `/api/home/detail`). O
painel tem:
- **Ordenacao** em todas as colunas (Issue, Resumo, Responsavel, Status, Due Date, Detalhe).
- **Filtros** dropdown-checkbox multi-selecao nas colunas categoricas (Responsavel, Status),
  **cascateantes** (as opcoes de um recalculam conforme o outro) + botao "Limpar filtros".
- **Paginacao** de 15 itens por pagina, com os controles na mesma linha dos filtros.
- **Coluna Due Date** (formato DD/MM/YYYY).
- Toggle (clicar de novo no indicador) fecha o painel; so um painel aberto por vez.

**Seletor de projetos.** Botao "Todos" renomeado para **"Selecionar todos"**; novo botao
**"Limpar filtro"** (desmarca todos). Selecao persiste em localStorage (`ct.myProjects`).

**Tooltip explicativo do commitment score.** No hover/focus do percentual, um balao mostra
a conta real (`mantidas ÷ total × 100`) + breakdown por classificacao. Dados via
`commitment_counts`/`commitment_total` no `/api/home/overview`.

**Componente reutilizavel `CTUI.infoTooltip` + `.ct-tip`** (ui.js / ui.css). Padrao do
design system para explicar de onde vem qualquer big number/KPI. Uso documentado no
`docs/GUIA-DESIGN-DASHBOARD.md` (secao 4b).

### Automacao (hook)

`.kiro/hooks/datasheet-before-commit.json` — hook `UserPromptSubmit` (tipo agent) que,
ao detectar intencao de commit, exige atualizar este DATASHEET antes de commitar.
