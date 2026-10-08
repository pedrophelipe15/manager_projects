"""Regras de diagnóstico de portfólio (Wave 4).

Analisa saúde de épicos, cross-project e riscos de entrega.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

from .engine import InsightsEngine, Insight


def register_portfolio_rules(engine: InsightsEngine) -> None:
    """Registra todas as regras de portfólio na engine."""
    engine.register("epics_at_risk", rule_epics_at_risk)
    engine.register("epic_stalled", rule_epic_stalled)
    engine.register("cross_project_imbalance", rule_cross_project_imbalance)


# --- Rules ---

def rule_epics_at_risk(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Detecta épicos com risco alto/crítico de não cumprir prazo."""
    cursor = conn.cursor()

    # Busca parents com subtasks
    cursor.execute('''
        SELECT 
            parent.key,
            parent.summary,
            parent.due_date,
            parent.issuetype_name,
            COUNT(child.key) as total,
            SUM(CASE WHEN child.status = 'Done' THEN 1 ELSE 0 END) as done
        FROM issues child
        INNER JOIN issues parent ON child.parent_key = parent.key
        WHERE child.project_key = ?
          AND parent.status != 'Done'
          AND parent.due_date IS NOT NULL AND parent.due_date != ''
        GROUP BY parent.key
        HAVING total > 2
    ''', (project_key,))
    rows = cursor.fetchall()

    if not rows:
        return []

    overdue_epics = []
    now = datetime.now()

    for key, summary, due_date, issue_type, total, done in rows:
        remaining = total - done
        if remaining <= 0:
            continue
        try:
            due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00")).replace(tzinfo=None)
            days_until_due = (due_dt - now).days
            progress = done / total if total > 0 else 0

            # Épico com due date próxima e progresso baixo
            if days_until_due < 0:
                overdue_epics.append((key, summary, remaining, days_until_due, "vencido", issue_type))
            elif days_until_due < 14 and progress < 0.7:
                overdue_epics.append((key, summary, remaining, days_until_due, "risco", issue_type))
        except (ValueError, TypeError):
            continue

    if not overdue_epics:
        return []

    vencidos = [e for e in overdue_epics if e[4] == "vencido"]
    em_risco = [e for e in overdue_epics if e[4] == "risco"]

    if vencidos:
        names = ", ".join(f"{e[0]} ({e[2]} restantes, {abs(e[3])}d atrasado)" for e in vencidos[:3])
        type_label = vencidos[0][5] or "item"
        return [Insight(
            category="portfolio",
            severity="critical",
            title=f"{len(vencidos)} {type_label}(s) com due date vencida",
            description=f"Issues-pai atrasadas: {names}. "
                        f"Itens restantes nao serao entregues no prazo original.",
            metric="parents_overdue",
            value=len(vencidos),
            recommendation="Renegociar prazos ou reduzir escopo. "
                           "Priorizar itens criticos e mover o restante para proximo ciclo.",
        )]
    elif em_risco:
        names = ", ".join(f"{e[0]} ({e[2]} restantes, {e[3]}d)" for e in em_risco[:3])
        type_label = em_risco[0][5] or "item"
        return [Insight(
            category="portfolio",
            severity="warning",
            title=f"{len(em_risco)} {type_label}(s) com prazo apertado",
            description=f"Issues-pai com due date em <14 dias e progresso baixo: {names}.",
            metric="parents_at_risk",
            value=len(em_risco),
            recommendation="Aumentar foco nesses itens ou comunicar risco ao stakeholder.",
        )]
    return []


def rule_epic_stalled(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Detecta épicos parados (sem conclusão de subtask há 3+ semanas)."""
    cursor = conn.cursor()
    cutoff = (datetime.now() - timedelta(weeks=3)).isoformat()

    # Busca parents abertos com subtasks
    cursor.execute('''
        SELECT 
            parent.key,
            parent.summary,
            parent.issuetype_name,
            COUNT(child.key) as total,
            SUM(CASE WHEN child.status = 'Done' THEN 1 ELSE 0 END) as done,
            MAX(CASE WHEN child.status = 'Done' THEN child.resolved_at ELSE NULL END) as last_done
        FROM issues child
        INNER JOIN issues parent ON child.parent_key = parent.key
        WHERE child.project_key = ?
          AND parent.status != 'Done'
        GROUP BY parent.key
        HAVING total > 2 AND done < total
    ''', (project_key,))
    rows = cursor.fetchall()

    stalled = []
    for key, summary, issue_type, total, done, last_done in rows:
        remaining = total - done
        if remaining <= 0:
            continue
        # Épico sem conclusão recente
        if last_done and last_done < cutoff:
            stalled.append((key, summary, remaining, issue_type))
        elif not last_done and done == 0:
            # Nunca teve item concluído
            stalled.append((key, summary, remaining, issue_type))

    if len(stalled) >= 3:
        names = ", ".join(f"{e[0]} ({e[2]} restantes)" for e in stalled[:3])
        type_label = stalled[0][3] or "item"
        return [Insight(
            category="portfolio",
            severity="warning",
            title=f"{len(stalled)} {type_label}(s) parada(s) (sem entrega ha 3+ semanas)",
            description=f"Issues-pai sem conclusao de subtask recente: {names}. "
                        f"Podem estar bloqueadas ou despriorizadas.",
            metric="parents_stalled",
            value=len(stalled),
            recommendation="Revisar se esses itens ainda sao prioridade. "
                           "Se sim, investigar bloqueios. Se nao, cancelar ou postergar formalmente.",
        )]
    return []


def rule_cross_project_imbalance(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Detecta desequilíbrio grande de throughput entre projetos (>3x diferença)."""
    cursor = conn.cursor()
    cutoff = (datetime.now() - timedelta(weeks=8)).isoformat()

    cursor.execute('''
        SELECT project_key, COUNT(*) as done_count
        FROM issues
        WHERE status = 'Done' AND resolved_at IS NOT NULL AND resolved_at >= ?
        GROUP BY project_key
    ''', (cutoff,))
    rows = cursor.fetchall()

    if len(rows) < 2:
        return []

    throughputs = [(row[0], row[1]) for row in rows]
    throughputs.sort(key=lambda x: -x[1])

    max_tp = throughputs[0][1]
    min_tp = throughputs[-1][1]

    if min_tp > 0 and max_tp / min_tp > 4:
        return [Insight(
            category="portfolio",
            severity="info",
            title=f"Desequilibrio de throughput entre projetos ({max_tp / min_tp:.1f}x)",
            description=f"Projeto {throughputs[0][0]} entregou {throughputs[0][1]} issues vs "
                        f"{throughputs[-1][0]} com {throughputs[-1][1]} nas ultimas 8 semanas. "
                        f"Diferenca de {max_tp / min_tp:.1f}x pode indicar times com capacidades diferentes ou prioridades desbalanceadas.",
            metric="throughput_imbalance",
            value=round(max_tp / min_tp, 1),
        )]
    return []
