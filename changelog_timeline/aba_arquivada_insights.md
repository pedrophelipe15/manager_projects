# Aba Arquivada: Insights

Data de arquivamento: 21/08/2026
Motivo: Substituida pela aba "Maturidade" que oferece report por assignee com acoes concretas.

---

## Arquivos

| Arquivo | Funcao | Status |
|---------|--------|--------|
| `insights.html` | Pagina HTML da aba | Arquivado (mantido no projeto, removido da nav) |
| `insights-page.js` | JavaScript da pagina | Arquivado |
| `insights.css` | CSS da pagina | Arquivado |
| `nav-alerts.js` | Badge de alertas na nav | MANTIDO (usado por outras paginas) |
| `metrics/insights/` | Engine de regras backend | MANTIDO (endpoints continuam funcionais) |

---

## Endpoints (continuam funcionais)

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/insights?project_key=X` | Retorna insights categorizados por severidade |
| GET | `/api/insights/alert-count` | Contagem de alertas (para badge nav) |

---

## Como reimplementar

1. Adicionar link na nav de todas as paginas:
   ```html
   <a href="/insights.html" class="nav-link">Insights</a>
   ```

2. Os arquivos ja existem no projeto — basta reativar o link.

3. Endpoints backend estao intactos (`/api/insights`, `/api/insights/alert-count`).

4. O `nav-alerts.js` continua funcionando e pode apontar para qualquer pagina de destino.

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

## Para restaurar completamente

1. Reativar link na nav (todas as 8 paginas raiz)
2. Nenhuma alteracao de backend necessaria
3. Considerar unificar com a aba Maturidade caso faca sentido no futuro
