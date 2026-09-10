# Roteiro de Correção — Sprint de Saneamento Técnico

> Baseado na auditoria em `MAPEAMENTO_PROJETO.md`.
> Formato: sprint única com backlog priorizado, critérios de aceite e validação por item.
> Cada item tem: contexto, tarefas, critério de aceite (Definition of Done) e comando/passo de validação.

Data: 10/09/2026
Duração sugerida: 1 sprint (5 dias úteis)
Objetivo da sprint: eliminar código legado quebrado, alinhar dependências, corrigir comportamento de UI inerte e reduzir duplicação de lógica crítica.

---

## Resumo do backlog

| # | Item | Prioridade | Estimativa | Risco | Tipo |
|---|------|-----------|------------|-------|------|
| 1 | `run_pipeline.py` quebrado com YAML atual | 🔴 Alta | 3 pts | Médio | Bug / Legado |
| 2 | Dependências: `openpyxl` + versões pinadas | 🔴 Alta | 2 pts | Alto | Infra |
| 3 | `nav-alerts.js` badge inerte | 🟡 Média | 2 pts | Baixo | Bug UI |
| 4 | Duplicações (Monte Carlo, ACTIVE_STATES, helpers) | 🟡 Média | 5 pts | Médio | Refatoração |
| 5 | Páginas órfãs (`timeline.html`, `dashboard.html`) | 🟢 Baixa | 2 pts | Baixo | Limpeza |

Total: 14 pts.

Ordem de execução recomendada: **2 → 1 → 3 → 4 → 5** (dependências primeiro, pois destravam o ambiente de validação de todos os demais).

---

## Dia 0 — Preparação (pré-sprint)

**Objetivo:** garantir ambiente reproduzível e baseline antes de qualquer mudança.

Tarefas:
- [ ] Criar branch `sprint/saneamento-tecnico` a partir da main.
- [ ] Criar/ativar um virtualenv limpo (`python -m venv .venv`).
- [ ] Rodar o servidor atual e registrar o estado "antes" (páginas que abrem, badge de alertas, sync funcionando).
- [ ] Fazer backup dos bancos: copiar `issues.db` e `hierarchy.db` para `./_backup/`.

Validação do Dia 0:
```powershell
# ambiente limpo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# baseline do servidor
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```
> ⚠️ Se a instalação já falhar aqui, o Item 2 é bloqueante e deve ser o primeiro a ser resolvido.

---

## Item 1 — Corrigir/decidir destino do `run_pipeline.py`

### Contexto
`run_pipeline.py` lê `project.get("jql")` diretamente, mas o `projects.yaml` atual usa a estrutura `pipelines: {active, done, delta}`. Com o YAML atual, `run_extraction` recebe JQL vazia e **pula todos os projetos** — o script está funcionalmente morto. O fluxo real de produção é `_run_sync()` em `api.py`.

### Decisão de rota (escolher UMA)
- **Opção A (recomendada):** Atualizar `run_pipeline.py` para o formato `pipelines`, reaproveitando a mesma lógica de JQL combinada (`OR`) que o `_run_sync` já usa. Mantém um entrypoint CLI válido para automação/cron.
- **Opção B:** Marcar como deprecado (mover para `legacy/` ou adicionar aviso de deprecação e `sys.exit`).

### Tarefas (Opção A)
- [ ] Ler as pipelines de cada projeto e montar a JQL unificada (mesma regra do `_run_sync`: combinar `active`, `done`, `delta` com `OR`).
- [ ] Passar `--exclude-statuses` para o `ingest_to_db.py` a partir do `exclude_statuses` do YAML.
- [ ] Alinhar os argumentos do `export_jira.py` (`--with-changelog`, `--db-cache`).
- [ ] Atualizar docstrings.

### Critério de aceite (DoD)
- Executar `run_pipeline.py --project-key REYK` extrai e ingere issues reais do projeto (issues > 0 no banco para a key).
- Nenhum projeto é pulado por "JQL vazia".
- Comportamento equivalente ao `_run_sync` para um projeto.

