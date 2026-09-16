# Manager Projects — Changelog Timeline

Sistema de **gestão de fluxo e métricas de engenharia** que extrai dados do Jira
(issues + changelog de transições de status), persiste em SQLite local e serve
dashboards analíticos e operacionais para líderes e gestores de delivery.

> **Status:** versão produtiva. A aplicação ativa é a `changelog_timeline/`.
> Protótipos anteriores (`dashboard/`, `dashboard_v2/`, `dashboard_v3/`) foram
> descontinuados e removidos.

---

## Para quem é

~10 líderes/gestores de delivery, cada um responsável por ~2 projetos. A ferramenta
responde as perguntas que trazem quando abrem o sistema: a equipe está cumprindo
prazo ou empurrando a data pra frente? O que está travado? Quem precisa de ajuda?

---

## Principais telas

| Tela | URL | Responde |
|------|-----|----------|
| **Minha Visão** | `/minha-visao.html` | O que preciso olhar hoje? (visão consolidada dos meus projetos) |
| **Compromisso de Prazo** | `/compromisso.html` | Estão cumprindo prazo ou reprogramando? |
| **Maturidade** | `/maturidade.html` | Report de ações pendentes por responsável |
| **Gargalo e Fluxo** (Wave 1) | `/wave1.html` | Onde o trabalho fica parado? (percentis, CFD, aging WIP) |
| **Previsibilidade** (Wave 2) | `/wave2.html` | Throughput, forecast Monte Carlo, aging backlog |
| **Pessoas** (Wave 3) | `/wave3.html` | WIP, distribuição de carga, handoffs, retrabalho |
| **Portfolio** (Wave 4) | `/wave4.html` | Epic health, benchmarking, throughput consolidado |
| **Dashboard** | `/dashboard.html` | KPIs operacionais + tabela de issues |
| **Hierarquia** | `/hierarchy/dashboard-v2.html` | Iniciativa → Épico → Story (módulo isolado) |
| **Inconsistências** | `/inconsistencies.html` | Validações de qualidade de dados |
| **Configurações** | `/settings.html` | Projetos, blacklist, expurgo |

---

## Arquitetura

```
Jira API (Cloud)
   │  REST v3 (paginado, retry, expand=changelog)
   ▼
exporter_jira/export_jira.py  ──►  output/{PROJECT}/ (JSONL)
   ▼
ingest_to_db.py  ──►  issues.db (SQLite, WAL)
   │  metrics/*  (base, wave1..5, insights)
   ▼
api.py (FastAPI + uvicorn)  ──►  Browser (HTML/CSS/JS vanilla + Chart.js)
```

- **Backend:** Python 3.12+, FastAPI/uvicorn, servindo REST + arquivos estáticos.
- **Persistência:** SQLite (WAL). Duas bases isoladas: `issues.db` (fluxo padrão) e
  `hierarchy.db` (módulo hierárquico).
- **Frontend:** HTML/CSS/JS puro (sem framework), Chart.js para gráficos.
- **Métricas por Waves:** base (lead/cycle time), Wave 1–4 e Wave 5 (compromisso de
  prazo / due date slippage).

### Design System

O frontend usa um design system centralizado a partir da revisão de UX:
- `tokens.css` — fonte única de cor, tipografia, espaçamento e botões (contraste AA).
- `nav.css` / `nav.js` — navegação compartilhada agrupada por pergunta.
- `ui.css` / `ui.js` — densidade (compacto/confortável), `tabular-nums`, copiar tabela.
- `context.js` — persistência do projeto selecionado entre páginas.
- Racional teórico: [`changelog_timeline/docs/GUIA-DESIGN-DASHBOARD.md`](changelog_timeline/docs/GUIA-DESIGN-DASHBOARD.md).

Documentação técnica completa: [`changelog_timeline/docs/DATASHEET.md`](changelog_timeline/docs/DATASHEET.md).

---

## Como rodar

### Pré-requisitos
- Python 3.12+
- Dependências em `changelog_timeline/requirements.txt`
- Arquivo `.env` em `changelog_timeline/exporter_jira/` com credenciais Jira
  (não versionado — ver abaixo)

### Instalação e execução

```powershell
cd changelog_timeline
pip install -r requirements.txt
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Acesso: `http://localhost:8000/minha-visao.html`

### Credenciais Jira (`changelog_timeline/exporter_jira/.env`)

```env
JIRA_BASE_URL="https://seu-dominio.atlassian.net"
JIRA_EMAIL="seu-email@empresa.com"
JIRA_API_TOKEN="seu-token"
JIRA_PAGE_SIZE=100
JIRA_REQUEST_TIMEOUT_SECONDS=30
```

> **Nunca commitar o `.env`.** Já está no `.gitignore`.

### Sincronização

Via UI em `/settings.html` (botão "Atualizar") ou via CLI (ver DATASHEET).

---

## Estrutura do repositório

```
manager_projects_v2/
├── changelog_timeline/       # Aplicação (backend + frontend + métricas)
│   ├── api.py                # FastAPI: endpoints REST + estáticos
│   ├── ingest_to_db.py       # Ingestão JSONL → SQLite + orquestra métricas
│   ├── metrics/              # Pacote de métricas (base, wave1..5, insights)
│   ├── exporter_jira/        # Extrator do Jira
│   ├── hierarchy/            # Módulo hierárquico (banco isolado)
│   ├── docs/                 # DATASHEET + Guia de Design
│   ├── tokens.css nav.* ui.* context.js  # Design system compartilhado
│   └── *.html *.css *.js     # Telas
├── .kiro/steering/           # Regras de layout e comunicação do projeto
└── README.md
```

> `.agent/` e `_bmad/` são ferramentas de desenvolvimento assistido por IA e não
> fazem parte do produto (ignorados no `.gitignore`).

---

## Versionamento

Não versionar: `.env`, bancos `*.db`, `__pycache__/`, saídas em `output/` e `temp/`.
