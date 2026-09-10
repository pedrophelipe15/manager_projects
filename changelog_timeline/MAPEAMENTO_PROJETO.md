# Mapeamento e Auditoria do Projeto — Changelog Timeline

> Documento gerado a partir da leitura completa do código-fonte.
> Objetivo: catalogar scripts, dependências e rotas de todos os arquivos internos, e avaliar se os processos/rotas existentes estão corretos ou apresentam problemas.

Data da análise: 10/09/2026

---

## 1. Visão geral da arquitetura

```
Jira Cloud (REST API v3)
   │
   ▼
exporter_jira/export_jira.py  ──►  output/{KEY}/*.jsonl
exporter_jira/export_hierarchy.py ─► hierarchy.db (direto)
   │
   ▼
ingest_to_db.py  ──►  issues.db  (+ cálculo de métricas base + Wave 1)
   │
   ▼
api.py (FastAPI + uvicorn, porta 8000)
   │
   ▼
Frontend estático (HTML/JS/CSS) servido a partir da raiz + /hierarchy + /mvp_slide
```

Há **dois bancos SQLite isolados**:
- `issues.db` — pipeline "flat" (dashboard, waves 1-4, insights, inconsistências).
- `hierarchy.db` — pipeline hierárquica (iniciativas → épicos → stories → subtasks).

---

## 2. Catálogo de scripts (backend Python)

### 2.1 Entrypoints / orquestração

| Arquivo | Papel | Argumentos CLI | Status |
|---------|-------|----------------|--------|
| `api.py` | Backend FastAPI, servidor de API + estáticos. Cria tabelas de config no import. | — (roda via uvicorn) | OK |
| `ingest_to_db.py` | Lê JSONL → popula `issues.db` → calcula métricas base + Wave 1. | `--input-dir` (obrig.), `--db-path`, `--clear`, `--only-keys`, `--exclude-statuses` | OK |
| `run_pipeline.py` | Orquestrador CLI. Lê `projects.yaml`, combina pipelines em JQL única, chama export + ingest. | `--projects-file`, `--project-key`, `--clear`, `--with-comments`, `--raw`, `--no-cache` | ✅ Corrigido (10/09/2026) — formato `pipelines` |
| `hierarchy_db.py` | Cria/gerencia schema do `hierarchy.db`. Auto-setup no import. | — | OK |
| `schema.py` | Script utilitário: imprime o schema e amostra de `issues.db`. | — | OK (ferramenta de debug) |

### 2.2 Pacote `metrics/`

| Módulo | Função pública principal | Lê | Escreve |
|--------|--------------------------|-----|---------|
| `base.py` | `calculate_metrics()` — lead/cycle time | `issues`, `parsed_changelogs` | `metrics` |
| `changelog_cache.py` | `load_status_changelogs()` — cache compartilhado | `parsed_changelogs` | — |
| `hierarchy_metrics.py` | `calculate_hierarchy_metrics()`, health/forecast/dashboard V2 | tabelas `h_*` | `h_metrics` |
| `wave1_bottleneck/__init__.py` | `run_wave1()` orquestra as 5 submétricas | vários | `metrics_per_status`, `metrics_flow`, `metrics_cfd`, `metrics_percentiles` |
| `wave1_bottleneck/time_per_status.py` | `calculate_time_per_status()` | issues + changelogs | `metrics_per_status` |
| `wave1_bottleneck/percentiles.py` | `calculate_percentiles()` | `metrics` | `metrics_percentiles` |
| `wave1_bottleneck/flow_efficiency.py` | `calculate_flow_efficiency()` | metrics + issues + changelogs | `metrics_flow` |
| `wave1_bottleneck/cfd.py` | `calculate_cfd()` | issues + changelogs | `metrics_cfd` |
| `wave1_bottleneck/aging_wip.py` | `get_aging_wip()` (on-the-fly) | percentiles + metrics + issues | — |
| `wave2_predictability/throughput.py` | `get_throughput_weekly()` | `issues` | — (read-only) |
| `wave2_predictability/forecast.py` | `monte_carlo_forecast()`, `get_open_epics()` | `issues` | — |
| `wave2_predictability/aging_backlog.py` | `get_aging_backlog()` | `issues` | — |
| `wave3_people/wip.py` | `get_wip_per_person()` | `issues` | — |
| `wave3_people/workload.py` | `get_workload_distribution()` (Gini + bus factor) | `issues` | — |
| `wave3_people/handoff.py` | `get_handoff_time()` | `parsed_changelogs` + issues | — |
| `wave3_people/rework.py` | `get_rework_rate()` | `parsed_changelogs` + issues | — |
| `wave4_portfolio/epic_health.py` | `get_epic_health()` | `issues` (self-join) | — |
| `wave4_portfolio/benchmarking.py` | `get_benchmarking()` | percentiles, flow, issues, changelogs | — |
| `wave4_portfolio/cross_project.py` | `get_cross_project_throughput()` | `issues` | — |
| `insights/engine.py` | `run_insights()`, `InsightsEngine`, dataclass `Insight` | — (orquestra regras) | — |
| `insights/rules_flow.py` | `register_flow_rules()` — 8 regras | metrics, percentiles, flow, per_status, issues | — |
| `insights/rules_throughput.py` | `register_throughput_rules()` — 4 regras | `issues` | — |
| `insights/rules_people.py` | `register_people_rules()` — 4 regras | issues + changelogs | — |
| `insights/rules_portfolio.py` | `register_portfolio_rules()` — 3 regras | `issues` | — |
| `insights/rules_alerts.py` | `register_alert_rules()` — 5 alertas | `issues` | — |

