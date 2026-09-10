# Melhorias v2 — Insights Automaticos e Metricas Avancadas

Data de criacao: 19/08/2026
Status geral: Concluido (itens pendentes menores documentados abaixo)

---

## Contexto

Com a pipeline otimizada (v1: 306.5s -> 8.2s) e Wave 1 completa (percentis, CFD, flow efficiency, aging WIP), o proximo passo foi expandir o sistema de metricas com analises automaticas e novas dimensoes de observabilidade.

### Objetivo

Transformar o dashboard de "visualizacao passiva" para "diagnostico ativo" — o sistema detecta padroes, anomalias e gera recomendacoes acionaveis automaticamente.

### Estrutura de entrega

| Wave | Tema | Pagina | Status |
|------|------|--------|--------|
| Engine de Insights | Analise automatica de todas as waves | `insights.html` | Concluido |
| Wave 2 | Previsibilidade (Throughput + Monte Carlo) | `wave2.html` | Concluido |
| Wave 3 | Pessoas e Qualidade (WIP, carga, retrabalho) | `wave3.html` | Concluido |
| Wave 4 | Cross-time e Portfolio (dependencias, epicos) | `wave4.html` | Concluido |
| Alertas Proativos | Flags automaticos integrados ao Insights | `insights.html` | Concluido |

---

## Onda 1 — Engine de Insights + Diagnostico de Fluxo

**Status: Concluido**

### Arquitetura

```
metrics/insights/
├── __init__.py              # run_insights(conn, project_key) -> dict
├── engine.py                # Classe InsightsEngine: registra rules, executa, categoriza
├── rules_flow.py            # 8 regras de diagnostico de fluxo (Wave 1)
├── rules_throughput.py      # 4 regras de previsibilidade (Wave 2)
├── rules_people.py          # 4 regras de pessoas (Wave 3)
├── rules_portfolio.py       # 3 regras de portfolio (Wave 4)
└── rules_alerts.py          # 5 alertas proativos (Onda 5)
```

### Categorias de insight

| Severidade | Significado | Cor |
|-----------|-------------|-----|
| critical | Requer acao imediata | Vermelho |
| warning | Tendencia negativa ou anomalia | Amarelo |
| info | Observacao relevante | Azul |
| healthy | Indicador positivo | Verde |

### Regras implementadas — Diagnostico de Fluxo (8)

| # | Item | Regra | Status |
|---|------|-------|--------|
| 1.1 | Picos de Lead Time | Lead Time P85 semanal > 3x mediana historica | [x] Concluido |
| 1.2 | Tendencia Lead Time | P85 crescente por 3+ semanas consecutivas | [x] Concluido |
| 1.3 | Tendencia Cycle Time | P85 crescente por 3+ semanas | [x] Concluido |
| 1.4 | Gap Lead/Cycle | Ratio lead/cycle > 5x | [x] Concluido |
| 1.5 | Volatilidade Lead Time | Coeficiente de variacao > 1.0 | [x] Concluido |
| 1.6 | Cycle Time estavel | CV < 30% por 4+ semanas | [x] Concluido |
| 1.7 | Flow Efficiency baixa | Efficiency media < 15% | [x] Concluido |
| 1.8 | Gargalo identificado | Status com P85 > 2x o segundo maior | [x] Concluido |

### Entregaveis

| # | Item | Arquivo | Status |
|---|------|---------|--------|
| 1.A | Criar InsightsEngine (base modular) | `metrics/insights/engine.py` | [x] Concluido |
| 1.B | Implementar regras de fluxo | `metrics/insights/rules_flow.py` | [x] Concluido |
| 1.C | Endpoint GET /api/insights?project_key=X | `api.py` | [x] Concluido |
| 1.D | Pagina insights.html com navegacao | `insights.html/js/css` | [x] Concluido |
| 1.E | Adicionar link na nav bar | Todos os HTMLs | [x] Concluido |

---

## Onda 2 — Wave 2: Previsibilidade

**Status: Concluido (exceto SLA)**

### Metricas

| # | Item | Descricao | Status |
|---|------|-----------|--------|
| 2.1 | Throughput semanal | Issues Done por semana, por projeto. Grafico de barras + tendencia | [x] Concluido |
| 2.2 | Throughput por tipo | Separado por issue type (Story, Task, Bug, Sub-task) | [x] Concluido |
| 2.3 | Monte Carlo Forecast | Simulacao: dado N itens restantes + throughput historico, quantas semanas com X% confianca | [x] Concluido |
| 2.4 | SLA por tipo de issue | Configuravel (ex: Bug = 5d, Story = 14d). Alerta de estouro | [ ] Pendente |
| 2.5 | Aging backlog | Issues abertas ha mais de N dias sem atividade | [x] Concluido |

### Entregaveis

