"""Wave 4.1 — Epic Health.
Progresso, previsão de término e risco por épico (parent issue).
Agrega dados de subtasks para dar visão de portfólio.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime

from ..forecast_core import simulate_completion_weeks, percentile_from_sorted


def get_epic_health(conn: sqlite3.Connection, project_key: str) -> dict:
    """Retorna saúde de cada épico/parent com subtasks.
    
    Para cada épico calcula:
    - Progresso (% done)
    - Throughput recente das subtasks deste épico
    - Forecast (semanas estimadas para concluir)
    - Risco (baseado em throughput declinante ou épico parado)
    """
    cursor = conn.cursor()

    # Busca todos os parents com subtasks neste projeto
    cursor.execute('''
        SELECT 
            parent.key,
            parent.summary,
            parent.status,
            parent.assignee_name,
            parent.due_date,
            parent.issuetype_name,
            COUNT(child.key) as total_children,
            SUM(CASE WHEN child.status = 'Done' THEN 1 ELSE 0 END) as done_children
        FROM issues child
        INNER JOIN issues parent ON child.parent_key = parent.key
        WHERE child.project_key = ?
        GROUP BY parent.key
        HAVING total_children > 1
        ORDER BY (total_children - done_children) DESC
    ''', (project_key,))
    rows = cursor.fetchall()

    if not rows:
        return {"project_key": project_key, "epics": [], "summary": {}}

    # Throughput histórico do projeto (últimas 12 semanas) para forecast
    project_weekly_throughput = _get_project_weekly_throughput(conn, project_key, weeks=12)

    epics = []
    at_risk = 0
    on_track = 0
    done_epics = 0

    for row in rows:
        key, summary, status, assignee, due_date, issue_type, total, done = row
        remaining = total - done
        progress_pct = round(done / total * 100, 1) if total > 0 else 0

        if status == "Done" or remaining == 0:
            done_epics += 1
            risk = "done"
            forecast_p85 = 0
        else:
            # Forecast com Monte Carlo simplificado
            forecast_p85 = _quick_forecast(project_weekly_throughput, remaining)

            # Avalia risco
            risk = _assess_risk(conn, key, due_date, forecast_p85, remaining, total)
            if risk in ("high", "critical"):
                at_risk += 1
            else:
                on_track += 1

        epics.append({
            "key": key,
            "summary": summary,
            "status": status,
            "assignee": assignee,
            "due_date": due_date,
            "issue_type": issue_type,
            "total": total,
            "done": done,
            "remaining": remaining,
            "progress_pct": progress_pct,
            "forecast_p85_weeks": forecast_p85,
            "risk": risk,
        })

    # Ordena: critical/high primeiro, depois por remaining desc
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "done": 4}
    epics.sort(key=lambda e: (risk_order.get(e["risk"], 9), -e["remaining"]))

    summary = {
        "total_epics": len(epics),
        "at_risk": at_risk,
        "on_track": on_track,
        "done": done_epics,
    }

    return {"project_key": project_key, "epics": epics, "summary": summary}


def _get_project_weekly_throughput(conn: sqlite3.Connection, project_key: str, weeks: int = 12) -> list[int]:
    """Retorna throughput semanal do projeto."""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT resolved_at FROM issues
        WHERE project_key = ? AND status = 'Done'
          AND resolved_at IS NOT NULL AND resolved_at != ''
    ''', (project_key,))

    by_week: dict[str, int] = defaultdict(int)
    for (resolved_at,) in cursor.fetchall():
        try:
            dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
            iso = dt.isocalendar()
            wk = f"{iso[0]}-W{iso[1]:02d}"
            by_week[wk] += 1
        except (ValueError, TypeError):
            continue

    sorted_weeks = sorted(by_week.keys())[-weeks:]
    return [by_week[w] for w in sorted_weeks]


def _quick_forecast(weekly_throughput: list[int], remaining: int) -> int:
    """Monte Carlo simplificado: retorna P85 em semanas."""
    if not weekly_throughput or max(weekly_throughput) == 0:
        return 0

    results = simulate_completion_weeks(weekly_throughput, remaining, 1000)
    return percentile_from_sorted(results, 85)


def _assess_risk(conn: sqlite3.Connection, epic_key: str, due_date: str | None, forecast_p85: int, remaining: int, total: int) -> str:
    """Avalia risco do épico baseado em múltiplos fatores."""
    risk_score = 0

    # Fator 1: Due date vs forecast
    if due_date and forecast_p85 > 0:
        try:
            due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00")).replace(tzinfo=None)
            weeks_until_due = (due_dt - datetime.now()).days / 7
            if weeks_until_due < forecast_p85:
                risk_score += 3  # Não vai dar tempo
            elif weeks_until_due < forecast_p85 * 1.2:
                risk_score += 1  # Apertado
        except (ValueError, TypeError):
            pass

    # Fator 2: Progresso muito baixo com muitos itens restantes
    progress = (total - remaining) / total if total > 0 else 0
    if remaining > 10 and progress < 0.2:
        risk_score += 2
    elif remaining > 5 and progress < 0.3:
        risk_score += 1

    # Fator 3: Forecast muito longo (>8 semanas)
    if forecast_p85 >= 12:
        risk_score += 2
    elif forecast_p85 >= 8:
        risk_score += 1

    if risk_score >= 5:
        return "critical"
    elif risk_score >= 3:
        return "high"
    elif risk_score >= 1:
        return "medium"
    return "low"
