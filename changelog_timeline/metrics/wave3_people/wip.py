"""Wave 3.1 — WIP por pessoa.
Quantas issues cada pessoa tem simultaneamente em estados ativos.
Multitasking excessivo (>3 items) é fator real de lentidão.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from ..constants import WIP_ACTIVE_STATES as ACTIVE_STATES


def get_wip_per_person(conn: sqlite3.Connection, project_key: str) -> dict:
    """Retorna WIP (Work In Progress) por pessoa.
    
    Conta issues em estados ativos atribuídas a cada pessoa.
    """
    cursor = conn.cursor()

    status_placeholders = ",".join(f"'{s}'" for s in ACTIVE_STATES)
    cursor.execute(f'''
        SELECT assignee_name, key, summary, status, updated_at
        FROM issues
        WHERE project_key = ? AND status IN ({status_placeholders})
          AND assignee_name IS NOT NULL AND assignee_name != ''
        ORDER BY assignee_name, updated_at DESC
    ''', (project_key,))
    rows = cursor.fetchall()

    by_person: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_person[row[0]].append({
            "key": row[1],
            "summary": row[2],
            "status": row[3],
            "updated_at": row[4],
        })

    # Busca issues Blocked por pessoa (informativo, não afeta cálculo de WIP)
    cursor.execute('''
        SELECT assignee_name, key, summary, status, updated_at
        FROM issues
        WHERE project_key = ? AND status = 'Blocked'
          AND assignee_name IS NOT NULL AND assignee_name != ''
        ORDER BY assignee_name, updated_at DESC
    ''', (project_key,))
    blocked_rows = cursor.fetchall()

    blocked_by_person: dict[str, list[dict]] = defaultdict(list)
    for row in blocked_rows:
        blocked_by_person[row[0]].append({
            "key": row[1],
            "summary": row[2],
            "status": row[3],
            "updated_at": row[4],
        })

    people = []
    # Coleta todas as pessoas (WIP + Blocked)
    all_persons = set(by_person.keys()) | set(blocked_by_person.keys())
    for person in sorted(all_persons, key=lambda p: -len(by_person.get(p, []))):
        issues = by_person.get(person, [])
        blocked = blocked_by_person.get(person, [])
        people.append({
            "name": person,
            "wip_count": len(issues),
            "issues": issues,
            "blocked_count": len(blocked),
            "blocked_issues": blocked,
            "risk": "high" if len(issues) >= 6 else ("medium" if len(issues) >= 4 else "low"),
        })

    # Summary stats
    wip_counts = [p["wip_count"] for p in people]
    avg_wip = sum(wip_counts) / len(wip_counts) if wip_counts else 0
    overloaded = sum(1 for p in people if p["wip_count"] >= 4)

    return {
        "project_key": project_key,
        "people": people,
        "summary": {
            "total_people": len(people),
            "avg_wip": round(avg_wip, 1),
            "overloaded": overloaded,
            "max_wip": max(wip_counts) if wip_counts else 0,
        },
    }
