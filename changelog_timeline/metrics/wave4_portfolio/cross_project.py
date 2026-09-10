"""Wave 4.3 — Cross-project throughput consolidado.
Throughput de todos os projetos em uma visão única.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime

from ..timeutils import week_to_date_range


def get_cross_project_throughput(conn: sqlite3.Connection, weeks: int = 26) -> dict:
    """Retorna throughput semanal de todos os projetos consolidados.
    
    Permite comparar ritmo de entrega entre projetos ao longo do tempo.
    """
    cursor = conn.cursor()

    cursor.execute('''
        SELECT project_key, resolved_at
        FROM issues
        WHERE status = 'Done' AND resolved_at IS NOT NULL AND resolved_at != ''
    ''')
    rows = cursor.fetchall()

    if not rows:
        return {"weekly": [], "projects": []}

    # Agrupa por semana ISO e projeto
    by_week_project: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    all_projects = set()

    for project_key, resolved_at in rows:
        try:
            dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
            iso = dt.isocalendar()
            wk = f"{iso[0]}-W{iso[1]:02d}"
            by_week_project[wk][project_key] += 1
            all_projects.add(project_key)
        except (ValueError, TypeError):
            continue

    # Ordena e limita
    sorted_weeks = sorted(by_week_project.keys())[-weeks:]
    projects = sorted(all_projects)

    weekly = []
    for wk in sorted_weeks:
        entry = {
            "week": wk,
            "week_label": week_to_date_range(wk),
            "total": sum(by_week_project[wk].values()),
            "by_project": {p: by_week_project[wk].get(p, 0) for p in projects},
        }
        weekly.append(entry)

    return {"weekly": weekly, "projects": projects}
