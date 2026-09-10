# Melhorias v4 — Hierarquia Jira: Épicos, Iniciativas e Visão Executiva

Data de criacao: 20/08/2026
Status geral: Planejado

---

## Contexto

### Hierarquia do Jira

```
Iniciativa (corporativo)
    └── Épico (tribo)
            └── Story (time/projeto)
                    └── Sub-task (time/projeto)
```

### Links entre níveis

| Nível | Link | Mecanismo |
|-------|------|-----------|
| Story → Sub-task | Automático | Campo `parent` nativo |
| Épico → Story | Manual | Campo `parent` ou `linkedissue` (depende do projeto) |
| Iniciativa → Épico | Manual | Campo `parent` ou `linkedissue` |

### Situação atual do projeto

- **Coletamos:** Stories + Sub-tasks por projeto/time (4 projetos: REYK, STN, BL, BKA)
- **Não coletamos:** Épicos e Iniciativas (estão fora do escopo das JQLs atuais)
- **parent_key na tabela issues:** liga Sub-task → Story (já funciona)
- **Não temos:** link Story → Épico nem Épico → Iniciativa

### Limitação do JQL

O Jira JQL **não faz recursão hierárquica** — olha apenas 1 nível de cada vez. Não existe uma JQL única que desce N níveis. A solução requer chamadas em cascata no extrator.

### Nuances importantes

| Cenário | Frequência | Impacto |
|---------|-----------|---------|
| Story sem Épico | Comum | Aparece isolada (sem parent de nível superior) |
| Épico sem Iniciativa | Comum | Aparece isolado (nível mais alto = épico) |
| Story de um time ligada a Épico de outro | Frequente | Precisa suportar cross-project |
| Story já coletada pela pipeline existente | Maioria | NÃO deve re-extrair — só adicionar o link |
| Story Done >6 meses (purgada) | Eventual | Épico perde visibilidade de progresso |
| Épico com stories em múltiplos times | Frequente | Agregação cross-project obrigatória |

---

## Objetivo

Extrair a camada de Épicos e Iniciativas do Jira e conectar à base existente de Stories/Sub-tasks, habilitando:

1. **Epic Health** com dados reais (não apenas stories que são "parent" de sub-tasks)
2. **Initiative Health** (visão corporativa)
3. **Forecast por Épico** com Monte Carlo baseado em throughput real das stories filhas
4. **Rastreabilidade completa:** Iniciativa → Épico → Story → Sub-task

---

## Princípios de design

| Princípio | Motivo |
|-----------|--------|
| Pipeline hierárquica é **completamente isolada** do projeto padrão | Banco separado (`hierarchy.db`), sem dependência cruzada de dados ou configurações |
| Stories que já estão no banco principal **são re-extraídas** na hierarchy | Volume pequeno, isolamento total — dados duplicados intencionalmente |
| Épicos/Iniciativas são extraídos **sem changelog** | São issues de tracking — progresso vem das stories filhas |
| Stories e Sub-tasks são extraídas **com changelog** | Precisam de cycle time, time per status, flow efficiency |
| Sem purge na hierarquia | Épicos duram 1 ano+ — retenção completa |
| Não consulta nem depende de tabelas do projeto padrão | Se hierarchy.db for deletado, projeto padrão continua 100% intacto |

---

## Isolamento entre projetos

```
┌─────────────────────────────────────┐    ┌─────────────────────────────────────┐
│ PROJETO PADRÃO (existente)          │    │ PIPELINE HIERÁRQUICA (nova, isolada) │
│                                     │    │                                     │
│ DB: issues.db                       │    │ DB: hierarchy.db                    │
│ Tabelas: issues, parsed_changelogs, │    │                                     │
│   metrics, metrics_*, etc.          │    │ Tabelas:                            │
│                                     │    │   h_initiatives                     │
│ Pipeline: sync por time/projeto     │    │   h_epics                           │
│ Dados: 6 meses Done + ativos       │    │   h_stories (COM changelog)         │
│ Purge: sim (>6 meses)              │    │   h_subtasks (COM changelog)        │
│                                     │    │   h_changelogs                      │
│ NÃO consulta hierarchy.db ←───X    │    │   h_metrics                         │
│                                     │    │                                     │
│                                     │    │ Pipeline: sync por épico/iniciativa  │
│                                     │    │ Purge: NÃO                          │
│                                     │    │ NÃO consulta issues.db ←───X        │
└─────────────────────────────────────┘    └─────────────────────────────────────┘
         │                                          │
         │ Compartilham APENAS:                     │
         ├── Credenciais Jira (.env)                │
         ├── Servidor API (api.py, mesmo processo)  │
         └── Frontend (mesma nav bar)               │
```

