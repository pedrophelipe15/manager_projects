"""Wave 1.5 — Aging WIP Report.
Identifica issues ativas (In Progress/Blocked) com cycle time acima do P85 histórico.
Não persiste — calcula on-the-fly (volume baixo: só issues ativas).
"""

from __future__ import annotations

import sqlite3
import math
from datetime import datetime


def setup_table(conn: sqlite3.Connection):
    """Aging WIP não precisa de tabela própria — calcula em tempo real."""
    pass


def calculate_aging_wip(conn: sqlite3.Connection, only_keys: list[str] | None = None) -> int:
    """Placeholder para consistência com o contrato de run_wave1.
    
    Aging WIP é calculado on-the-fly no endpoint (não na ingestão),
    pois depende de 'agora' e do P85 calculado por percentiles.py.
    
    Retorna 0 (nada persistido).
    """
    return 0


def get_aging_wip(conn: sqlite3.Connection, project_key: str) -> dict:
    """Calcula Aging WIP em tempo real para um projeto.
    
    Retorna issues ativas com cycle_time > P85 histórico do projeto.
    """
    cursor = conn.cursor()

    # Busca P85 do cycle time deste projeto
    cursor.execute("""
        SELECT p85_ms FROM metrics_percentiles
        WHERE project_key = ? AND metric_type = 'cycle_time'
    """, (project_key,))
    row = cursor.fetchone()
    p85_ms = row[0] if row else 0

    if p85_ms == 0:
        return {"p85_ms": 0, "issues": [], "total": 0}

    # Busca issues ativas com cycle time
    cursor.execute("""
        SELECT i.key, i.summary, i.status, i.assignee_name, m.cycle_time_ms,
               i.due_date, i.updated_at
        FROM issues i
        LEFT JOIN metrics m ON i.key = m.issue_key
        WHERE i.project_key = ? AND i.status IN ('In Progress', 'Blocked', 'Test', 'Waiting for Delivery')
          AND m.cycle_time_ms > ?
        ORDER BY m.cycle_time_ms DESC
    """, (project_key, p85_ms))
    
    issues = []
    for row in cursor.fetchall():
        issues.append({
            "key": row[0],
            "summary": row[1],
            "status": row[2],
            "assignee": row[3],
            "cycle_time_ms": row[4],
            "over_p85_ms": row[4] - p85_ms,
            "due_date": row[5],
            "updated_at": row[6],
        })

    return {
        "p85_ms": p85_ms,
        "issues": issues,
        "total": len(issues),
    }
