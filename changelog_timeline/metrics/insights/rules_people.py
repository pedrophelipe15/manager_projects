"""Regras de diagnóstico de pessoas e qualidade (Wave 3).

Analisa WIP excessivo, concentração de carga, handoffs e retrabalho.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

from .engine import InsightsEngine, Insight


def register_people_rules(engine: InsightsEngine) -> None:
    """Registra todas as regras de pessoas na engine."""
    engine.register("wip_overload", rule_wip_overload)
    engine.register("bus_factor_risk", rule_bus_factor_risk)
    engine.register("high_rework_rate", rule_high_rework_rate)
    engine.register("handoff_excessive", rule_handoff_excessive)


# --- Rules ---

def rule_wip_overload(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Detecta pessoas com WIP excessivo (>=4 itens simultâneos)."""
    cursor = conn.cursor()

    active_states = ("In Progress", "Test")
    placeholders = ",".join(f"'{s}'" for s in active_states)

    cursor.execute(f'''
        SELECT assignee_name, COUNT(*) as wip
        FROM issues
        WHERE project_key = ? AND status IN ({placeholders})
          AND assignee_name IS NOT NULL AND assignee_name != ''
        GROUP BY assignee_name
        HAVING wip >= 4
        ORDER BY wip DESC
    ''', (project_key,))
    rows = cursor.fetchall()

    if not rows:
        return []

    overloaded = [(row[0], row[1]) for row in rows]
    critical = [p for p in overloaded if p[1] >= 6]
    
    if critical:
        names = ", ".join(f"{p[0]} ({p[1]})" for p in critical[:3])
        return [Insight(
            category="people",
            severity="critical",
            title=f"Multitasking crítico: {len(critical)} pessoa(s) com 6+ itens WIP",
            description=f"Pessoas com WIP excessivo: {names}. "
                        f"Context-switching constante com 6+ itens reduz produtividade em até 80%.",
            metric="wip_overload_critical",
            value=critical[0][1],
            threshold=6,
            recommendation="Limitar WIP individual a 3 itens máximo. "
                           "Priorizar conclusão antes de iniciar novos trabalhos.",
        )]
    else:
        names = ", ".join(f"{p[0]} ({p[1]})" for p in overloaded[:3])
        return [Insight(
            category="people",
            severity="warning",
            title=f"Multitasking elevado: {len(overloaded)} pessoa(s) com 4+ itens WIP",
            description=f"Pessoas com WIP acima do recomendado: {names}. "
                        f"Multitasking acima de 3 itens gera perda de foco e atrasos.",
            metric="wip_overload",
            value=overloaded[0][1],
            threshold=4,
            recommendation="Redistribuir carga ou definir prioridade clara para limitar itens simultâneos.",
        )]


