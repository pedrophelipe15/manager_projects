# Melhorias v1 — Performance da Pipeline

Data de criacao: 19/08/2026
Status geral: Em andamento

---

## Contexto

Pipeline do projeto STN levou 306.5s para processar 923 issues (70 active + 790 done + 208 delta).
O delta deveria ser rapido mas nao e, por problemas estruturais identificados.

### Diagnostico resumido

| Problema | Impacto |
|----------|---------|
| Zero indices nas tabelas principais | ~4.600 full scans por sync |
| Bug: changelogs duplicados (seen_changelogs nao usado) | Tabela inflada 2-3x |
| N+1 de rede: 1 requisicao por issue sequencial | ~1068 round-trips |
| JQL sobreposta entre pipelines | ~145 issues buscadas 2-3x |
| CFD reprocessa projeto inteiro mesmo no delta | CPU desperdicada |
| Cache pode nunca acertar (comparacao exata de string) | Full load silencioso |

---

## Onda 1 — Ganho massivo, esforco minimo

**Ganho estimado: 306s → 60-90s**
**Esforco total: ~45 min**

| # | Item | Arquivo | Status | Notas |
|---|------|---------|--------|-------|
| 1.1 | Criar indice `parsed_changelogs(issue_key, field)` | `ingest_to_db.py` (setup_db) | [x] Concluido | Indice mais critico — resolve full scans de metricas e ingestao |
| 1.2 | Criar indice `parsed_changelogs(project_key)` | `ingest_to_db.py` (setup_db) | [x] Concluido | Resolve queries do CFD e agregacoes por projeto |
| 1.3 | Criar indice `issues(project_key)` | `ingest_to_db.py` (setup_db) | [x] Concluido | Resolve COUNT/SELECT por projeto na API e sync |
| 1.4 | Criar indice `issues(status)` | `ingest_to_db.py` (setup_db) | [x] Concluido | Resolve queries de inconsistencias |
| 1.5 | Criar indice `metrics(project_key)` | `ingest_to_db.py` (setup_db) | [x] Concluido | Resolve percentiles e queries do Wave 1 |
| 1.6 | Corrigir dedup de changelogs no `_run_sync` | `api.py` (~linha 562) | [x] Concluido | Dedup por (issue_key, event_date, field, to_value) |
| 1.7 | Usar `executemany` nos inserts de changelog | `ingest_to_db.py` (ingest_changelogs) | [x] Concluido | Batch delete + executemany. Elimina N inserts individuais |
| 1.8 | Adicionar `PRAGMA synchronous=NORMAL` | `ingest_to_db.py` (main) | [x] Concluido | Ja tem WAL, synchronous=NORMAL e seguro com WAL |

### Como validar a Onda 1

Apos implementar, rodar sync do STN e comparar:
- Antes: 306.5s
- Meta: <90s

---

## Onda 2 — Elimina N+1 de rede

**Ganho estimado: tempo de extracao cai 70-85%**
**Esforco total: ~2h**
**Pre-requisito: Onda 1 concluida (senao paraleliza rede mas trava no banco)**

| # | Item | Arquivo | Status | Notas |
|---|------|---------|--------|-------|
| 2.1 | Usar `requests.Session` reutilizada no JiraClient | `exporter_jira/jira_client.py` | [x] Concluido | Session criada no __init__, elimina N handshakes TLS |
| 2.2 | `ThreadPoolExecutor(max_workers=8)` no fetch de changelog | `exporter_jira/export_jira.py` | [x] Concluido | 8 workers paralelos + lock para append thread-safe |
| 2.3 | Unificar pipelines em 1 subprocesso (merge JQLs) | `api.py` (_run_sync) | [x] Concluido | Combina JQLs com OR, 1 extração por projeto em vez de 3. Elimina dedup de JSONL |
| 2.4 | Usar `fields` explicito em vez de `*all` na busca | `exporter_jira/jira_client.py` (fetch_issues_raw) | [x] Concluido | Reduz payload ~40%. Campos: key,summary,status,project,assignee,reporter,issuetype,created,updated,resolutiondate,duedate,parent,labels |
| 2.5 | Usar `expand=changelog` na busca de issues | `exporter_jira/jira_client.py` | [x] Concluido | Embute changelog na resposta. Fallback para endpoint dedicado se >100 entries (overflow) |
| 2.6 | Adicionar retry robusto (backoff exponencial) para 5xx e timeout | `exporter_jira/jira_client.py` | [x] Concluido | _request_with_retry com backoff 2^n, max 4 retries. Semaforo global freia workers no 429 |

### Sobre rate limit do Jira

Jira Cloud tem rate limit. Com 8 workers paralelos, espera-se ~1-2 hits de 429 por sync. Implementado semaforo global (`threading.Event`) que freia todos os workers quando qualquer thread recebe 429. Retry com backoff exponencial (2^attempt) para 5xx e timeouts, max 4 tentativas.

### Como validar a Onda 2

Apos implementar, rodar sync do STN e comparar:
- Antes (pos-Onda 1): ~60-90s
- Meta: <30s

---

## Onda 3 — Corrige hotspots de CPU

**Ganho estimado: calculo de metricas 3-5x mais rapido**
**Esforco total: ~3h**
**Pre-requisito: Onda 1 (indices) para que as queries otimizadas usem os indices**

