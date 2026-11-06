# Changelog Timeline

Sistema de gestão de fluxo e métricas ágeis que extrai dados do Jira (issues + changelog de
transições de status), persiste em SQLite local e serve dashboards de fluxo, previsibilidade,
pessoas, portfólio, insights automáticos e hierarquia (iniciativa → épico → story → sub-task).

Backend em **FastAPI** servindo uma API REST + páginas estáticas (HTML/JS/CSS). Extração via
**API REST do Jira Cloud**.

> Este repositório é a **casca** do projeto: vem sem dados e sem credenciais. Cada pessoa
> configura o próprio `.env` e gera os próprios dados (mock ou Jira real).

---

## Requisitos

- **Python 3.12+**
- Dependências em `requirements.txt` (fastapi, uvicorn, starlette, pydantic, pyyaml, python-dotenv, requests)
- (Opcional, só para dados reais) Credenciais de API do Jira Cloud

---

## Quickstart

```powershell
# 1. Clonar
git clone <URL-DO-SEU-REPO> changelog_timeline
cd changelog_timeline

# 2. Ambiente virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/bin/activate           # Linux/macOS

# 3. Instalar dependências
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 4. Gerar dados de demonstração (não precisa de Jira) — ver secao "Dados"
python mock_full_load.py

# 5. Subir o servidor
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Acesse: **http://localhost:8000**

---

## Dados: mock ou Jira real

Um clone novo **não vem com banco** (`issues.db`/`hierarchy.db` estão no `.gitignore`).
Há duas formas de popular:

### Opção A — Dados de demonstração (mais rápido, sem Jira)

```powershell
python mock_full_load.py       # gera ~5.000 issues fake em issues.db
python mock_delta_sync.py      # (opcional) simula um delta sync
```
Bom para explorar a interface sem configurar credenciais.
> Observação: os mocks populam apenas as tabelas base; as métricas de Wave 1 são calculadas
> pela pipeline real de ingestão (`ingest_to_db.py`).

### Opção B — Dados reais do Jira

1. Configure as credenciais (ver "Configuração").
2. Ajuste os projetos/JQLs em `projects.yaml`.
3. Rode a pipeline:
   ```powershell
   python run_pipeline.py --project-key REYK
   # ou todos os projetos habilitados:
   python run_pipeline.py
   ```
   Alternativamente, use a UI em `http://localhost:8000/settings.html` (botão "Atualizar").

---

## Configuração (apenas para dados reais do Jira)

As credenciais ficam em `exporter_jira/.env` (nunca versionado). Crie a partir do exemplo:

```powershell
copy exporter_jira\.env.example exporter_jira\.env
```

Preencha no `.env`:

```env
JIRA_BASE_URL=https://seu-dominio.atlassian.net
JIRA_EMAIL=seu-email@empresa.com
JIRA_API_TOKEN=seu-token-aqui
```

Os projetos e as JQLs de extração são definidos em `projects.yaml`.

---

## Estrutura do projeto

```
changelog_timeline/
├── api.py                 # Ponto de entrada (uvicorn api:app): create_app()
├── kernel/                # plataforma: registry, migrações, ConfigStore, jobs, shared/, jira/, web/
├── modules/
│   ├── flow/              # dashboards: routers/, metrics/, db.py, ingest.py, migrations/, web/ (páginas em /)
│   └── hierarchy/         # hierarquia: routers/, metrics.py, db.py, migrations/, web/ (páginas em /hierarchy/)
├── config/modules.yaml    # módulos ligados/desligados
├── ingest_to_db.py        # atalho de CLI para modules/flow/ingest.py
├── run_pipeline.py        # Orquestrador CLI (extração + ingestão)
├── projects.yaml          # Projetos e pipelines (JQLs)
├── requirements.txt
│
├── exporter_jira/         # Extratores Jira (standalone) + .env
├── tests/                 # pytest
├── mock_full_load.py      # Gera dados de demonstração
├── mock_delta_sync.py     # Simula delta sync
└── docs/                  # Documentação (ver docs/README.md)
```

Páginas principais: `/dashboard.html`, `/wave1.html`..`/wave4.html`, `/insights.html`,
`/inconsistencies.html`, `/maturidade.html`, `/settings.html`, `/hierarchy/dashboard-v2.html`.

---

## Documentação

A documentação completa está em **[`docs/`](docs/README.md)**:

- `docs/DATASHEET.md` — referência técnica (arquitetura, pipeline, schema, endpoints, métricas).
- `docs/MAPEAMENTO_PROJETO.md` — mapa de scripts, dependências e rotas.
- `docs/design-system.md` — tokens visuais do tema executivo.
- `docs/historico/` — histórico de evolução (planos e prompts).

---

## Notas

- Este projeto não define licença. Sem licença explícita, o padrão é "todos os direitos
  reservados" — cada pessoa que receber a casca deve alinhar o uso conforme necessário.
- `.env`, `*.db` e `output/` são ignorados pelo git (ver `.gitignore`).