def rule_bus_factor_risk(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Detecta concentração de conhecimento (bus factor <= 2)."""
    cursor = conn.cursor()
    cutoff = (datetime.now() - timedelta(weeks=12)).isoformat()

    cursor.execute('''
        SELECT assignee_name, COUNT(*) as done_count
        FROM issues
        WHERE project_key = ? AND status = 'Done'
          AND resolved_at IS NOT NULL AND resolved_at >= ?
          AND assignee_name IS NOT NULL AND assignee_name != ''
        GROUP BY assignee_name
        ORDER BY done_count DESC
    ''', (project_key, cutoff))
    rows = cursor.fetchall()

    if len(rows) < 3:
        return []

    total_done = sum(row[1] for row in rows)
    if total_done == 0:
        return []

    # Calcula bus factor (mínimo de pessoas para 50%+ das entregas)
    accum = 0
    bus_factor = 0
    for row in rows:
        accum += row[1]
        bus_factor += 1
        if accum >= total_done * 0.5:
            break

    top_pct = (rows[0][1] / total_done * 100)

    if bus_factor <= 1:
        return [Insight(
            category="people",
            severity="critical",
            title=f"Bus factor crítico: 1 pessoa faz {top_pct:.0f}% das entregas",
            description=f"{rows[0][0]} concentra {top_pct:.0f}% das entregas nas últimas 12 semanas "
                        f"({rows[0][1]} de {total_done} issues). Se essa pessoa sair, o projeto para.",
            metric="bus_factor",
            value=1,
            threshold=2,
            recommendation="Distribuir conhecimento via pair programming, rotação de tarefas, "
                           "ou documentação de processos críticos.",
        )]
    elif bus_factor == 2 and top_pct > 35:
        return [Insight(
            category="people",
            severity="warning",
            title=f"Concentração de carga: 2 pessoas fazem 50%+ das entregas",
            description=f"Bus factor = 2. Top contribuidores: {rows[0][0]} ({rows[0][1]}) e "
                        f"{rows[1][0]} ({rows[1][1]}) de {total_done} total. "
                        f"Risco organizacional se algum sair.",
            metric="bus_factor",
            value=2,
            threshold=3,
            recommendation="Envolver mais pessoas em tarefas variadas para distribuir conhecimento.",
        )]
    return []


def rule_high_rework_rate(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Detecta taxa de retrabalho alta (>20% das issues com transições para trás)."""
    cursor = conn.cursor()

    # Status order para detectar transições "para trás"
    status_order = {
        "Open": 0, "Backlog": 1, "To do": 2, "Refinement": 3,
        "In Progress": 4, "Blocked": 4, "Test": 5,
        "Waiting for Delivery": 6, "Done": 7,
    }

    cursor.execute('''
        SELECT pc.issue_key, pc.from_value, pc.to_value
        FROM parsed_changelogs pc
        INNER JOIN issues i ON pc.issue_key = i.key
        WHERE i.project_key = ? AND pc.field = 'status'
    ''', (project_key,))
    rows = cursor.fetchall()

    if not rows:
        return []

    issues_with_rework = set()
    all_issues = set()
    for issue_key, from_val, to_val in rows:
        all_issues.add(issue_key)
        from_order = status_order.get(from_val, 3)
        to_order = status_order.get(to_val, 3)
        if to_order < from_order and from_val and to_val:
            issues_with_rework.add(issue_key)

    total = len(all_issues)
    rework_count = len(issues_with_rework)
    rate = (rework_count / total * 100) if total > 0 else 0

    if rate > 30:
        return [Insight(
            category="people",
            severity="warning",
            title=f"Taxa de retrabalho alta: {rate:.0f}%",
            description=f"{rework_count} de {total} issues ({rate:.0f}%) tiveram transições para trás no fluxo. "
                        f"Indica problemas de qualidade, escopo mal definido ou mudanças tardias de requisito.",
            metric="rework_rate",
            value=round(rate, 1),
            threshold=30,
            recommendation="Investir em refinamento de requisitos antes do início do trabalho. "
                           "Revisar critérios de 'Done' para reduzir retornos de QA.",
        )]
    elif rate < 10 and total > 20:
        return [Insight(
            category="people",
            severity="healthy",
            title=f"Retrabalho baixo: apenas {rate:.0f}%",
            description=f"Apenas {rework_count} de {total} issues ({rate:.0f}%) tiveram retrabalho. "
                        f"Indica boa definição de requisitos e qualidade no primeiro ciclo.",
            metric="rework_rate",
            value=round(rate, 1),
        )]
    return []


def rule_handoff_excessive(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Detecta handoffs excessivos (média > 2 por issue)."""
    cursor = conn.cursor()

    cursor.execute('''
        SELECT pc.issue_key, COUNT(*) as handoffs
        FROM parsed_changelogs pc
        INNER JOIN issues i ON pc.issue_key = i.key
        WHERE i.project_key = ? AND pc.field = 'assignee'
          AND pc.from_value IS NOT NULL AND pc.from_value != ''
          AND pc.to_value IS NOT NULL AND pc.to_value != ''
        GROUP BY pc.issue_key
    ''', (project_key,))
    rows = cursor.fetchall()

    if not rows:
        return []

    total_issues = len(rows)
    total_handoffs = sum(row[1] for row in rows)
    avg_handoffs = total_handoffs / total_issues
    issues_with_3plus = sum(1 for row in rows if row[1] >= 3)

    if avg_handoffs > 2.0:
        return [Insight(
            category="people",
            severity="warning",
            title=f"Handoffs excessivos: média {avg_handoffs:.1f} por issue",
            description=f"{total_handoffs} transferências de responsabilidade em {total_issues} issues "
                        f"(média {avg_handoffs:.1f}/issue). {issues_with_3plus} issues tiveram 3+ handoffs. "
                        f"Cada handoff adiciona espera e perda de contexto.",
            metric="avg_handoffs",
            value=round(avg_handoffs, 1),
            threshold=2.0,
            recommendation="Reduzir handoffs desnecessários: quem inicia deve concluir quando possível. "
                           "Revisar processo para eliminar etapas de 'passar adiante'.",
        )]
    return []