### Validação
```powershell
# roda para um único projeto e confere contagem no banco
python run_pipeline.py --project-key REYK
python -c "import sqlite3; c=sqlite3.connect('issues.db'); print('REYK issues:', c.execute(\"SELECT COUNT(*) FROM issues WHERE project_key='REYK'\").fetchone()[0])"
```
> Aceite: contagem > 0 e log sem "Projeto sem JQL definida. Pulando".
> Se Opção B: validar que o script sai com mensagem de deprecação clara e não corrompe nada.

---

## Item 2 — Dependências: `openpyxl` e versões pinadas

### Contexto
- `DATASHEET.md` cita `openpyxl` como pré-requisito e existe `metrics_export.xlsx`, mas `openpyxl` não está em nenhum `requirements.txt`.
- As versões pinadas na raiz parecem à frente do que existe no PyPI (ex.: `fastapi==0.139.2`, `starlette==1.3.1`, `requests==2.34.2`, `pydantic==2.13.4`) — risco de falha de instalação em ambiente limpo.

### Tarefas
- [ ] Buscar no código quem realmente usa `openpyxl` (`import openpyxl` / geração de `.xlsx`). Se usado → adicionar ao `requirements.txt`. Se não → remover a menção do `DATASHEET.md`.
- [ ] Rodar `validate_requirements.ps1` em venv limpo e corrigir cada versão que falhar na resolução (ajustar para a última versão estável real de cada pacote).
- [ ] Padronizar estratégia de pin (decidir entre `==` exato ou `~=`/`>=` compatível) entre raiz e `exporter_jira`.
- [ ] Após ajustar, congelar com `pip freeze` para confirmar o conjunto instalável.

### Critério de aceite (DoD)
- `pip install -r requirements.txt` conclui sem erro em venv limpo.
- `validate_requirements.ps1` sai com código 0.
- Se `openpyxl` é usado, importa sem erro; se não, não é mais citado como dependência.

### Validação
```powershell
# ambiente limpo
python -m venv .venv-test
.\.venv-test\Scripts\Activate.ps1
python -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File .\validate_requirements.ps1
# confirma imports-chave
python -c "import fastapi, uvicorn, starlette, pydantic, yaml, dotenv, requests; print('imports OK')"
# se openpyxl for mantido:
python -c "import openpyxl; print('openpyxl OK')"
```
> Aceite: todos os comandos retornam sucesso; `validate_requirements.ps1` imprime "requirements.txt VALIDADO com sucesso".

---

## Item 3 — `nav-alerts.js`: badge de alertas inerte fora de `insights.html`

### Contexto
`nav-alerts.js` é carregado em ~10 páginas, mas procura `a[href="/insights.html"]` para colar o badge. Só `insights.html` tem esse link — nas demais o seletor retorna `null` e o badge nunca aparece. Efeito: o alerta de saúde do fluxo só é visível justamente onde é menos útil.

### Decisão de rota (escolher UMA)
- **Opção A (recomendada):** Adicionar o link "Insights" na nav de todas as páginas que carregam `nav-alerts.js` (padroniza a navegação — também resolve o Item relacionado do `index.html` desatualizado).
- **Opção B:** Ajustar `nav-alerts.js` para um seletor mais robusto (ex.: um elemento fixo `#nav-insights` ou fallback para um container conhecido) e injetar o badge nele.

### Tarefas (Opção A)
- [ ] Definir a nav canônica (Dashboard | Wave 1 | Wave 2 | Wave 3 | Wave 4 | Insights | Inconsistências | Configurações | Hierarquia).
- [ ] Aplicar a nav em todas as páginas raiz (incluindo `index.html`, que hoje está com set reduzido).
- [ ] Confirmar que `nav-alerts.js` encontra o link e injeta o badge.

### Critério de aceite (DoD)
- O badge de alertas aparece em pelo menos uma página que **não** seja `insights.html` (ex.: dashboard) quando `/api/insights/alert-count` retorna `total > 0`.
- Nenhuma página que carrega `nav-alerts.js` gera erro de console por seletor nulo.

