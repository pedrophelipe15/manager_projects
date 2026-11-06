# Estudo — Modularização da plataforma (módulos plugáveis)

> Status: **proposta para decisão** — nenhuma implementação feita.
> Data: 06/11/2026. Base: código atual após a divisão do `api.py` em `routers/` e `core/`.

## 1. Objetivo

Transformar a aplicação em uma **plataforma com módulos independentes**, onde cada módulo:

1. pode ser **ligado/desligado** sem afetar os demais;
2. **não quebra a plataforma** se falhar ao carregar;
3. segue um **contrato único**, para que módulos futuros entrem do mesmo jeito.

Módulos atuais (hoje não existem formalmente, só por convenção de pasta):

| Módulo | O que contém hoje |
|---|---|
| **flow** (dashboards) | Minha Visão, Compromisso, Maturidade, Waves 1–5, Dashboard, Insights, Inconsistências, Settings de projetos/blacklist/purge. Banco `issues.db`. |
| **hierarchy** | Iniciativa → Épico → Story: dashboard-v2, roadmap, timeline, pendências, epic/initiative health, settings. Banco `hierarchy.db`. Pasta `hierarchy/`. |

## 2. Diagnóstico — onde os módulos se tocam hoje

A boa notícia: o acoplamento é **pequeno e concentrado**. O banco já é isolado (`issues.db` × `hierarchy.db`) e **flow quase não conhece hierarchy**.

### 2.1 flow → hierarchy (quase nada)

| Ponto | Onde | Impacto se hierarchy sumir |
|---|---|---|
| Link "Hierarquia" no menu | `nav.js:53` | Link quebrado (404) |
| Link "Hierarquia" | `visao-projeto.html:139` | Link quebrado |

Nenhum endpoint, tabela ou métrica de flow usa dados de hierarchy.

### 2.2 hierarchy → flow (onde está o acoplamento real)

| # | Acoplamento | Onde | Gravidade |
|---|---|---|---|
| A | **`projects.yaml` compartilhado.** Chaves `projects:` (flow), `hierarchy:` e `excluded_projects:` (hierarchy) no mesmo arquivo, com leitura-modificação-escrita sem lock em 3 lugares (`routers/projects.py` `_save_projects`, `routers/hierarchy_config.py`) | `projects.yaml`, `routers/hierarchy_config.py`, `metrics/hierarchy_metrics.py:29` | **Alta** — risco de um módulo sobrescrever a config do outro (race) |
| B | **Imports entre routers.** `hierarchy_common`, `hierarchy_config`, `hierarchy_sync` importam `PROJECTS_YAML`/`EXPORTER_DIR` de `routers.projects` (flow) | `routers/hierarchy_*.py` | **Alta** — desligar flow quebra hierarchy no import |
| C | **Efeito colateral no import.** `hierarchy_db.py:172` chama `setup_hierarchy_db()` ao importar; `core/db_init.py` cria tabelas de flow ao importar | `hierarchy_db.py`, `core/db_init.py` | **Média** — módulo "desligado" ainda cria banco/tabelas |
| D | **Código compartilhado sem dono.** `metrics/forecast_core.py` (Monte Carlo) usado por flow e hierarchy; `exporter_jira/` (`jira_client`, mapper) usado pelos dois; `metrics/constants.py`, `timeutils.py` | `metrics/`, `exporter_jira/` | **Média** — hoje funciona, mas não há fronteira |
| E | **Front compartilhado.** `hierarchy/*.html` usam `../tokens.css`, `../nav.css`, `../dashboard.css` (design system) | `hierarchy/*.html` | **Baixa** — é o design system, deve virar "plataforma" |
| F | **Nav duplicada.** `nav.js` (flow, hardcoded) e `hierarchy/nav.js` (hardcoded) | ambos | **Média** — hoje cada módulo desenha seu menu; módulo novo exigiria editar o menu dos outros |
| G | **Rota fora do namespace.** `/api/settings/excluded-projects` é de hierarchy, mas mora em `/api/settings/` | `routers/hierarchy_config.py` | **Baixa** |
| H | **Sync duplicado.** Cada módulo tem seu próprio `sync_state` + `Lock` + subprocess (`routers/projects.py`, `routers/hierarchy_sync.py`) | idem | **Média** — mesmo padrão copiado; vira terceira cópia no próximo módulo |
| I | **Schema do banco espalhado e sem versão.** `issues.db` é criado em ~8 pontos (`core/db_init.py`, `ingest_to_db.py`, métricas Wave 1 e 5, que criam a própria tabela ao calcular); `hierarchy.db` em `hierarchy_db.py`. Sem `schema_version`, sem migrações; instalação nova sobe com `issues.db` incompleto até o primeiro sync | vários | **Alta** — impede instalação limpa e evolução de schema (ver §3.5) |

