# Aba Insights — histórico de arquivamento e reativação

Data de arquivamento: 21/08/2026
Motivo do arquivamento (à época): substituída pela aba "Maturidade", que oferece report por assignee com ações concretas.

**Status atual (reativada em 10/09/2026):** a aba Insights foi **reativada**. Durante a sprint de saneamento técnico, o link "Insights" foi readicionado à navegação de todas as páginas para que o badge de alertas do `nav-alerts.js` voltasse a funcionar fora da própria `insights.html`. A aba Insights e a aba Maturidade **coexistem** — Insights entrega o diagnóstico automático por severidade; Maturidade entrega o report acionável por assignee.

Este documento passa a ser um **registro histórico** desse ciclo (arquivada → reativada), não um estado atual de "arquivado".

---

## Arquivos

| Arquivo | Funcao | Status atual |
|---------|--------|--------|
| `insights.html` | Pagina HTML da aba | **Ativo** (link na nav de todas as páginas) |
| `insights-page.js` | JavaScript da pagina | **Ativo** |
| `insights.css` | CSS da pagina | **Ativo** |
| `nav-alerts.js` | Badge de alertas na nav | **Ativo** (usado por todas as páginas; alvo `/insights.html` agora existe em todas) |
| `metrics/insights/` | Engine de regras backend | **Ativo** (endpoints funcionais) |

---

## Endpoints (continuam funcionais)

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/insights?project_key=X` | Retorna insights categorizados por severidade |
| GET | `/api/insights/alert-count` | Contagem de alertas (para badge nav) |

---

## Reativação (já realizada em 10/09/2026)

O link abaixo **já foi readicionado** à nav de todas as páginas que carregam `nav-alerts.js` (dashboard, wave1-4, inconsistencies, settings) e também em maturidade e index:

```html
<a href="/insights.html" class="nav-link">Insights</a>
```

- Os arquivos da aba sempre existiram no projeto — a reativação foi apenas o link na nav.
- Endpoints backend permanecem intactos (`/api/insights`, `/api/insights/alert-count`).
- O `nav-alerts.js` cola o badge no elemento `a[href="/insights.html"]`, que agora existe em todas as páginas (antes só em `insights.html`, por isso o badge não aparecia fora dela).

---

## Estrutura do Engine (metrics/insights/)

```
metrics/insights/
├── __init__.py              # run_insights(conn, project_key) -> dict
├── engine.py                # InsightsEngine: registra rules, executa, categoriza
├── rules_flow.py            # 8 regras de diagnostico de fluxo (Wave 1)
├── rules_throughput.py      # 4 regras de previsibilidade
├── rules_people.py          # 4 regras de pessoas
├── rules_portfolio.py       # 3 regras de portfolio
└── rules_alerts.py          # 5 alertas proativos
```

---

## Regras implementadas (24 total)

| Categoria | Qtd | Arquivo |
|-----------|-----|---------|
| Fluxo | 8 | rules_flow.py |
| Previsibilidade | 4 | rules_throughput.py |
| Pessoas | 4 | rules_people.py |
| Portfolio | 3 | rules_portfolio.py |
| Alertas proativos | 5 | rules_alerts.py |

---

## Formato de retorno da API

```json
{
  "project_key": "STN",
  "total": 5,
  "severity_counts": {"critical": 1, "warning": 2, "info": 1, "healthy": 1},
  "by_category": {"flow": [...], "alert": [...]},
  "insights": [
    {
      "category": "flow",
      "severity": "warning",
      "title": "Lead Time piorando",
      "description": "P85 crescente 3+ semanas consecutivas",
      "recommendation": "Investigar gargalos no fluxo",
      "metric": "lead_time_p85",
      "value": 15.2,
      "threshold": 10.0
    }
  ]
}
```

---

## Estado atual e possível evolução

1. ✅ Link reativado na nav de todas as páginas raiz (feito em 10/09/2026).
2. ✅ Backend intacto — nenhuma alteração foi necessária.
3. 💡 Evolução futura possível: unificar/aproximar Insights e Maturidade, caso faça sentido (Insights = diagnóstico por severidade; Maturidade = report acionável por assignee).