Observação: Waves 2/3/4 e as regras de insights são **read-only** (calculam on-the-fly). Somente base + Wave 1 persistem tabelas. Não existe `run_wave2/3/4` — os endpoints chamam as funções diretamente (assimetria intencional, ver §6).

### 2.3 Pacote `exporter_jira/`

| Arquivo | Papel | Argumentos CLI | Status |
|---------|-------|----------------|--------|
| `export_jira.py` | Extrator de issues + changelog/comentários → JSONL | `--jql`, `--output-dir`, `--with-comments`, `--with-changelog`, `--db-cache`, `--skip-test`, `--raw` | OK |
| `export_hierarchy.py` | Extração em cascata (iniciativa→épico→story→subtask) → `hierarchy.db` | `--initiative`, `--epics` | ⚠️ Sem validação de exclusividade (ver §5) |
| `jira_client.py` | Cliente REST v3: auth básica, paginação por cursor, retry com backoff, pausa global em 429 | — | OK |
| `jira_mapper.py` | `map_issue()` — payload bruto → registro flat (lê customfields via env) | — | OK |
| `jira_comments.py` | `normalize_jira_comments()` — extrai texto ADF de comentários | — | OK |

### 2.4 Scripts mock / utilitários

| Arquivo | Papel | Status |
|---------|-------|--------|
| `mock_full_load.py` | Gera 5.000 issues fake em `issues.db` (dados de teste) | ⚠️ Ver §5 (schema divergente) |
| `mock_delta_sync.py` | Simula delta sync fechando 20 issues | ⚠️ Ferramenta de teste, não de produção |
| `stop_services.ps1` | Mata apenas o processo uvicorn `api:app` deste projeto (identificação precisa por CWD/porta) | OK (bem implementado) |
| `validate_requirements.ps1` | Valida `requirements.txt` (versões pinadas + dry-run pip + imports) | ⚠️ Ver §5 (openpyxl) |

---

## 3. Dependências

### 3.1 `requirements.txt` (raiz)

```
fastapi==0.139.2
uvicorn==0.51.0
starlette==1.3.1
pydantic==2.13.4
PyYAML==6.0.3
python-dotenv==1.2.2
requests==2.34.2
```

### 3.2 `exporter_jira/requirements.txt`

```
requests>=2.32.0
python-dotenv>=1.0.1
```

### 3.3 Problemas de dependência detectados