| # | Item | Arquivo | Status |
|---|------|---------|--------|
| 2.A | Modulo metrics/wave2_predictability/ | Novo diretorio | [x] Concluido |
| 2.B | calculate_throughput(conn, project_key) | `throughput.py` | [x] Concluido |
| 2.C | monte_carlo_forecast(throughput_history, remaining_items, simulations=10000) | `forecast.py` | [x] Concluido |
| 2.D | Endpoints Wave 2 | `api.py` | [x] Concluido |
| 2.E | Pagina wave2.html | `wave2.html/js/css` | [x] Concluido |
| 2.F | Regras de insight (throughput) | `metrics/insights/rules_throughput.py` | [x] Concluido |

---

## Onda 3 — Wave 3: Pessoas e Qualidade

**Status: Concluido**

### Metricas

| # | Item | Descricao | Status |
|---|------|-----------|--------|
| 3.1 | WIP por pessoa | Qtd de issues simultaneas em estados ativos (In Progress, Test), por assignee | [x] Concluido |
| 3.2 | Distribuicao de carga | Issues Done por pessoa (Gini coefficient + bus factor) | [x] Concluido |
| 3.3 | Handoff time | Tempo entre mudancas de assignee. Mede atraso em transferencias | [x] Concluido |
| 3.4 | Taxa de reabertura | Issues que voltaram de Done/estado avancado para estado anterior | [x] Concluido |
| 3.5 | Retrabalho em tempo | Lead time de ciclos que "voltaram" vs ciclos lineares | [x] Concluido |

### Cuidado etico

> Estas metricas SAO para identificar riscos organizacionais (bus factor, multitasking, gargalo de handoff).
> NAO SAO para ranking individual de performance.
> Usar para: redistribuir carga, identificar quem precisa de apoio, reduzir riscos.

### Entregaveis

| # | Item | Arquivo | Status |
|---|------|---------|--------|
| 3.A | Modulo metrics/wave3_people/ | Novo diretorio | [x] Concluido |
| 3.B | calculate_wip_per_person(conn, project_key) | `wip.py` | [x] Concluido |
| 3.C | calculate_workload_distribution(conn, project_key) | `workload.py` | [x] Concluido |
| 3.D | calculate_handoff_time(conn, project_key) | `handoff.py` | [x] Concluido |
| 3.E | calculate_rework_rate(conn, project_key) | `rework.py` | [x] Concluido |
| 3.F | Endpoints Wave 3 | `api.py` | [x] Concluido |
| 3.G | Pagina wave3.html | `wave3.html/js/css` | [x] Concluido |
| 3.H | Regras de insight (pessoas) | `metrics/insights/rules_people.py` | [x] Concluido |

---

## Onda 4 — Wave 4: Cross-time e Portfolio

**Status: Concluido (exceto mapa de dependencias)**

### Metricas

| # | Item | Descricao | Status |
|---|------|-----------|--------|
| 4.1 | Mapa de dependencias | Issues bloqueadas aguardando outro time (via parent_key ou labels) | [ ] Pendente |
| 4.2 | Benchmarking normalizado | Comparacao de lead/cycle entre projetos, normalizado por tipo de issue | [x] Concluido |
| 4.3 | Issue-pai health | % concluido, previsao de termino, risco por issue-pai (parent_key) | [x] Concluido |
| 4.4 | Cross-project throughput | Throughput consolidado todos os projetos | [x] Concluido |

### Entregaveis

| # | Item | Arquivo | Status |
|---|------|---------|--------|
| 4.A | Modulo metrics/wave4_portfolio/ | Novo diretorio | [x] Concluido |
| 4.B | Endpoints Wave 4 | `api.py` | [x] Concluido |
| 4.C | Pagina wave4.html | `wave4.html/js/css` | [x] Concluido |
| 4.D | Regras de insight (portfolio) | `metrics/insights/rules_portfolio.py` | [x] Concluido |

---

## Onda 5 — Alertas Proativos

**Status: Concluido (exceto SLA)**

### Alertas

| # | Item | Regra | Status |
|---|------|-------|--------|
| 5.1 | Issue parada | Status inalterado ha mais de 14 dias | [x] Concluido |
| 5.2 | Issue sem assignee | Em estado ativo sem responsavel | [x] Concluido |
| 5.3 | Throughput caindo | Queda >30-50% nas ultimas 2 semanas vs media | [x] Concluido |
| 5.4 | SLA estourando | Issue ativa se aproximando do limite (80% do SLA) | [ ] Pendente |
| 5.5 | Issue-pai em risco | Due date vencida com itens pendentes | [x] Concluido |
| 5.6 | WIP explosion | WIP total >3x throughput semanal | [x] Concluido |

### Entregaveis