## 3. Arquitetura proposta

> Nota de nomenclatura: o pacote do núcleo se chama `kernel/` (e não `platform/`) para não colidir com o módulo `platform` da biblioteca padrão do Python. Os **URLs** `/platform/…` e `/api/platform/…` podem permanecer.

### 3.1 Camadas

```
changelog_timeline/
├── kernel/                   # núcleo da plataforma: nunca depende de módulo
│   ├── app_factory.py        # monta FastAPI, middleware, carrega módulos
│   ├── registry.py           # descobre, valida e liga/desliga módulos
│   ├── module_base.py        # contrato (Module / manifest)
│   ├── config_store.py       # YAML por seção, com lock e escrita atômica
│   ├── jobs.py               # JobRunner genérico (sync/recalc: estado, lock, cancel)
│   ├── jira/                 # jira_client, mapper (hoje exporter_jira/)
│   ├── shared/               # forecast_core, timeutils, constants
│   └── static/               # tokens.css, nav.css, ui.*, context.js, nav.js (dinâmico)
├── modules/
│   ├── flow/                 # manifest + routers + metrics + ingest + static + db
│   └── hierarchy/
├── config/
│   └── modules.yaml          # quais módulos estão ligados
└── api.py                    # só chama kernel.app_factory
```

**Regras de dependência** (verificadas automaticamente em CI com `import-linter`):

- `modules/*` pode importar `kernel/*`;
- `kernel/*` **nunca** importa `modules/*`;
- `modules/A` **nunca** importa `modules/B`. Se precisar de algo do outro, declara `requires` e usa um serviço exposto pela plataforma.

### 3.2 Contrato do módulo (manifest)

Cada módulo expõe um objeto descrevendo tudo que ele traz. Exemplo:

```python
# modules/hierarchy/module.py
from kernel.module_base import Module, NavItem

module = Module(
    id="hierarchy",
    name="Hierarquia",
    version="1.0.0",
    requires=[],                         # ex.: um módulo futuro que use hierarchy -> ["hierarchy"]
    routers=["modules.hierarchy.routers"],   # APIRouters (prefixo /api/hierarchy)
    static_dir="modules/hierarchy/static",   # servido em /hierarchy/
    nav=[NavItem("Hierarquia", "/hierarchy/dashboard-v2.html", order=20)],
    config_section="hierarchy",          # seção própria no ConfigStore
    on_enable=setup_hierarchy_db,        # cria banco/tabelas SÓ se ligado
    on_disable=None,
    health=check_hierarchy_db,           # usado no painel de módulos
)
```

O que a plataforma faz com isso:

| Etapa | Comportamento |
|---|---|
| Descoberta | Lê `config/modules.yaml`, importa **somente** os módulos ligados (import dinâmico). |
| Validação | Checa `requires` (liga/recusa se faltar dependência) e conflitos de rota. |
| Isolamento | Falha no import ou no `on_enable` de um módulo → módulo fica `failed`, **os outros sobem normalmente**; erro aparece no painel. |
| Rotas | Inclui os routers do módulo; desligado = rota **não existe** (404). |
| Estáticos | Serve `static_dir` em `/<id>/`; desligado = 404. |
| Menu | `GET /api/platform/modules` devolve módulos ligados + itens de menu; `nav.js` renderiza dinamicamente. Acabam os links hardcoded. |
| Banco | `on_enable` roda migrações do próprio banco; módulo desligado não cria nada. |
| Jobs | Sync/recalc registrados via `JobRunner`; módulo desligado não agenda nem executa. |

### 3.3 Configuração

- `config/modules.yaml`:
  ```yaml
  modules:
    flow:           { enabled: true }
    hierarchy:      { enabled: true }
  ```
- `projects.yaml` deixa de ser compartilhado: cada módulo tem sua **seção** acessada via `ConfigStore.section("hierarchy")`, com lock de arquivo e escrita atômica (resolve o item A). Leitura mantém compatibilidade com o formato atual durante a transição.

### 3.4 Frontend

- Design system (`tokens.css`, `nav.css`, `ui.*`, `context.js`) vira **assets da plataforma**, servidos em `/platform/` e referenciados por todos os módulos.
- Menu único e dinâmico (um `nav.js`), alimentado por `/api/platform/modules`.
- URLs atuais são mantidas: hierarchy continua em `/hierarchy/...`; flow continua na raiz (`/wave1.html`), para não quebrar favoritos.

### 3.5 Instalação, bancos e ativação de módulos

**Bancos:** um banco por módulo (`issues.db` = flow, `hierarchy.db` = hierarchy, futuros módulos seguem igual). Dados da própria plataforma, se houver (estado dos módulos), vão para um `kernel.db` pequeno. Sem JOIN entre bancos de módulos — preserva o isolamento.

**O que vai para o git:** código, nunca o `.db`.
- `.gitignore`: `*.db`, `*.db-wal`, `*.db-shm`.
- Cada módulo traz **migrações numeradas** (`migrations/001_init.sql`, `002_...`) + tabela `schema_version` no próprio banco, e um `seed/` versionado para dados iniciais (ex.: regras de validação padrão).
- O `on_enable` do módulo cria o banco se não existir e aplica as migrações pendentes. O mesmo caminho serve para instalação nova e para atualizar banco em uso.
- Toda tabela do módulo (inclusive as de métricas, hoje criadas durante o cálculo) passa a ser criada pelas migrações, nunca pelo código de negócio.

**Dependências Python:** cada módulo tem seu `requirements.txt`; o setup instala só os dos módulos ligados.

**Instalação (pessoa nova):** `setup.ps1` (ou `python -m kernel.cli init`):
1. cria venv e instala dependências do kernel;
2. gera `.env` (credenciais Jira) e `config/modules.yaml` a partir de exemplos;
3. pergunta quais módulos ligar e instala as dependências deles;
4. roda `on_enable` de cada módulo (cria bancos + migrações + seed);
5. valida `requires` e testa a conexão com o Jira; imprime resumo.

Projetos e hierarquias (dados de configuração, dependem de chaves do Jira) são cadastrados depois, pelas telas de settings de cada módulo.

**Adicionar módulo depois:** por **script** — `python -m kernel.cli enable <modulo>` (valida `requires`, instala dependências, roda migrações, atualiza `modules.yaml`, avisa do reinício). Também `disable` e `status`. A tela de módulos (fase 7) começa **somente leitura** (status/erros); o toggle pela tela só depois de existir autenticação, pois altera o que roda no servidor.

## 4. Decisões que precisam do seu aval

### D1 — Como ligar/desligar