### Changelog por nível hierárquico

| Nível | Changelog | Motivo |
|-------|-----------|--------|
| Iniciativa | **Não extrai** | Issue de tracking — progresso vem dos épicos filhos |
| Épico | **Não extrai** | Issue de tracking — progresso vem das stories filhas |
| Story | **Sim, extrai** | Precisa de cycle time, time per status, flow efficiency |
| Sub-task | **Sim, extrai** | Idem — é onde o trabalho acontece |

### Por que dados duplicados é aceitável

| Aspecto | Impacto |
|---------|---------|
| Volume | 10 épicos × ~30 stories = ~300 issues. Custo desprezível |
| Divergência | Cada banco tem seus dados. Não precisa sincronizar entre eles |
| Pipeline roda tudo junto | Mesma sync atualiza ambos — dados sempre alinhados temporalmente |
| Reset da hierarquia | Pode deletar `hierarchy.db` sem impactar nada do projeto padrão |

---

## Onda 1 — Extração e persistência da hierarquia

**Objetivo: coletar Épicos/Iniciativas e mapear parentesco**
**Esforço estimado: ~4h**

### Arquitetura

```
exporter_jira/
├── export_jira.py            # Extrator existente (stories/subtasks)
└── export_hierarchy.py       # NOVO: extrator de hierarquia (épicos/iniciativas)

metrics/
└── wave4_portfolio/
    └── hierarchy.py          # NOVO: resolução de parentesco completo
```

### Banco: `hierarchy.db` (tabelas)

```sql
-- Iniciativas e Épicos (sem changelog)
CREATE TABLE IF NOT EXISTS h_initiatives (
    key TEXT PRIMARY KEY,
    summary TEXT,
    status TEXT,
    issuetype_name TEXT,
    project_key TEXT,
    assignee_name TEXT,
    due_date TEXT,
    created_at TEXT,
    updated_at TEXT,
    resolved_at TEXT,
    children_keys TEXT,             -- JSON array de épicos filhos
    last_synced_at TEXT
);

CREATE TABLE IF NOT EXISTS h_epics (
    key TEXT PRIMARY KEY,
    summary TEXT,
    status TEXT,
    issuetype_name TEXT,
    project_key TEXT,
    assignee_name TEXT,
    due_date TEXT,
    created_at TEXT,
    updated_at TEXT,
    resolved_at TEXT,
    parent_key TEXT,                -- Link para iniciativa (se houver)
    children_keys TEXT,             -- JSON array de stories filhas
    last_synced_at TEXT
);

-- Stories e Sub-tasks (com changelog)
CREATE TABLE IF NOT EXISTS h_stories (
    key TEXT PRIMARY KEY,
    summary TEXT,
    status TEXT,
    issuetype_name TEXT,
    project_key TEXT,
    assignee_name TEXT,
    due_date TEXT,
    created_at TEXT,
    updated_at TEXT,
    resolved_at TEXT,
    parent_key TEXT,                -- Link para épico
    last_synced_at TEXT
);

CREATE TABLE IF NOT EXISTS h_subtasks (
    key TEXT PRIMARY KEY,
    summary TEXT,
    status TEXT,
    issuetype_name TEXT,
    project_key TEXT,
    assignee_name TEXT,
    due_date TEXT,
    created_at TEXT,
    updated_at TEXT,
    resolved_at TEXT,
    parent_key TEXT,                -- Link para story
    last_synced_at TEXT
);

-- Changelogs (apenas stories e subtasks)
CREATE TABLE IF NOT EXISTS h_changelogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_key TEXT,
    project_key TEXT,
    author_name TEXT,
    event_date TEXT,
    field TEXT,
    from_value TEXT,
    to_value TEXT
);

-- Métricas calculadas (apenas stories e subtasks)
CREATE TABLE IF NOT EXISTS h_metrics (
    issue_key TEXT PRIMARY KEY,
    parent_key TEXT,                -- épico da story
    project_key TEXT,
    status TEXT,
    lead_time_ms INTEGER,
    cycle_time_ms INTEGER
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_h_changelogs_issue ON h_changelogs(issue_key, field);
CREATE INDEX IF NOT EXISTS idx_h_stories_parent ON h_stories(parent_key);
CREATE INDEX IF NOT EXISTS idx_h_subtasks_parent ON h_subtasks(parent_key);
CREATE INDEX IF NOT EXISTS idx_h_metrics_parent ON h_metrics(parent_key);
```