- **`openpyxl` — RESOLVIDO (10/09/2026).** Confirmado por grep que `openpyxl` **não é importado** em nenhum arquivo Python (as ocorrências de "xlsx" eram a menção no `DATASHEET.md`, um nome de template HTML e nomes de anexos do Jira). Não é dependência real. A menção foi removida do `DATASHEET.md` e a instalação passou a apontar para `pip install -r requirements.txt`.
- **Versões pinadas — FALSO POSITIVO (10/09/2026).** Ao contrário do que a análise inicial supôs, todas as versões pinadas na raiz (`fastapi==0.139.2`, `uvicorn==0.51.0`, `starlette==1.3.1`, `pydantic==2.13.4`, `PyYAML==6.0.3`, `python-dotenv==1.2.2`, `requests==2.34.2`) **existem no PyPI e instalam sem conflito** em venv limpo (Python 3.14.6). `validate_requirements.ps1` sai com código 0 e `import api` carrega. Nenhuma alteração de versão foi necessária.
- **Inconsistência de pin.** A raiz usa `==` (pinado exato), o exporter usa `>=` (aberto). Não é erro, mas convém padronizar.

---

## 4. Catálogo de rotas (API — `api.py`)

Todas as rotas foram cruzadas com as chamadas `fetch()` do frontend. **Nenhuma chamada do frontend aponta para rota inexistente**, e **nenhum arquivo estático referenciado está faltando**.

### 4.1 Issues & Timeline
| Método | Rota | Consumidor no front |
|--------|------|---------------------|
| GET | `/api/issues` | `dashboard.js` |
| GET | `/api/issues/{key}/timeline` | `app.js` |

### 4.2 Settings — Blacklist
| Método | Rota |
|--------|------|
| GET/POST | `/api/settings/blacklist` |
| PUT/DELETE | `/api/settings/blacklist/{rule_id}` |

### 4.3 Settings — Projetos & Sync
| Método | Rota |
|--------|------|
| GET | `/api/settings/projects` |
| POST | `/api/settings/projects/sync` |
| GET | `/api/settings/projects/sync/status` |
| POST | `/api/settings/projects/sync/cancel` |

### 4.4 Settings — Expurgo & Validações
| Método | Rota |
|--------|------|
| GET | `/api/settings/purge/status` |
| POST | `/api/settings/purge` |
| GET | `/api/settings/validations` |
| PUT | `/api/settings/validations/{rule_id}` |

### 4.5 Inconsistências
| Método | Rota |
|--------|------|
| GET | `/api/inconsistencies` |

### 4.6 Wave 1 (gargalo/fluxo)
| Método | Rota |
|--------|------|
| GET | `/api/metrics/wave1/time-per-status` |
| GET | `/api/metrics/wave1/percentiles` |
| GET | `/api/metrics/wave1/percentiles-weekly` |
| GET | `/api/metrics/wave1/flow-efficiency` |
| GET | `/api/metrics/wave1/cfd` |
| GET | `/api/metrics/wave1/aging-wip` |
| POST | `/api/metrics/wave1/recalculate` |
| GET | `/api/metrics/wave1/recalculate/status` |
| GET | `/api/metrics/wave1/last-update` |

### 4.7 Insights
| Método | Rota |
|--------|------|
| GET | `/api/insights` |
| GET | `/api/insights/alert-count` |

### 4.8 Wave 2 / 3 / 4
| Método | Rota |
|--------|------|
| GET | `/api/metrics/wave2/throughput` |
| GET | `/api/metrics/wave2/forecast` |
| GET | `/api/metrics/wave2/open-epics` |
| GET | `/api/metrics/wave2/aging-backlog` |
| GET | `/api/metrics/wave3/wip` |
| GET | `/api/metrics/wave3/workload` |
| GET | `/api/metrics/wave3/handoff` |
| GET | `/api/metrics/wave3/rework` |
| GET | `/api/metrics/wave4/epic-health` |
| GET | `/api/metrics/wave4/benchmarking` |
| GET | `/api/metrics/wave4/cross-project-throughput` |

