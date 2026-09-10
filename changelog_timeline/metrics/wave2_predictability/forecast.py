"""Wave 2.2 — Monte Carlo Forecast.
Simulação probabilística: dado um throughput histórico e N itens restantes,
estima com X% de confiança em quantas semanas o trabalho será concluído.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime

from ..forecast_core import simulate_completion_weeks, percentile_from_sorted


def monte_carlo_forecast(
    conn: sqlite3.Connection,
    project_key: str,
    remaining_items: int,
    simulations: int = 10000,
    history_weeks: int = 12,
) -> dict:
    """Executa simulação Monte Carlo para prever conclusão de N itens.
    
    Usa o throughput semanal histórico como distribuição de probabilidade.
    Cada simulação sorteia semanas aleatórias do histórico e soma até atingir remaining_items.
    
    Retorna:
    - percentiles: {p50, p70, p85, p95} em semanas
    - histogram: distribuição das simulações
    - throughput_used: stats do throughput histórico usado
    """
    # Coleta throughput histórico
    cursor = conn.cursor()
    cursor.execute('''
        SELECT resolved_at
        FROM issues
        WHERE status = 'Done' AND resolved_at IS NOT NULL AND resolved_at != ''
          AND project_key = ?
    ''', (project_key,))
    rows = cursor.fetchall()

    if not rows:
        return {"error": "Sem dados de throughput histórico"}

    # Agrupa por semana ISO
    by_week: dict[str, int] = defaultdict(int)
    for (resolved_at,) in rows:
        try:
            dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
            iso = dt.isocalendar()
            week_key = f"{iso[0]}-W{iso[1]:02d}"
            by_week[week_key] += 1
        except (ValueError, TypeError):
            continue

    # Usa últimas N semanas
    sorted_weeks = sorted(by_week.keys())[-history_weeks:]
    weekly_throughputs = [by_week[w] for w in sorted_weeks]

    if not weekly_throughputs or max(weekly_throughputs) == 0:
        return {"error": "Throughput histórico insuficiente (0 items/semana)"}

    # Simulação Monte Carlo (núcleo compartilhado — mesma sequência de amostragem)
    results = simulate_completion_weeks(weekly_throughputs, remaining_items, simulations)

    def percentile(pct: float) -> int:
        return percentile_from_sorted(results, pct)

    # Histograma (distribuição de frequência)
    from collections import Counter
    freq = Counter(results)
    histogram = [{"weeks": w, "count": c} for w, c in sorted(freq.items())]

    avg_throughput = sum(weekly_throughputs) / len(weekly_throughputs)

    return {
        "project_key": project_key,
        "remaining_items": remaining_items,
        "simulations": simulations,
        "history_weeks": len(weekly_throughputs),
        "percentiles": {
            "p50": percentile(50),
            "p70": percentile(70),
            "p85": percentile(85),
            "p95": percentile(95),
        },
        "throughput_used": {
            "avg": round(avg_throughput, 1),
            "min": min(weekly_throughputs),
            "max": max(weekly_throughputs),
            "weeks_sampled": len(weekly_throughputs),
        },
        "histogram": histogram,
    }


def get_open_epics(conn: sqlite3.Connection, project_key: str) -> list[dict]:
    """Retorna épicos/parents abertos com contagem de itens restantes.
    
    Usado para alimentar o forecast: "quantos itens faltam neste épico?"
    """
    cursor = conn.cursor()

    # Busca parents que têm subtasks não-Done
    cursor.execute('''
        SELECT 
            parent.key,
            parent.summary,
            parent.status,
            parent.assignee_name,
            parent.issuetype_name,
            COUNT(child.key) as total_children,
            SUM(CASE WHEN child.status = 'Done' THEN 1 ELSE 0 END) as done_children
        FROM issues child
        INNER JOIN issues parent ON child.parent_key = parent.key
        WHERE child.project_key = ?
          AND parent.status != 'Done'
        GROUP BY parent.key
        HAVING total_children > 1
        ORDER BY (total_children - done_children) DESC
    ''', (project_key,))
    rows = cursor.fetchall()

    epics = []
    for row in rows:
        total = row[5]
        done = row[6]
        remaining = total - done
        if remaining > 0:
            epics.append({
                "key": row[0],
                "summary": row[1],
                "status": row[2],
                "assignee": row[3],
                "issue_type": row[4],
                "total": total,
                "done": done,
                "remaining": remaining,
                "progress_pct": round(done / total * 100, 1) if total > 0 else 0,
            })
    return epics