| Opção | Como funciona | Prós | Contras |
|---|---|---|---|
| **A. Arquivo + reinício** (recomendada p/ fase 1) | Edita `config/modules.yaml` e reinicia o serviço | Simples, robusto, rota realmente some, import isolado | Exige reinício |
| **B. Em tempo de execução** | Botão na tela; um *gate* (middleware) responde 404/503 por prefixo de módulo | Sem reinício | FastAPI não remove rotas já registradas; módulo precisa estar carregado, perde parte do isolamento de import |
| **C. Híbrida** | A no boot + B para pausar um módulo carregado | Melhor dos dois | Mais complexidade |

**Recomendação:** começar com **A**, desenhando o registry para aceitar **B/C** depois sem retrabalho.

### D2 — Granularidade do módulo "flow"

Hoje é um bloco só (Waves 1–5, Insights, Inconsistências, Minha Visão, Settings). Opções: manter um módulo `flow` (recomendado agora) ou já quebrar em `flow-core`, `commitment` (Wave 5), `insights`. Dá para quebrar depois sem mudar o contrato.

### D3 — Layout físico das pastas

Mover tudo para `modules/<id>/` (limpo, mais diff) **ou** manter arquivos onde estão e só adicionar o manifest apontando para eles (menos risco, fronteira menos visível). Recomendação: **migrar em etapas** — manifest primeiro, mover pastas depois.

## 5. Plano de implementação (fases)

Cada fase termina com a app funcionando e o OpenAPI idêntico (mesma verificação usada na divisão do `api.py`).