### Validação
```
Manual (browser):
1. Subir servidor com dados que gerem alertas (total > 0).
2. Abrir /dashboard.html → confirmar badge no link "Insights".
3. Abrir DevTools Console → sem erros de nav-alerts.js.
4. Repetir em wave1/wave2/wave3/wave4/settings.
```
```powershell
# checagem prévia da API que alimenta o badge
python -c "import urllib.request,json; print(json.load(urllib.request.urlopen('http://localhost:8000/api/insights/alert-count')))"
```
> Aceite: badge visível fora de insights.html e sem erro de console.

---

## Item 4 — Eliminar duplicações de lógica crítica

### Contexto
Lógica duplicada com risco de drift silencioso:
- **3 implementações de Monte Carlo forecast:** `metrics/wave2_predictability/forecast.py` (10.000 sims), `metrics/wave4_portfolio/epic_health.py::_quick_forecast` (1.000), `metrics/hierarchy_metrics.py::monte_carlo_forecast` (1.000).
- **`ACTIVE_STATES`** hardcoded em `base.py`, `wip.py` (variante) e `api.py`.
- **`STATUS_ORDER` / detecção de transição "para trás"** em `rework.py`, `rules_people.py`, `benchmarking.py`.
- **`_week_to_date_range`** copiado em throughput.py, cross_project.py, rules_flow.py, rules_throughput.py.
- **Extração de texto ADF** duplicada em `jira_mapper.py` e `jira_comments.py`.
- Import morto: `math` em `benchmarking.py`.

### Tarefas
- [ ] Criar módulo `metrics/constants.py` com `ACTIVE_STATES` e `STATUS_ORDER` (documentar a variante do WIP: se Blocked entra ou não).
- [ ] Criar `metrics/common/forecast.py` com uma função Monte Carlo parametrizável (`simulations`, `history_weeks`) e migrar os 3 usos, preservando os defaults atuais de cada chamador (para não mudar resultados).
- [ ] Criar `metrics/common/time_utils.py` com `week_to_date_range` e substituir as 4 cópias.
- [ ] Extrair a extração ADF para uma função compartilhada (parametrizar o limite de truncamento 5000/10000).
- [ ] Remover o import morto `math` em `benchmarking.py`.

### Critério de aceite (DoD)
- Uma única fonte de verdade para ACTIVE_STATES, STATUS_ORDER, Monte Carlo, week_to_date_range e ADF.
- **Sem regressão numérica:** as métricas calculadas para um projeto de referência são idênticas antes/depois (dentro da variância esperada do Monte Carlo — usar `random.seed` fixo no teste).
- Nenhum import quebrado.

### Validação
```powershell
# 1. Snapshot ANTES (rodar antes de refatorar e guardar saída)
python -c "import sqlite3, json; from metrics.wave2_predictability.forecast import monte_carlo_forecast; c=sqlite3.connect('issues.db'); import random; random.seed(42); print(json.dumps(monte_carlo_forecast(c,'REYK',10), sort_keys=True))" > _before_forecast.txt

# 2. Após refatorar: repetir e comparar
python -c "import sqlite3, json; from metrics.wave2_predictability.forecast import monte_carlo_forecast; c=sqlite3.connect('issues.db'); import random; random.seed(42); print(json.dumps(monte_carlo_forecast(c,'REYK',10), sort_keys=True))" > _after_forecast.txt
fc _before_forecast.txt _after_forecast.txt

# 3. Sanidade de imports de todo o pacote
python -c "import metrics.base, metrics.wave1_bottleneck, metrics.wave2_predictability, metrics.wave3_people, metrics.wave4_portfolio, metrics.insights, metrics.hierarchy_metrics; print('todos os imports OK')"

# 4. Recalcular Wave 1 e conferir que não quebrou
python ingest_to_db.py --input-dir output/REYK --db-path issues.db
```
> Aceite: `fc` acusa arquivos idênticos (com seed fixo), todos os imports carregam, e a ingestão conclui sem erro.

