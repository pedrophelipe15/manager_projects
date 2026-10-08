"""Wave 3.4 — Taxa de reabertura e retrabalho.
Issues que voltaram de estado avançado para estado anterior.
Reflete qualidade: retrabalho = tempo desperdiçado.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from ..constants import is_backward_transition


def get_rework_rate(conn: sqlite3.Connection, project_key: str) -> dict:
    """Retorna análise de retrabalho — issues com transições "para trás".
    
    Uma transição é "para trás" quando o status de destino é anterior ao de origem
    na ordem lógica do fluxo (ex: Done→In Progress, Test→In Progress).
    """
    cursor = conn.cursor()

    # Busca todas as transições de status do projeto
    cursor.execute('''
        SELECT pc.issue_key, pc.event_date, pc.from_value, pc.to_value
        FROM parsed_changelogs pc
        INNER JOIN issues i ON pc.issue_key = i.key
        WHERE i.project_key = ? AND pc.field = 'status'
        ORDER BY pc.issue_key, pc.event_date ASC
    ''', (project_key,))
    rows = cursor.fetchall()

    if not rows:
        return {"project_key": project_key, "issues": [], "summary": {}}

    # Identifica retrabalho (transições para trás)
    by_issue: dict[str, list[dict]] = defaultdict(list)
    total_transitions = 0
    total_rework_transitions = 0
    rework_issues: dict[str, list[dict]] = defaultdict(list)

    for issue_key, event_date, from_val, to_val in rows:
        total_transitions += 1

        if is_backward_transition(from_val, to_val):
            # Transição para trás = retrabalho
            total_rework_transitions += 1
            rework_issues[issue_key].append({
                "date": event_date,
                "from": from_val,
                "to": to_val,
            })

    # Issues Done no projeto (para calcular %)
    cursor.execute('''
        SELECT COUNT(*) FROM issues WHERE project_key = ? AND status = 'Done'
    ''', (project_key,))
    total_done = cursor.fetchone()[0]

    cursor.execute('''
        SELECT COUNT(*) FROM issues WHERE project_key = ?
    ''', (project_key,))
    total_issues = cursor.fetchone()[0]

    # Monta lista de issues com retrabalho
    issues_with_rework = []
    for issue_key, reworks in sorted(rework_issues.items(), key=lambda x: -len(x[1])):
        # Busca info da issue
        cursor.execute('SELECT summary, status, assignee_name FROM issues WHERE key = ?', (issue_key,))
        row = cursor.fetchone()
        if row:
            issues_with_rework.append({
                "key": issue_key,
                "summary": row[0],
                "status": row[1],
                "assignee": row[2],
                "rework_count": len(reworks),
                "reworks": reworks[:5],  # Limita detalhes
            })

    # Tipos de retrabalho mais comuns
    rework_types: dict[str, int] = defaultdict(int)
    for issue_key, reworks in rework_issues.items():
        for r in reworks:
            rework_types[f"{r['from']} → {r['to']}"] += 1

    top_rework_types = sorted(rework_types.items(), key=lambda x: -x[1])[:5]

    # Summary
    rework_rate = (len(rework_issues) / total_issues * 100) if total_issues > 0 else 0

    summary = {
        "total_issues": total_issues,
        "issues_with_rework": len(rework_issues),
        "rework_rate_pct": round(rework_rate, 1),
        "total_rework_transitions": total_rework_transitions,
        "total_transitions": total_transitions,
        "rework_transition_pct": round(total_rework_transitions / total_transitions * 100, 1) if total_transitions > 0 else 0,
    }

    return {
        "project_key": project_key,
        "issues": issues_with_rework[:30],  # Top 30
        "top_rework_types": [{"type": t, "count": c} for t, c in top_rework_types],
        "summary": summary,
    }
