"""InsightsEngine — motor modular de análise automática.

Registra regras (funções), executa todas para um projeto e retorna
insights categorizados por severidade.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, asdict
from typing import Any, Callable


@dataclass
class Insight:
    """Um insight individual gerado por uma regra."""
    category: str          # "flow", "throughput", "people", "portfolio", "alert"
    severity: str          # "critical", "warning", "info", "healthy"
    title: str             # Título curto (ex: "Lead Time piorando")
    description: str       # Explicação detalhada
    metric: str | None = None       # Métrica relacionada (ex: "lead_time_p85")
    value: Any = None               # Valor atual
    threshold: Any = None           # Threshold/referência
    recommendation: str | None = None  # Ação sugerida

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


# Tipo de uma rule function: recebe conn + project_key, retorna lista de Insights
RuleFunction = Callable[[sqlite3.Connection, str], list[Insight]]


class InsightsEngine:
    """Motor de insights: registra regras e executa para um projeto."""

    def __init__(self):
        self._rules: list[tuple[str, RuleFunction]] = []

    def register(self, name: str, rule_fn: RuleFunction) -> None:
        """Registra uma regra de detecção."""
        self._rules.append((name, rule_fn))

    def run(self, conn: sqlite3.Connection, project_key: str) -> list[Insight]:
        """Executa todas as regras registradas e retorna insights agregados."""
        all_insights: list[Insight] = []

        for rule_name, rule_fn in self._rules:
            try:
                insights = rule_fn(conn, project_key)
                all_insights.extend(insights)
            except Exception as e:
                # Regra falhou — não quebra as outras
                all_insights.append(Insight(
                    category="system",
                    severity="warning",
                    title=f"Erro na regra '{rule_name}'",
                    description=str(e)[:200],
                ))

        # Ordena: critical > warning > info > healthy
        severity_order = {"critical": 0, "warning": 1, "info": 2, "healthy": 3}
        all_insights.sort(key=lambda i: severity_order.get(i.severity, 9))

        return all_insights


# Instância global da engine (recriada quando módulo recarrega)
_engine: InsightsEngine | None = None


def get_engine() -> InsightsEngine:
    """Retorna a engine singleton, registrando todas as regras disponíveis."""
    global _engine
    if _engine is None:
        _engine = InsightsEngine()
        # Registra regras de fluxo (Wave 1)
        from .rules_flow import register_flow_rules
        register_flow_rules(_engine)
        # Registra regras de previsibilidade (Wave 2)
        from .rules_throughput import register_throughput_rules
        register_throughput_rules(_engine)
        # Registra regras de pessoas (Wave 3)
        from .rules_people import register_people_rules
        register_people_rules(_engine)
        # Registra regras de portfólio (Wave 4)
        from .rules_portfolio import register_portfolio_rules
        register_portfolio_rules(_engine)
        # Registra alertas proativos (Onda 5)
        from .rules_alerts import register_alert_rules
        register_alert_rules(_engine)
    return _engine


def run_insights(conn: sqlite3.Connection, project_key: str) -> dict:
    """Executa a engine e retorna resultado formatado para a API."""
    engine = get_engine()
    insights = engine.run(conn, project_key)

    # Agrupa por categoria
    by_category: dict[str, list[dict]] = {}
    for insight in insights:
        cat = insight.category
        by_category.setdefault(cat, []).append(insight.to_dict())

    # Contadores por severidade
    severity_counts = {"critical": 0, "warning": 0, "info": 0, "healthy": 0}
    for insight in insights:
        severity_counts[insight.severity] = severity_counts.get(insight.severity, 0) + 1

    return {
        "project_key": project_key,
        "total": len(insights),
        "severity_counts": severity_counts,
        "by_category": by_category,
        "insights": [i.to_dict() for i in insights],
    }