---

## Item 5 — Páginas órfãs (`hierarchy/timeline.html`, `hierarchy/dashboard.html`)

### Contexto
- `hierarchy/timeline.html` (+ `timeline.js`): não está na nav (`nav.js`) nem é linkada em lugar nenhum — inalcançável pela UI.
- `hierarchy/dashboard.html` (+ `dashboard.js`): página legada; a nav aponta para `dashboard-v2.html`.

### Decisão de rota (escolher por página)
- Se ainda tem valor → **reconectar** (adicionar link na `nav.js`).
- Se é legado morto → **remover** os arquivos.

### Tarefas
- [ ] Confirmar com o time se `timeline.html` deve virar feature ativa (tem endpoint `/api/hierarchy/tree` funcional) ou ser removida.
- [ ] Confirmar se `dashboard.html` (legado) pode ser removida em favor de `dashboard-v2.html`.
- [ ] Executar a decisão: remover arquivos OU adicionar entradas em `hierarchy/nav.js`.
- [ ] Se remover: garantir que nenhum outro arquivo referencia os removidos (grep por `timeline.html` / `dashboard.js` dentro de `hierarchy/`).

### Critério de aceite (DoD)
- Não existem HTML/JS órfãos em `hierarchy/` (todo arquivo servido é alcançável) OU os mantidos estão na nav.
- Nenhum link quebrado após a mudança.

### Validação
```powershell
# procura referências às páginas antes de remover
Select-String -Path .\hierarchy\*.js, .\hierarchy\*.html, .\*.js, .\*.html -Pattern "timeline.html|hierarchy/dashboard.html|dashboard.js" 
```
```
Manual (browser):
1. Navegar por toda a nav da hierarquia → nenhum 404.
2. Se reconectada: abrir a página via nav e confirmar que carrega dados.
```
> Aceite: nenhuma referência pendente às páginas removidas; navegação sem 404.

---

## Validação final da sprint (Definition of Done global)

Executar ao fim, em venv limpo, antes do merge:

- [ ] `pip install -r requirements.txt` OK em ambiente limpo (Item 2).
- [ ] `validate_requirements.ps1` → exit 0 (Item 2).
- [ ] `run_pipeline.py` (ou seu substituto/deprecação) com comportamento definido e validado (Item 1).
- [ ] Servidor sobe (`uvicorn api:app`) sem erro e todas as páginas da nav abrem sem 404 (Itens 3 e 5).
- [ ] Badge de alertas visível fora de `insights.html` (Item 3).
- [ ] Snapshot de métricas idêntico antes/depois com seed fixo (Item 4).
- [ ] `python -c "import ..."` de todos os pacotes `metrics.*` sem erro (Item 4).
- [ ] Console do browser sem erros nas páginas principais.
- [ ] Atualizar `DATASHEET.md` e `MAPEAMENTO_PROJETO.md` refletindo as correções.
- [ ] Limpar arquivos temporários de validação (`_before_forecast.txt`, `_after_forecast.txt`, venvs de teste).

### Checklist de PR
- [ ] Branch `sprint/saneamento-tecnico` com commits atômicos por item.
- [ ] Descrição do PR lista cada item, decisão de rota tomada e evidência de validação.
- [ ] Bancos de produção não versionados/alterados indevidamente.
- [ ] Sem `--force`, sem alteração de git config.

---

## Riscos e mitigações

| Risco | Mitigação |
|-------|-----------|
| Versões corrigidas do requirements introduzem breaking change (ex.: Pydantic v1→v2) | Testar subida do servidor e endpoints-chave após ajuste; ler changelog dos pacotes major |
| Refatoração do Monte Carlo altera resultados | Validação com `random.seed` fixo e comparação byte a byte |
| Remoção de página órfã que ainda é usada por link externo/bookmark | Confirmar com o time antes de remover; manter em `legacy/` por 1 release se houver dúvida |
| Mudança na nav quebra layout/CSS | Testar visualmente cada página após padronizar a nav |