### Fluxo de extração (cascata)

```
Entrada: lista de Épico keys OU Iniciativa keys
    │
    ▼
Passo 1: Busca metadados de Iniciativas e Épicos (SEM changelog — rápido)
    JQL: key in (PSADB-1457, PSADB-1500, ...)
    Campos: key, summary, status, issuetype, parent, due_date, assignee, created, updated, resolved
    expand: NENHUM
    │
    ▼
Passo 2: Busca Stories filhas dos Épicos (COM changelog)
    JQL: (parent in (EPIC-1,...) OR linkedissue in (EPIC-1,...)) AND type = Story
    Campos: key, summary, status, project, assignee, created, updated, resolved, due_date, parent, labels
    expand: changelog (embutido na resposta)
    │
    ▼
Passo 3: Busca Sub-tasks das Stories (COM changelog)
    JQL: parent in (STORY-1, STORY-2, ...) AND type = Sub-task
    Campos: mesmos da Story
    expand: changelog
    │
    ▼
Passo 4: Persiste no hierarchy.db
    - h_initiatives / h_epics → apenas metadados
    - h_stories / h_subtasks → metadados + changelogs
    - h_changelogs → transições de status das stories e subtasks
    - Calcula h_metrics (lead time, cycle time) para stories e subtasks
```

### Performance esperada

| Nível | Qtd estimada | Changelog | Tempo estimado |
|-------|-------------|-----------|----------------|
| Iniciativas | 2-5 | Não | <1s |
| Épicos | 5-15 | Não | <1s |
| Stories | 50-200 | Sim (expand) | 3-8s |
| Sub-tasks | 100-500 | Sim (expand ou fetch paralelo) | 5-15s |
| **Total** | | | **~10-25s** |

### Configuração: qual hierarquia extrair

Novo campo no `projects.yaml` ou tabela separada:

```yaml
hierarchy:
  - key: PSADB-1457
    name: "Migration Oracle"
    type: epic
  - key: PSADB-1500
    name: "Performance Improvements"
    type: epic
  - key: INI-100
    name: "Programa de Modernização"
    type: initiative
```

### Entregáveis Onda 1

| # | Item | Arquivo | Status |
|---|------|---------|--------|
| 1.1 | Criar `hierarchy.db` com schema completo (6 tabelas + índices) | `hierarchy_db.py` ou `ingest_hierarchy.py` | [ ] Pendente |
| 1.2 | Extrator hierárquico (cascata de JQLs: sem changelog para épicos e iniciativas, com changelog para stories/subtasks) | `exporter_jira/export_hierarchy.py` | [ ] Pendente |
| **1.2.1** | **CHECKPOINT: Validação humana pós-extração (ver seção abaixo)** | **Parada obrigatória** | [ ] Pendente |
| 1.3 | Cálculo de métricas (lead/cycle time) para stories e subtasks da hierarquia | `metrics/hierarchy_metrics.py` | [ ] Pendente |
| 1.4 | Endpoint: GET /api/hierarchy/tree?key=X (retorna árvore completa) | `api.py` | [ ] Pendente |
| 1.5 | Configuração de hierarquias a extrair | `projects.yaml` (campo `hierarchy`) | [ ] Pendente |
| 1.6 | Endpoint: POST /api/hierarchy/sync (trigger independente) | `api.py` | [ ] Pendente |