| Fase | Entrega | Resolve | Risco |
|---|---|---|---|
| **0. Rede de segurança** ✅ *concluída em 06/11/2026* | `tests/`: snapshot do OpenAPI + smoke das 49 rotas GET + fixture que cria o banco pelo pipeline real de ingestão + testes de funções puras (65 testes). Caminhos de banco/yaml configuráveis por env | pré-requisito | Baixo |
| **1. Plataforma mínima** ✅ *concluída em 06/11/2026* | `kernel/` (`Module`, `Registry`, `create_app`); `api.py` usa o registry; manifests de `flow` e `hierarchy` em `modules/*/module.py` apontando para `routers/`; `config/modules.yaml`; rota `GET /api/platform/modules`. Liga/desliga por arquivo + reinício (D1 = A). Falha em um módulo não derruba os demais. 78 testes passando. **Ainda não resolvido:** estáticos `/hierarchy/*` seguem servidos com o módulo desligado (fase 5); `hierarchy_db` cria o banco no import (fase 2); hierarchy ainda importa de `routers.projects` (fase 4) | Estrutura, B (parcial) | Baixo |
| **2. Bancos: migrações + `on_enable`** ✅ *concluída em 06/11/2026 — `kernel/migrations.py`; `modules/{flow,hierarchy}/migrations/` (001 baseline, 002 colunas legadas, 003 seed só no flow); `core/db_init.py` removido; `hierarchy_db` não cria mais no import; módulo desligado não cria seu banco; schema gerado == legado (golden) e adoção validada em cópia do `issues.db` local (5.000 issues preservadas). 122 testes. Pendente: DATASHEET ainda cita `setup_table`/`setup_db`; o seed deixou de rodar a cada restart* — Consolidar a criação de tabelas de cada banco em migrações numeradas por módulo (`schema_version`, `seed/`); `setup_hierarchy_db` e `core/db_init` viram `on_enable`; tabelas de métricas deixam de ser criadas durante o cálculo; `*.db` no `.gitignore` | C, I | **Médio** — tem que reproduzir o schema atual exatamente; validar comparando o schema de um banco existente com o gerado pelas migrações |
| **3. ConfigStore** ✅ *concluída em 06/11/2026 — `kernel/config_store.py` (lock thread+processo, escrita atômica, `.bak`, arquivo inválido nunca sobrescrito, seções que só gravam as chaves que possuem); `modules/flow/config.py` (`projects`) e `modules/hierarchy/config.py` (`hierarchy`, `excluded_projects`); duplicata/404 checados sob lock; rota canônica `/api/hierarchy/excluded-projects` (a antiga segue como deprecated). Formato do `projects.yaml` mantido. Decisão: NÃO dividi o arquivo fisicamente (sem ganho agora, risco em arquivo real); seções são lógicas.* — Seções por módulo, lock + escrita atômica; migra `hierarchy:` e `excluded_projects:` | A, G (alias da rota antiga) | **Médio** — mexe em arquivo de produção; fazer backup e manter leitura compatível |
| **4. Quebrar imports cruzados** ✅ *concluída em 06/11/2026 — `kernel/paths.py` (BASE_DIR, EXPORTER_DIR), `kernel/shared/` (constants, timeutils, forecast_core), `kernel/jira/` (client, mapper, comments; credenciais continuam em `exporter_jira/.env`), `hierarchy_db.py` → `modules/hierarchy/db.py`; `.importlinter` (3 contratos) + `tests/test_architecture.py` (inclui teste negativo, cobertura de arquivos novos e prova em runtime: flow desligado não importa código do flow, e vice-versa). Limites: `ingest_to_db.py` (script solto) fica fora do grafo do linter; a fronteira ainda é por lista de arquivos até a fase 8.* — Constantes (`PROJECTS_YAML`, `EXPORTER_DIR`) e `forecast_core`, `jira_client` vão para `kernel/`; `import-linter` no CI | B, D | Médio |
| **5. Menu dinâmico e estáticos por módulo** ✅ *concluída em 06/11/2026 — `NavItem(group, group_order, order)`, `Module.home/static_dirs/static_root`; `GET /api/platform/modules` devolve `menu`; `nav.js` único e dinâmico (sem páginas fixas); `kernel/static.py` com `StaticPolicy` (assets da plataforma sempre; `/hierarchy/*` só com hierarchy ligada; raiz só com flow ligado); `/` redireciona p/ a home do 1º módulo ligado; "VOLTAR" da hierarquia → `/`. Decisão: URLs mantidas (sem `/platform/`) e arquivos físicos no lugar até a fase 8; `dashboard.css` virou asset da plataforma por ser usado pela hierarquia. 152 testes; menu e assets conferidos no navegador.* — `/api/platform/modules`, `nav.js` único, design system em `/platform/`, 404 para módulo desligado | E, F | Médio (front) |
| **6. JobRunner** ✅ *concluída em 06/11/2026 — `kernel/jobs.py`; os 3 jobs (sync do flow, recálculo Wave 1, sync da hierarquia) migrados; formato das rotas de status mantido. Ganhos: início atômico (antes: janela de corrida entre checar `running` e a thread marcá-lo), `running` já verdadeiro na resposta do POST, e exceção inesperada não trava mais o job em "rodando" (antes só reiniciando o servidor — bug reproduzido por teste antes da migração). Testes de caracterização escritos ANTES e mantidos (`test_jobs_endpoints.py`) + `test_job_runner.py`; 173 testes.* — Sync de flow e hierarchy migram para o mesmo runner | H | Médio |
| **7. Painel de módulos** ✅ *concluída em 06/11/2026 — página `/modules.html` (plataforma, sempre servida; item "Módulos" no grupo "Plataforma" do menu): estado (ligado/desligado/falhou), versão, dependências, saúde (arquivo do banco + versão do schema) e causa da falha de carga; somente leitura (liga/desliga continua por `config/modules.yaml` + reinício, D1 = A). Saúde sem caminho absoluto do servidor (teste). Achado: `off:`/`on:`/`yes:`/`no:` sem aspas viram booleano no YAML e o módulo sumia em silêncio; `load_config` agora rejeita com mensagem clara. 180 testes; conferido no navegador. Observação: sem autenticação, qualquer um que alcance o servidor vê esse status (já era assim em `/api/platform/modules`).* — Tela em Settings: status, saúde, erro de carga (e toggle se D1 = B/C) | observabilidade | Baixo |
| **8. Mover pastas** ✅ *concluída em 06/11/2026 — `git mv` (histórico preservado): routers/metrics/db/ingest/web do flow → `modules/flow/`; da hierarchy → `modules/hierarchy/`; design system, menu e painel → `kernel/web/`. URLs, rotas e OpenAPI inalterados (snapshot idêntico). Estáticos agora por pasta do módulo (`web_dir`/`web_prefix`; desligado = não montado = 404), substituindo a política em runtime. `.importlinter` virou 2 contratos com `independence` real. `ingest_to_db.py` ficou como atalho de CLI; `exporter_jira/` e `run_pipeline.py` ficaram na raiz (scripts compartilhados/de orquestração). Mocks (`mock_*.py`) não foram movidos.* — `modules/<id>/…` (D3) | clareza final | Baixo, muito diff |