### 4.9 Hierarquia
| Método | Rota | Consumidor no front |
|--------|------|---------------------|
| GET/POST | `/api/hierarchy/config` | hierarchy/settings.js, timeline.js |
| PUT/DELETE | `/api/hierarchy/config/{key}` | **PUT sem consumidor** (ver §6) |
| GET/POST/DELETE | `/api/settings/excluded-projects[/{key}]` | hierarchy/settings.js |
| GET | `/api/hierarchy/sync/history` | hierarchy/settings.js |
| GET | `/api/hierarchy/tree` | epic-health.js, timeline.js, executive-slide.js |
| POST | `/api/hierarchy/sync` | hierarchy dashboards |
| GET | `/api/hierarchy/sync/status` | hierarchy dashboards |
| GET | `/api/hierarchy/last-sync` | hierarchy/dashboard.js |
| GET | `/api/hierarchy/epic-health` | epic-health.js, dashboard.js, timeline.js |
| GET | `/api/hierarchy/initiative-health` | initiative-health.js |
| GET | `/api/hierarchy/dashboard-v2` | dashboard-v2.js |
| GET | `/api/hierarchy/roadmap` | roadmap.js |
| GET | `/api/hierarchy/issue-links` | (sem consumidor direto identificado) |

### 4.10 Estáticos
`app.mount("/", StaticFiles(directory=BASE_DIR, html=True))` — serve raiz + subpastas. OK.

---

## 5. Catálogo do frontend (páginas e dependências)

### 5.1 Raiz
| Página | Scripts | CSS | Endpoints principais |
|--------|---------|-----|----------------------|
| `index.html` | `app.js` | `style.css` | `/api/issues/{key}/timeline` |
| `dashboard.html` | Chart.js, `dashboard.js`, `nav-alerts.js` | `dashboard.css` | `/api/issues` |
| `insights.html` | `insights-page.js`, `nav-alerts.js` | `insights.css` | `/api/settings/projects`, `/api/insights` |
| `inconsistencies.html` | `inconsistencies.js`, `nav-alerts.js` | `inconsistencies.css` | `/api/inconsistencies`, `/api/settings/validations` |
| `settings.html` | `settings.js`, `nav-alerts.js` | `settings.css` | blacklist, projects/sync, purge |
| `maturidade.html` | inline (sem JS/CSS externo) | inline | wave3/wip, inconsistencies, wave1/aging-wip |
| `wave1.html` | Chart.js, `wave1.js`, `nav-alerts.js` | `wave1.css` | 10 endpoints wave1 |
| `wave2.html` | Chart.js, `wave2.js`, `nav-alerts.js` | `wave2.css` | 4 endpoints wave2 |
| `wave3.html` | Chart.js, `wave3.js`, `nav-alerts.js` | `wave3.css` | 4 endpoints wave3 |
| `wave4.html` | Chart.js + datalabels, `wave4.js`, `nav-alerts.js` | `wave4.css` | 3 endpoints wave4 |

### 5.2 `hierarchy/` (nav injetada por `nav.js`)
| Página | Situação |
|--------|----------|
| `dashboard-v2.html` + js | Landing canônica da hierarquia. OK |
| `roadmap.html` + js | OK, linkada na nav |
| `settings.html` + js | OK, linkada na nav |
| `epic-health.html` + js | Alcançável via clique de linha (não na nav) |
| `initiative-health.html` + js | Alcançável via clique de linha (não na nav) |
| `dashboard.html` + js | ✅ **Removida (10/09/2026)** — legado; substituída por dashboard-v2. Sem referências no código; retorna 404 |
| `timeline.html` + js | ✅ **Reconectada (10/09/2026)** — link "Timeline" na `nav.js`, validada em runtime |

### 5.3 `mvp_slide/`
| Página | Situação |
|--------|----------|
| `executive-slide.html` + js | Standalone (só por URL direta, com `?key=`). Usa `/api/hierarchy/tree` + JSONs locais opcionais (`eco_classification.json`, `initiative_meta.json`). OK |

---

## 6. Avaliação — problemas e inconsistências encontrados

### 6.1 Correção funcional (nada quebrado, mas atenção)

