"""Wave 3.2 — Distribuição de carga (workload).
Issues Done por pessoa — identifica concentração de conhecimento (bus factor).
NÃO é ranking individual. É para risco organizacional.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta


def get_workload_distribution(conn: sqlite3.Connection, project_key: str, weeks: int = 12) -> dict:
    """Retorna distribuição de entregas por pessoa nas últimas N semanas.
    
    Identifica concentração (bus factor) e desequilíbrio.
    """
    cursor = conn.cursor()

    # Calcula data de corte
    cutoff = (datetime.now() - timedelta(weeks=weeks)).isoformat()

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

    if not rows:
        return {"project_key": project_key, "people": [], "summary": {}, "weeks": weeks}

    total_done = sum(row[1] for row in rows)
    people = []
    cumulative_pct = 0.0

    for row in rows:
        name, count = row[0], row[1]
        pct = (count / total_done * 100) if total_done > 0 else 0
        cumulative_pct += pct
        people.append({
            "name": name,
            "done_count": count,
            "percentage": round(pct, 1),
            "cumulative_pct": round(cumulative_pct, 1),
        })

    # Gini coefficient (mede desigualdade: 0 = perfeito, 1 = toda carga em 1 pessoa)
    n = len(people)
    counts = sorted([p["done_count"] for p in people])
    if n > 1 and total_done > 0:
        numerator = sum((2 * (i + 1) - n - 1) * counts[i] for i in range(n))
        gini = numerator / (n * total_done)
    else:
        gini = 0.0

    # Bus factor: quantas pessoas fazem 50%+ das entregas
    bus_factor = 0
    accum = 0
    for p in people:
        accum += p["done_count"]
        bus_factor += 1
        if accum >= total_done * 0.5:
            break

    summary = {
        "total_done": total_done,
        "total_people": n,
        "gini": round(gini, 3),
        "bus_factor": bus_factor,
        "top_contributor_pct": people[0]["percentage"] if people else 0,
    }

    return {
        "project_key": project_key,
        "people": people,
        "summary": summary,
        "weeks": weeks,
    }
