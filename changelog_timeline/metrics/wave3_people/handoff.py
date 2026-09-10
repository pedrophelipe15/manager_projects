"""Wave 3.3 — Handoff time.
Tempo entre mudanças de assignee — mede atraso em transferências.
Handoffs frequentes/longos são gargalo invisível.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime


def get_handoff_time(conn: sqlite3.Connection, project_key: str) -> dict:
    """Retorna análise de handoffs (mudanças de assignee) no projeto.
    
    Mede tempo médio entre handoffs e identifica pares com mais transferências.
    """
    cursor = conn.cursor()

    # Busca todas as mudanças de assignee do projeto
    cursor.execute('''
        SELECT pc.issue_key, pc.event_date, pc.from_value, pc.to_value
        FROM parsed_changelogs pc
        INNER JOIN issues i ON pc.issue_key = i.key
        WHERE i.project_key = ? AND pc.field = 'assignee'
          AND pc.from_value IS NOT NULL AND pc.from_value != ''
          AND pc.to_value IS NOT NULL AND pc.to_value != ''
        ORDER BY pc.issue_key, pc.event_date ASC
    ''', (project_key,))
    rows = cursor.fetchall()

    if not rows:
        return {"project_key": project_key, "handoffs": [], "pairs": [], "summary": {}}

    # Agrupa por issue para calcular tempo entre handoffs
    by_issue: dict[str, list[tuple]] = defaultdict(list)
    for issue_key, event_date, from_val, to_val in rows:
        by_issue[issue_key].append((event_date, from_val, to_val))

    # Analisa handoffs
    all_handoffs: list[dict] = []
    pair_counts: dict[tuple, int] = defaultdict(int)
    handoff_durations: list[float] = []

    for issue_key, events in by_issue.items():
        for i, (event_date, from_val, to_val) in enumerate(events):
            pair_counts[(from_val, to_val)] += 1
            all_handoffs.append({
                "issue_key": issue_key,
                "from": from_val,
                "to": to_val,
                "date": event_date,
            })

            # Calcula tempo até próximo evento nesta issue (se houver)
            if i + 1 < len(events):
                try:
                    dt_current = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
                    dt_next = datetime.fromisoformat(events[i + 1][0].replace("Z", "+00:00"))
                    duration_hours = (dt_next - dt_current).total_seconds() / 3600
                    if duration_hours > 0:
                        handoff_durations.append(duration_hours)
                except (ValueError, TypeError):
                    pass

    # Top pares de handoff
    pairs = []
    for (from_val, to_val), count in sorted(pair_counts.items(), key=lambda x: -x[1])[:10]:
        pairs.append({"from": from_val, "to": to_val, "count": count})

    # Issues com mais handoffs
    issues_by_handoff_count = sorted(
        [(k, len(v)) for k, v in by_issue.items()],
        key=lambda x: -x[1]
    )[:10]

    top_issues = [{"key": k, "handoff_count": c} for k, c in issues_by_handoff_count]

    # Summary
    avg_duration_hours = sum(handoff_durations) / len(handoff_durations) if handoff_durations else 0
    total_handoffs = len(all_handoffs)
    issues_with_handoffs = len(by_issue)

    summary = {
        "total_handoffs": total_handoffs,
        "issues_with_handoffs": issues_with_handoffs,
        "avg_time_between_handoffs_hours": round(avg_duration_hours, 1),
        "avg_handoffs_per_issue": round(total_handoffs / issues_with_handoffs, 1) if issues_with_handoffs > 0 else 0,
    }

    return {
        "project_key": project_key,
        "pairs": pairs,
        "top_issues": top_issues,
        "summary": summary,
    }