1. **`export_hierarchy.py` sem validação de argumentos mutuamente exclusivos.**
   `--initiative` e `--epics` ambos com default `None` e nenhum `required`. Se invocado sem args diretamente, o `main()` trata o caso (imprime erro e sai), mas o fluxo via `api.py` (config do YAML) e a chamada direta têm caminhos distintos. Convém tornar explícito (`argparse` com grupo mutuamente exclusivo).

2. **Divergência na definição de "estados ativos" (ACTIVE_STATES).**
   - `metrics/base.py` (cycle time): `{In Progress, Blocked, Test, Waiting for Delivery}`
   - `metrics/wave3_people/wip.py` (WIP por pessoa): `{In Progress, Test}` (Blocked tratado à parte)
   - `api.py` hierarquia: `{In Progress, Blocked, Test, Waiting for Delivery}`

   Isso é **intencional em parte** (WIP não conta Blocked como carga ativa), mas o conjunto está **hardcoded e duplicado** em vários lugares. Risco de drift silencioso. → Centralizar num único ponto de configuração.

3. **`nav-alerts.js` — CORRIGIDO (10/09/2026).**
   O script procura `a[href="/insights.html"]` para colar o badge, mas nenhuma das páginas que o carregam tinha esse link (só a própria `insights.html`). Foi adicionado o link "Insights" na nav de todas as páginas que carregam `nav-alerts.js` (dashboard, wave1-4, inconsistencies, settings) — além de maturidade e index para consistência. Validado em runtime: `/api/insights/alert-count` retorna `total=11, critical=5` e o `dashboard.html` é servido com o link + o script juntos, então o badge passa a renderizar fora de `insights.html`.

4. **`index.html` com nav desatualizada — CORRIGIDO (10/09/2026).**
   A nav do `index.html` (conjunto reduzido) foi expandida para o set canônico completo (Hierarquia, Dashboard, Wave 1-4, Insights, Maturidade, Inconsistências, Configurações), alinhada às demais páginas.

5. **Rota `PUT /api/hierarchy/config/{key}` sem consumidor.**
   O frontend faz edição via add+delete; o endpoint PUT existe mas ninguém chama. Código morto (não é erro, mas candidato a remoção ou uso).

### 6.2 Divergências de schema (risco real)

6. **`mock_full_load.py` desalinhado com o schema real.**
   - Insere em `metrics` via `INSERT ... VALUES (?, ?, … 11 colunas)` posicional. O schema real de `metrics` (em `ingest_to_db.py`) tem colunas em ordem específica; qualquer mudança de coluna quebra o mock silenciosamente (insere no campo errado).
   - Não popula as tabelas Wave 1 (`metrics_per_status`, `metrics_flow`, `metrics_cfd`, `metrics_percentiles`), então as páginas Wave 1 ficam vazias com dados mock.
   - Não cria as tabelas de config (`blacklist_rules`, `sync_history`, etc.) — essas são criadas por `api.py` no import, então funciona, mas o mock não é auto-suficiente.
   → Tratar `mock_full_load.py` como ferramenta de teta descartável; documentar que não gera métricas de Wave.

7. **`mock_delta_sync.py`** insere `metrics` com colunas nomeadas mas omite `parent_key` e `due_date`; funciona porque são nullable, porém reforça que os mocks não refletem o pipeline real.

### 6.3 Duplicação de código (manutenção)