### Teste inicial: Iniciativa GPPGI-325

A implementação da Onda 1 deve usar a iniciativa `GPPGI-325` como caso de teste. A cascata esperada:

```
GPPGI-325 (Iniciativa)
    └── Épicos filhos (buscar via parent/linkedissue)
            └── Stories filhas de cada épico (com changelog)
                    └── Sub-tasks de cada story (com changelog)
```

### CHECKPOINT OBRIGATÓRIO — Validação humana pós-extração (após item 1.2)

> **PARADA MANDATÓRIA após o item 1.2:** Uma vez que o extrator hierárquico executou e os dados foram persistidos no `hierarchy.db`, o processo DEVE parar e apresentar ao humano:
>
> 1. **Resumo da extração:**
>    - Quantas iniciativas, épicos, stories e sub-tasks foram encontradas
>    - Distribuição por projeto/time
>    - Distribuição por status
>
> 2. **Amostra dos dados extraídos:**
>    - Árvore hierárquica completa (Iniciativa → Épicos → Stories)
>    - Para cada épico: lista de stories com status e projeto
>    - Confirmar que os links parent estão corretos
>
> 3. **Validação do changelog:**
>    - Amostra de 3-5 stories com suas transições de status
>    - Confirmar que lead time e cycle time fazem sentido
>
> 4. **Perguntas de validação:**
>    - "Os épicos encontrados são os esperados?"
>    - "Faltou algum épico/story que deveria estar?"
>    - "As stories estão ligadas ao épico correto?"
>    - "Os status estão coerentes com o que você vê no Jira?"
>
> **SOMENTE após aprovação explícita do humano**, prosseguir para os itens 1.3 em diante.
>
> Se a validação revelar problemas (links errados, stories faltando, changelog incompleto), corrigir na Onda 1 antes de avançar.

---

## Onda 2 — Epic Health com dados reais

**Objetivo: métricas executivas por Épico com dados da hierarquia**
**Esforço estimado: ~4h**
**Pré-requisito: Onda 1 concluída**

### Métricas por Épico

| Métrica | Cálculo | Fonte |
|---------|---------|-------|
| Progresso (%) | Stories Done / Total Stories | `h_stories` |
| Throughput do Épico | Stories Done/semana (apenas filhas deste épico) | `h_stories.resolved_at` |
| Forecast P85 | Monte Carlo com throughput específico do épico | Mesmo algoritmo do wave2 |
| Risco | Due date vs forecast + progresso + throughput declinante | Composto |
| Lead Time médio das stories | Média de lead_time_ms das filhas Done | `h_metrics` |
| Cycle Time médio | Idem para cycle_time | `h_metrics` |

### Entregáveis Onda 2

| # | Item | Arquivo | Status |
|---|------|---------|--------|
| 2.1 | Página Epic Health (`hierarchy/epic-health.html/js`) | Frontend módulo | [ ] Pendente |
| 2.2 | Throughput por Épico (só filhas dele) | `metrics/hierarchy_metrics.py` | [ ] Pendente |
| 2.3 | Forecast por Épico (Monte Carlo) | Reutiliza lógica existente com dados do hierarchy.db | [ ] Pendente |
| 2.4 | Endpoint: GET /api/hierarchy/epic-health?key=X | `api.py` | [ ] Pendente |
| 2.5 | Dashboard do módulo (`hierarchy/dashboard.html/js`) | Frontend módulo | [ ] Pendente |
| 2.6 | Nav bar interna do módulo | `hierarchy/nav.js` | [ ] Pendente |

---

## Onda 3 — Initiative Health (visão corporativa)

**Objetivo: agregar Épicos por Iniciativa para visão executiva**
**Esforço estimado: ~3h**
**Pré-requisito: Onda 2 concluída**

### Métricas por Iniciativa

| Métrica | Cálculo |
|---------|---------|
| Progresso geral | Épicos Done / Total Épicos |
| Progresso ponderado | Soma(stories Done de todos os épicos) / Soma(total stories) |
| Timeline de épicos | Quando cada épico foi/será entregue |
| Risco corporativo | Composição dos riscos individuais dos épicos |
| Times envolvidos | Projetos distintos que têm stories filhas |