| # | Item | Arquivo | Status |
|---|------|---------|--------|
| 5.A | Regras de alertas | `metrics/insights/rules_alerts.py` | [x] Concluido |
| 5.B | Secao de alertas no insights.html | `insights-page.js` | [x] Concluido |
| 5.C | Badge de alertas na nav bar | Todos os HTMLs + `nav-alerts.js` | [x] Concluido |

---

## Itens pendentes para futuro

Itens que dependem de configuracao de negocio ou dados adicionais:

| Item | Onda | Descricao | Pre-requisito |
|------|------|-----------|---------------|
| 2.4 | Onda 2 | SLA por tipo de issue | Definir thresholds por tipo (ex: Bug=5d, Story=14d, Task=7d). Criar tabela de config + UI em settings.html |
| 4.1 | Onda 4 | Mapa de dependencias entre times | Depende de campo "blocked by" ou labels especificos no Jira. Verificar se existe nos dados |
| 5.4 | Onda 5 | Alerta SLA estourando | Depende do item 2.4 estar implementado |

### Como implementar SLA (quando decidido):

1. Criar tabela `sla_config` (issue_type, max_days, project_key)
2. Endpoint CRUD em `/api/settings/sla`
3. UI em settings.html para configurar thresholds
4. Regra em `rules_alerts.py`: compara cycle_time atual vs SLA configurado
5. Frontend wave2.html: destaca issues acima do SLA

### Como implementar mapa de dependencias:

1. Verificar se campo `blocked_by` existe no changelog ou se labels de bloqueio sao usadas
2. Se existir: criar `dependencies.py` que mapeia bloqueios cross-project
3. Visualizacao: grafo ou tabela de dependencias entre times

---

## Decisoes de design

| Decisao | Justificativa |
|---------|--------------|
| Engine modular com regras separadas por arquivo | Facil adicionar novas regras sem tocar no core |
| Insights calculados on-the-fly (nao persistidos) | Dados mudam a cada sync; cache seria complicado e stale |
| Pagina unica de Insights (nao uma por wave) | Visao consolidada > navegacao fragmentada |
| Monte Carlo no backend (Python) | Precisa de simulacao estatistica; JS seria lento para 10k iteracoes |
| Alertas como subset dos insights (category = "alert") | Reutiliza a mesma engine; nao duplica logica |
| Metricas de pessoas sem ranking individual | Principio etico: mede sistema, nao pessoa |
| Issue type dinamico (nao hardcodar "epico") | Projetos usam tipos diferentes — Stories como parents, etc. |
| Badge de alertas na nav bar | Visibilidade imediata sem precisar entrar na pagina de insights |

---

## Navegacao final

```
Dashboard | Gargalo e Fluxo | Previsibilidade | Pessoas | Portfolio | Insights [badge] | Inconsistencias | Configuracoes
```

---

## Resumo de entrega

| Metrica | Valor |
|---------|-------|
| Paginas criadas | 4 (insights, wave2, wave3, wave4) |
| Endpoints novos | 12 |
| Regras de insight | 24 (8 fluxo + 4 throughput + 4 pessoas + 3 portfolio + 5 alertas) |
| Modulos Python | 4 packages (insights, wave2, wave3, wave4) com 14 arquivos |
| Frontend | 4 HTML + 5 JS + 4 CSS + nav-alerts.js |
| Badge dinamico | Em todas as 8 paginas |

---

## Historico de execucao

| Data | Onda | Itens feitos | Resultado |
|------|------|-------------|-----------|
| 19/08/2026 | Onda 1 | 1.A a 1.E (todos) | Engine modular + 8 regras de fluxo + endpoint + pagina insights.html + nav bar atualizada |
| 19/08/2026 | Onda 2 | 2.A a 2.F (todos exceto SLA) | Throughput semanal + Monte Carlo Forecast + Aging Backlog + 4 regras insight + pagina wave2.html |
| 19/08/2026 | Onda 3 | 3.A a 3.H (todos) | WIP por pessoa + Distribuicao de carga (Gini/bus factor) + Handoff time + Retrabalho + 4 regras insight + pagina wave3.html |
| 19/08/2026 | Onda 4 | 4.A a 4.D (todos exceto mapa de dependencias) | Issue-pai Health + Benchmarking cross-project + Throughput consolidado + 3 regras insight + pagina wave4.html |
| 19/08/2026 | Onda 5 | 5.A a 5.C (todos exceto SLA) | 5 regras de alertas proativos + banner destacado no insights + badge dinamico na nav bar de todas as paginas |

---

## Como usar este documento

1. Para itens pendentes, consulte a secao "Itens pendentes para futuro"
2. Para adicionar novas regras de insight, consulte o DATASHEET.md secao "Adicionar novas regras"
3. Para adicionar nova Wave, consulte o DATASHEET.md secao "Adicionar Nova Wave de Metricas"