8-12. **Duplicações — CORRIGIDAS (10/09/2026).** Foram criados 3 módulos compartilhados e os chamadores migrados, preservando 100% do comportamento (snapshot de regressão com `random.seed` fixo idêntico byte a byte antes/depois):
   - `metrics/forecast_core.py` — núcleo Monte Carlo (`simulate_completion_weeks` + `percentile_from_sorted`). Consolidou as 3 implementações (`wave2/forecast.py`, `wave4/epic_health.py::_quick_forecast`, `hierarchy_metrics.py::monte_carlo_forecast`), preservando os defaults de cada chamador (10.000 / 1.000 / 1.000 simulações).
   - `metrics/timeutils.py::week_to_date_range` — substituiu as 4 cópias de `_week_to_date_range` (`throughput.py`, `cross_project.py`, `rules_flow.py`; a cópia em `rules_throughput.py` era código morto e foi removida).
   - `metrics/constants.py` — `ACTIVE_STATES`, `WIP_ACTIVE_STATES` (variante intencional do WIP), `STATUS_ORDER` e `is_backward_transition()`. Migrados `base.py`, `wip.py`, `rework.py` e `benchmarking.py` (eliminando as 3 cópias de STATUS_ORDER).
   - Extração ADF unificada: `jira_comments.extract_text_from_comment_adf` agora delega a `jira_mapper.extract_text_from_adf(max_len=10000)`.
   - Import morto `math` removido de `benchmarking.py` (e `math`/`random` mortos removidos de `hierarchy_metrics.py`).
   Validação: snapshot idêntico, todos os `import metrics.*` + `import api` OK, e ingestão completa (base + Wave 1) rodou com sucesso contra cópia do banco.

### 6.4 Documentação desatualizada

13. **`exporter_jira/README.md`** não menciona `--with-changelog`, `--db-cache`, nem o `changelogs.jsonl` gerado; omite `export_hierarchy.py`; e o caminho de setup (`C:\Pedro_Codes\exporter_jira`) não bate com o real.

14. **`DATASHEET.md`** cita `openpyxl` como dependência mas ele não está nos requirements (ver §3.3). Lista "24 regras" de insights — confere com o código (8+4+4+3+5).

15. **`run_pipeline.py` — CORRIGIDO (10/09/2026).** Antes usava o formato antigo (`project.get("jql")` direto) e pulava todos os projetos com o YAML atual. Foi reescrito para combinar as pipelines (`active/done/delta`) numa JQL única com `OR` (mesma lógica do `_run_sync` do `api.py`), passar `--with-changelog`/`--db-cache`/`--exclude-statuses`, e adicionar a flag `--no-cache`. Validado contra o `projects.yaml` atual: os 4 projetos geram JQL não-vazia e `exclude_statuses` corretos.

---

## 7. Resumo do veredito

| Área | Situação |
|------|----------|
| Rotas da API × chamadas do front | ✅ 100% consistente (sem rota quebrada) |
| Referências a arquivos estáticos (script/link/href) | ✅ Nenhuma quebrada |
| Bancos e schemas de produção (`ingest_to_db`, `hierarchy_db`) | ✅ Consistentes |
| Pipeline de sync real (via `api.py`) | ✅ Funcional |
| `run_pipeline.py` (CLI) | ✅ Corrigido — usa formato `pipelines`, validado contra YAML atual |
| Scripts mock | ⚠️ Desalinhados com schema/pipeline real (só teste) |
| Páginas órfãs | ✅ Resolvido — `timeline.html` reconectada na nav; `hierarchy/dashboard.html` (legado) removida |
| `nav-alerts.js` | ✅ Corrigido — link Insights adicionado em todas as páginas; badge validado em runtime |
| Dependências | ✅ Resolvido: `openpyxl` era falso (removido do doc); versões pinadas validadas OK em venv limpo |
| Duplicação de código | ✅ Corrigido — módulos compartilhados (`constants`, `timeutils`, `forecast_core`); snapshot idêntico antes/depois |
| Documentação (README exporter, run_pipeline) | ⚠️ Desatualizada |

### Ações recomendadas (prioridade)

1. **Alta** — Validar versões do `requirements.txt` num ambiente limpo e adicionar `openpyxl` se usado.
2. **Alta** — Decidir o destino de `run_pipeline.py`: atualizar para o formato `pipelines` ou marcar como deprecado.
3. **Média** — Centralizar `ACTIVE_STATES`/`STATUS_ORDER` num módulo único de constantes.
4. **Média** — Corrigir/remover o `nav-alerts.js` (colar badge onde faz sentido) e uniformizar a nav do `index.html`.
5. **Baixa** — Remover páginas órfãs ou reconectá-las à navegação; consolidar as 3 implementações de Monte Carlo e os helpers duplicados; atualizar READMEs.
6. **Baixa** — Remover import morto (`math` em `benchmarking.py`) e a rota PUT sem uso, se confirmado.