### Entregáveis Onda 3

| # | Item | Arquivo | Status |
|---|------|---------|--------|
| 3.1 | Página Initiative Health (`hierarchy/initiative-health.html/js`) | Frontend módulo | [ ] Pendente |
| 3.2 | Cálculo de métricas agregadas por iniciativa | `metrics/hierarchy_metrics.py` | [ ] Pendente |
| 3.3 | Endpoint: GET /api/hierarchy/initiative-health?key=X | `api.py` | [ ] Pendente |
| 3.4 | Regras de insight para hierarquia | `metrics/insights/rules_hierarchy.py` | [ ] Pendente |

---

## Onda 4 — Timeline visual, Configurações e polish

**Objetivo: árvore visual + aba de configurações do módulo**
**Esforço estimado: ~3h**
**Pré-requisito: Ondas 1-3 concluídas**

### Entregáveis Onda 4

| # | Item | Descrição | Status |
|---|------|-----------|--------|
| 4.1 | Página Timeline (`hierarchy/timeline.html/js`) — árvore collapsible | Frontend módulo | [ ] Pendente |
| 4.2 | Página Configurações (`hierarchy/settings.html/js`) — CRUD + sync + histórico | Frontend módulo | [ ] Pendente |
| 4.3 | Endpoint: CRUD /api/hierarchy/config (add/remove épicos/iniciativas) | `api.py` | [ ] Pendente |
| 4.4 | Endpoint: POST /api/hierarchy/sync + GET /api/hierarchy/sync/status | `api.py` | [ ] Pendente |
| 4.5 | Link "Iniciativas e Épicos" na nav bar do projeto principal | Todas as páginas existentes | [ ] Pendente |
| 4.6 | CSS do módulo (`hierarchy/hierarchy.css`) | Estilo consistente com projeto principal | [ ] Pendente |

---

## Tratamento de cenários especiais

### Story já coletada pela pipeline padrão (issues.db)

```
Extrator hierárquico encontra STN-100 como filha do PSADB-1457
    → Extrai normalmente com changelog
    → Persiste em hierarchy.db (h_stories + h_changelogs)
    → Dados duplicados entre issues.db e hierarchy.db: OK (intencional)
    → Cada banco vive isolado — não se consultam
```

### Story Done >6 meses (purgada do issues.db, mas relevante para o épico)

```
Extrator hierárquico encontra STN-50 (Done há 8 meses)
    → NÃO existe em issues.db (foi purgada)
    → MAS o extrator hierárquico busca da API normalmente (com changelog)
    → Persiste em hierarchy.db como qualquer outra story
    → hierarchy.db NUNCA purga → dado permanece para sempre
    → Progresso do épico: CORRETO (conta STN-50 como Done)
```

### Épico com stories em múltiplos times

```
PSADB-1457 (Épico - tribo)
    ├── STN-100 (Story - San Antonio)  → extraída na hierarchy com changelog
    ├── BL-200 (Story - Belize)        → extraída na hierarchy com changelog
    └── BKA-300 (Story - San Ignacio)  → extraída na hierarchy com changelog

Todas vão para h_stories no hierarchy.db, independente do projeto.
Progresso = cross-project por natureza.
```

### Sync: como ambas as pipelines convivem

```
Botão "Sincronizar" no settings.html:
    1. Roda pipeline padrão (issues.db) — como hoje
    2. Roda pipeline hierárquica (hierarchy.db) — nova, independente
    
    Se a hierárquica falhar:
    → Projeto padrão já completou com sucesso
    → Nenhum impacto nas 8 páginas existentes
    → Apenas a página executive/hierarchy fica desatualizada
```

---

## Decisões de design

