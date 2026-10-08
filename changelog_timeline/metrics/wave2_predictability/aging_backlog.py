"""Wave 2.3 — Aging Backlog.
Issues abertas há muito tempo sem atividade — candidatas a cancelamento.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime


def get_aging_backlog(conn: sqlite3.Connection, project_key: str, min_days: int = 30) -> dict:
    """Retorna issues que não estão Done e não foram atualizadas há mais de N dias.
    
    Identifica itens "esquecidos" no backlog que provavelmente deveriam ser cancelados.
    """
    cursor = conn.cursor()

    now = datetime.now()

    cursor.execute('''
        SELECT key, summary, status, assignee_name, updated_at, created_at, issuetype_name
        FROM issues
        WHERE project_key = ? AND status != 'Done'
          AND updated_at IS NOT NULL AND updated_at != ''
        ORDER BY updated_at ASC
    ''', (project_key,))
    rows = cursor.fetchall()

    issues = []
    for row in rows:
        key, summary, status, assignee, updated_at, created_at, issue_type = row
        try:
            updated_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).replace(tzinfo=None)
            days_stale = (now - updated_dt).days
        except (ValueError, TypeError):
            continue

        if days_stale >= min_days:
            created_dt = None
            try:
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")).replace(tzinfo=None)
            except (ValueError, TypeError):
                pass

            age_days = (now - created_dt).days if created_dt else None

            issues.append({
                "key": key,
                "summary": summary,
                "status": status,
                "assignee": assignee,
                "issue_type": issue_type,
                "days_stale": days_stale,
                "age_days": age_days,
                "updated_at": updated_at,
                "created_at": created_at,
            })

    # Agrupa por faixa de inatividade
    brackets = {"30-60d": 0, "60-90d": 0, "90-180d": 0, "180d+": 0}
    for issue in issues:
        d = issue["days_stale"]
        if d >= 180:
            brackets["180d+"] += 1
        elif d >= 90:
            brackets["90-180d"] += 1
        elif d >= 60:
            brackets["60-90d"] += 1
        else:
            brackets["30-60d"] += 1

    return {
        "project_key": project_key,
        "min_days": min_days,
        "total": len(issues),
        "brackets": brackets,
        "issues": issues[:100],  # Limita a 100 para não sobrecarregar o frontend
    }