| # | Item | Arquivo | Status | Notas |
|---|------|---------|--------|-------|
| 3.1 | Carregar changelogs uma vez e compartilhar entre base, time_per_status e flow_efficiency | `metrics/` (todos) | [x] Concluido | Criado `metrics/changelog_cache.py` com `load_status_changelogs()`. 1 query bulk, compartilhada via param `status_cache` |
| 3.2 | Reescrever CFD com varredura incremental | `metrics/wave1_bottleneck/cfd.py` | [x] Concluido | Algoritmo O(N+T): eventos ordenados, contadores atualizados incrementalmente ao cruzar fronteira de dia |
| 3.3 | CFD respeitar `only_keys` | `metrics/wave1_bottleneck/cfd.py` | [x] Concluido | only_keys determina projetos afetados, CFD recalcula corretamente usando todas issues do projeto |
| 3.4 | `executemany` nos inserts do CFD | `metrics/wave1_bottleneck/cfd.py` | [x] Concluido | Acumula all_rows e insere em batch no final |
| 3.5 | `executemany` nos inserts do time_per_status | `metrics/wave1_bottleneck/time_per_status.py` | [x] Concluido | Batch delete + executemany. Elimina N inserts individuais |

### Como validar a Onda 3

Rodar "Atualizar Dados" no Wave 1 com projeto BKA (1415 issues) e medir tempo:
- Antes: estimar rodando 1x
- Meta: <10s para recalcular tudo

---

## Onda 4 — Correcoes de robustez e cache

**Ganho estimado: elimina retrabalho silencioso**
**Esforco total: ~1h**
**Pode ser feita a qualquer momento (independente das outras)**

| # | Item | Arquivo | Status | Notas |
|---|------|---------|--------|-------|
| 4.1 | Instrumentar cache: logar hit/miss rate | `exporter_jira/export_jira.py` | [x] Concluido | Contadores hit/miss + hit_rate % no output |
| 4.2 | Corrigir comparacao de cache: normalizar timestamps antes de comparar | `exporter_jira/export_jira.py` | [x] Concluido | `_normalize_ts()` usa `fromisoformat` — resolve Z vs +00:00, trailing zeros |
| 4.3 | Cache: reutilizar conexao SQLite (abrir 1x fora do loop) | `exporter_jira/export_jira.py` | [x] Concluido | 1 conexao + 1 cursor reutilizado para todas as queries de cache |
| 4.4 | Eliminar round-trip DB→JSONL→DB no cache-hit | `exporter_jira/export_jira.py` + `ingest_to_db.py` | [x] Concluido | Cache-hit nao escreve changelog no JSONL. DB intocado. cache_hit_keys.json para diagnostico |
| 4.5 | Remover variavel morta `cached_changelogs = {}` | `exporter_jira/export_jira.py` | [x] Concluido | Ja removida na Onda 2 |
| 4.6 | Eliminar `test_connection` redundante (3x por projeto) | `exporter_jira/export_jira.py` | [x] Concluido | Flag --skip-test adicionada. api.py passa na pipeline. test_connection so roda standalone |

---

## Decisoes descartadas

| Opcao | Por que nao |
|-------|-------------|
| Trocar SQLite por PostgreSQL | SQLite com indices corretos aguenta 10x o volume. Custo de infra/migracao nao justifica |
| Trocar por DuckDB | Bom para leitura analitica, ruim para o padrao upsert desta pipeline |
| Async/aiohttp em vez de threads | Mais complexo, mesmo ganho. ThreadPoolExecutor e suficiente para I/O bound |

---

## Historico de execucao

| Data | Onda | Itens feitos | Resultado medido |
|------|------|-------------|-----------------|
| 19/08/2026 | Onda 1 | 1.1 a 1.8 (todos) | 306.5s → 81.3s (73% reducao). Dedup reduziu changelogs de 26.353 para 17.729 (33% menos) |
| 19/08/2026 | Onda 2 | 2.1, 2.2, 2.4 | 81.3s → 17.4s (79% reducao). ThreadPool 8 workers + Session + fields explicito. Total acumulado: 306.5s → 17.4s (94% reducao) |
| 19/08/2026 | Onda 2 | 2.3, 2.5, 2.6 | 4 projetos (2828 issues, 44k changelogs) em 70.2s total. STN: 925 issues em 26.4s (full). Delta real esperado: <5s |
| 19/08/2026 | Onda 3 | 3.1 a 3.5 (todos) | BKA (1505 issues): todas as metricas em ~0.3s total. CFD: 0.0s (antes estimado >5s). Meta <10s cumprida com folga |
| 19/08/2026 | Onda 4 | 4.1 a 4.6 (todos) | Delta: 4 projetos (2827 issues) em 25.9s total. STN 8.2s (99% hit rate). Cache funcional, round-trip eliminado. Otimizacao extra: expand=changelog so sem cache |

---

## Como usar este documento

1. Escolha a onda que quer atacar
2. Implemente os itens na ordem (ou fora de ordem se independentes)
3. Marque `[x] Concluido` no item
4. Apos completar os itens da onda, rode o teste de validacao e anote na tabela de historico
5. Retorne quando quiser para a proxima onda