| Decisão | Justificativa |
|---------|--------------|
| Banco separado (`hierarchy.db`) | Isolamento total. Pode resetar sem impactar projeto padrão |
| Dados duplicados entre issues.db e hierarchy.db | Volume desprezível (~300-500 issues). Elimina qualquer dependência cruzada |
| Extrator separado (`export_hierarchy.py`) | Fluxo diferente, trigger diferente, sem interferência na sync padrão |
| Cascata de JQLs no extrator | Limitação do Jira — JQL não desce N níveis |
| SEM changelog para Iniciativas e Épicos | Issues de tracking — progresso vem das filhas |
| COM changelog para Stories e Sub-tasks | Precisam de cycle time, lead time, time per status |
| Sem purge no hierarchy.db | Épicos duram 1 ano+ — precisa de histórico completo |
| Configuração de hierarquias é explícita (YAML) | Épicos podem ser de projetos diferentes — precisa saber quais buscar |
| NÃO consulta issues.db para nada | Zero acoplamento. Se um falhar o outro continua |
| Pipeline hierárquica falha silenciosamente | Projeto padrão nunca é afetado por erro na hierarquia |

---

## Impacto no projeto existente

| Componente | Impacto |
|-----------|---------|
| Banco `issues.db` | **ZERO** — não é lido, escrito ou alterado pela pipeline hierárquica |
| Pipeline de sync padrão | **ZERO** — continua independente |
| Métricas Wave 1-4 | **ZERO** — não consultam hierarchy.db |
| Purge do projeto padrão | **ZERO** — purga normalmente, sem verificar hierarquia |
| Endpoints existentes | **ZERO** — novos endpoints são adicionais |
| `projects.yaml` | **Aditivo** — novo campo `hierarchy` (opcional, não quebra se ausente) |
| Frontend páginas existentes | **ZERO** — nova página/seção, não altera as 8 existentes |

---

## Navegação futura (com hierarquia)

A pipeline hierárquica é um **módulo independente** dentro do projeto, com sua própria estrutura de navegação interna — similar a um "sub-projeto" com dashboard, métricas e configurações próprias.

### Navegação principal (nível projeto)

```
Dashboard | Gargalo | Previsibilidade | Pessoas | Portfolio | Insights | Inconsistências | Config | [Iniciativas e Épicos]
                                                                                                          ↓
                                                                                              Abre módulo separado
```

### Navegação interna do módulo "Iniciativas e Épicos"

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ← Voltar ao Projeto Principal                                                  │
│                                                                                 │
│  [Dashboard] [Epic Health] [Initiative Health] [Timeline] [Configurações]       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  Dashboard:                                                                     │
│    - KPIs: Épicos ativos, Stories Done esta semana, Progresso geral             │
│    - Tabela de Épicos com progresso, forecast, risco                            │
│                                                                                 │
│  Epic Health:                                                                   │
│    - Progresso por Épico (% Done, forecast P85, risco)                          │
│    - Throughput por Épico (stories Done/semana)                                 │
│    - Cycle Time / Lead Time das stories do épico                                │
│    - Drill-down: clicar no épico mostra stories com métricas                    │
│                                                                                 │
│  Initiative Health:                                                             │
│    - Progresso por Iniciativa (épicos Done / total)                             │
│    - Timeline: quando cada épico foi/será entregue                              │
│    - Risco corporativo (composição dos riscos dos épicos)                       │
│                                                                                 │
│  Timeline:                                                                      │
│    - Árvore visual: Iniciativa → Épico → Stories (collapsible)                  │
│    - Filtros: por time, por status, por risco                                   │
│                                                                                 │
│  Configurações:                                                                 │
│    - Lista de Épicos/Iniciativas monitorados (CRUD)                             │
│    - Pipeline: JQLs configuráveis por hierarquia                                │
│    - Sync: botão "Sincronizar" independente + status/progresso                  │
│    - Histórico de sincronizações da hierarquia                                  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Páginas do módulo (arquivos)

| Página | Arquivo | Descrição |
|--------|---------|-----------|
| Dashboard | `hierarchy/dashboard.html` | KPIs + tabela de épicos |
| Epic Health | `hierarchy/epic-health.html` | Métricas detalhadas por épico |
| Initiative Health | `hierarchy/initiative-health.html` | Visão corporativa por iniciativa |
| Timeline | `hierarchy/timeline.html` | Árvore hierárquica visual |
| Configurações | `hierarchy/settings.html` | Pipeline, sync, CRUD de épicos/iniciativas |

