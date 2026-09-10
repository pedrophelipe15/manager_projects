"""Wave 2.1 — Throughput semanal.
Quantas issues foram concluídas por semana, total e por tipo de issue.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime

from ..timeutils import week_to_date_range


def get_throughput_weekly(conn: sqlite3.Connection, project_key: str, weeks: int = 26) -> dict:
    """Retorna throughput semanal (issues Done por semana ISO).
    
    Retorna:
    - weekly: lista de {week, week_label, total, by_type: {type: count}}
    - summary: {avg, stddev, min, max, total_weeks}
    """
    cursor = conn.cursor()

    cursor.execute('''
        SELECT resolved_at, issuetype_name
        FROM issues
        WHERE status = 'Done' AND resolved_at IS NOT NULL AND resolved_at != ''
          AND project_key = ?
    ''', (project_key,))
    rows = cursor.fetchall()

    if not rows:
        return {"project_key": project_key, "weekly": [], "summary": {}}

    # Agrupa por semana ISO
    by_week: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for resolved_at, issue_type in rows:
        try:
            dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
            iso = dt.isocalendar()
            week_key = f"{iso[0]}-W{iso[1]:02d}"
            by_week[week_key][issue_type or "Outros"] += 1
            by_week[week_key]["_total"] += 1
        except (ValueError, TypeError):
            continue

    # Ordena e limita às últimas N semanas
    sorted_weeks = sorted(by_week.keys())[-weeks:]

    result = []
    totals = []
    for wk in sorted_weeks:
        data = by_week[wk]
        total = data.pop("_total", 0)
        totals.append(total)
        result.append({
            "week": wk,
            "week_label": week_to_date_range(wk),
            "total": total,
            "by_type": dict(data),
        })

    # Summary stats
    avg = sum(totals) / len(totals) if totals else 0
    variance = sum((x - avg) ** 2 for x in totals) / len(totals) if totals else 0
    import math
    stddev = math.sqrt(variance)

    summary = {
        "avg": round(avg, 1),
        "stddev": round(stddev, 1),
        "min": min(totals) if totals else 0,
        "max": max(totals) if totals else 0,
        "total_weeks": len(totals),
    }

    return {"project_key": project_key, "weekly": result, "summary": summary}