Ordem sugerida: **0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8**. As fases 1–2 já entregam "desligar hierarchy sem afetar flow" no nível de backend; 5 completa no frontend.

## 6. Critérios de aceite (como saber que deu certo)

1. Com `hierarchy: enabled: false`: nenhuma rota `/api/hierarchy/*` nem `/hierarchy/*` (404), `hierarchy.db` **não é criado**, menu não mostra o link, **todas** as rotas de flow respondem igual.
2. Com `flow: enabled: false`: hierarchy sobe e funciona sozinha (hoje não funciona, por B).
3. Módulo com erro de import → plataforma sobe, módulo marcado `failed` com a causa.
4. `import-linter` falha o CI se `modules/A` importar `modules/B` ou `kernel` importar módulo.
5. Adicionar um módulo novo exige **só** a pasta do módulo + uma linha em `config/modules.yaml` (sem editar menu, `api.py` nem outros módulos).
6. Duas escritas simultâneas de configuração (flow e hierarchy) não perdem dados.
7. Instalação limpa (sem nenhum `.db`): `setup` cria os bancos só dos módulos escolhidos, e todas as rotas respondem sem erro de tabela ausente.
8. O schema gerado pelas migrações é idêntico ao de um banco de produção existente; rodar as migrações duas vezes não altera nada.
9. `enable`/`disable` de um módulo pela CLI funciona sem editar arquivo à mão e sem afetar os demais.

## 7. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Regressão silenciosa de rotas | Fase 0 (snapshot OpenAPI + smoke) antes de qualquer mudança |
| Corromper `projects.yaml` ao migrar | Backup automático, leitura compatível com formato antigo, migração reversível |
| URLs mudarem e quebrarem favoritos | Manter URLs atuais; só adicionar `/platform/` para assets |
| ✅ **CORRIGIDO em 06/11/2026** (`kernel/static.py`: allowlist de extensões + pastas web, bloqueia `.`-prefixados; 33 testes). **Exposição de arquivos pelo mount estático** (achado na fase 1): `StaticFiles(directory=BASE_DIR)` serve **qualquer** arquivo da pasta — `/issues.db`, `/projects.yaml`, código `.py`, `/.venv/...` e `/exporter_jira/.env` se existir. Não é causado pela modularização, mas ela o torna visível | Tratar antes de qualquer exposição além da máquina local: servir só um allowlist de extensões/pastas (`.html .css .js` e assets) e/ou mover os estáticos para uma pasta dedicada (fase 5) |
| Overengineering (plataforma maior que o problema) | Fases 1–2 entregam valor sozinhas; 6–8 são opcionais e podem esperar o 3º módulo real |
| Módulos futuros precisarem de dados de outro módulo | Serviços expostos via plataforma + `requires`; nunca import direto |

## 8. Pontos que não consegui verificar

- Como o serviço é operado em produção (`start_service.ps1`/`stop_services.ps1` assumem `api:app`; o plano mantém esse entrypoint, mas não validei com o ambiente real).
- Se existem outros consumidores externos das URLs atuais (favoritos, links em Jira/Confluence) — por isso a proposta mantém as URLs.