### Estrutura de arquivos do módulo

```
changelog_timeline/
├── hierarchy/                        # Módulo "Iniciativas e Épicos" (isolado)
│   ├── dashboard.html                # Dashboard do módulo
│   ├── dashboard.js
│   ├── epic-health.html              # Métricas por Épico
│   ├── epic-health.js
│   ├── initiative-health.html        # Métricas por Iniciativa
│   ├── initiative-health.js
│   ├── timeline.html                 # Árvore hierárquica visual
│   ├── timeline.js
│   ├── settings.html                 # Configurações da pipeline hierárquica
│   ├── settings.js
│   ├── hierarchy.css                 # CSS compartilhado do módulo
│   └── nav.js                        # Nav bar interna do módulo
│
├── exporter_jira/
│   └── export_hierarchy.py           # Extrator hierárquico (cascata JQLs)
│
├── metrics/
│   └── hierarchy_metrics.py          # Cálculo de métricas para hierarchy.db
│
└── hierarchy.db                      # Banco isolado do módulo
```

### Configurações do módulo (aba Configurações)

Seguindo o mesmo padrão visual e técnico do `settings.html` existente:

| Seção | Funcionalidade |
|-------|---------------|
| **Hierarquias monitoradas** | Lista de Épicos/Iniciativas com CRUD (adicionar, remover, editar JQL) |
| **Pipeline** | JQLs geradas automaticamente a partir das keys, editáveis manualmente |
| **Sincronização** | Botão "Sincronizar" + status em tempo real (polling) + cancelamento |
| **Histórico** | Tabela de sincronizações anteriores (data, duração, issues, status) |
| **Exclude statuses** | Quais status ignorar na extração (mesma lógica do projeto padrão) |

### Padrão de UI do módulo (espelhando projeto padrão)

| Elemento | Como funciona |
|----------|---------------|
| Nav bar interna | Links entre as 5 páginas do módulo + "← Voltar" |
| Filtro de projeto/épico | Dropdown no topo para selecionar qual épico/iniciativa visualizar |
| Botão "Sincronizar" | Mesmo padrão: POST → polling status → log em tempo real |
| KPI cards | Mesmo visual: glass cards com valor + "O que é?" |
| Tabelas | Mesmo CSS: `metric-table` com hover e badges de risco |
| Gráficos | Chart.js (mesma lib) para throughput e timeline |

---

## Pré-requisitos para implementação

Antes de iniciar, validar:

1. **As stories do Jira usam `parent` ou `linkedissue` para apontar ao Épico?**
   - Testar: `parent in (PSADB-1457) AND type = Story` retorna resultados?
   - Se não: tentar `linkedissue in (PSADB-1457) AND type = Story`
   - A JQL que você já tem (`parent in (...) OR linkedissue in (...)`) sugere que ambos são usados

2. **Qual projeto do Jira contém os Épicos?**
   - Os épicos PSADB-* estão no projeto "PSADB"? Ou é um projeto de tribo separado?

3. **Iniciativas existem como issue type no Jira?**
   - Se sim: qual projeto? Qual issue type name exato?
   - Se não: pular Onda 3 (Initiative Health)

4. **Quantos épicos ativos existem?**
   - Se <50: configuração manual no YAML é viável
   - Se >50: precisa de auto-discovery ou JQL genérica

---

## Histórico de execução

| Data | Onda | Itens feitos | Resultado |
|------|------|-------------|-----------|
| 21/08/2026 | Onda 1 | 1.1, 1.2, 1.2.1 | Schema criado (7 tabelas + 6 índices). Extrator executado com GPPGI-325: 1 ini, 4 épicos, 51 stories, 196 subtasks, 4703 changelogs em 19.4s. Checkpoint humano: APROVADO |

---

## Como usar este documento

1. Validar pré-requisitos (seção acima)
2. Implementar Onda 1 (extração + persistência)
3. Validar dados extraídos (hierarquia correta?)
4. Implementar Ondas 2-4 incrementalmente
5. Atualizar DATASHEET.md após cada onda
