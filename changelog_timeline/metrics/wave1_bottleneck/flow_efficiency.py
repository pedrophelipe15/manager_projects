"""Wave 1.3 — Flow Efficiency.
Flow Efficiency = tempo trabalhando (In Progress) / tempo total (Lead Time).
Persiste por issue na tabela metrics_flow.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ..changelog_cache import StatusTransitions


def setup_table(conn: sqlite3.Connection):
    """Cria tabela metrics_flow se não existir."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS metrics_flow (
            issue_key TEXT PRIMARY KEY,
            project_key TEXT NOT NULL,
            work_time_ms INTEGER DEFAULT 0,
            wait_time_ms INTEGER DEFAULT 0,
            lead_time_ms INTEGER DEFAULT 0,
            flow_efficiency REAL DEFAULT 0.0
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_mf_project ON metrics_flow(project_key)')
    conn.commit()


def calculate_flow_efficiency(
    conn: sqlite3.Connection,
    only_keys: list[str] | None = None,
    status_cache: dict[str, StatusTransitions] | None = None,
) -> int:
    """Calcula flow efficiency por issue (Done com lead time > 0).
    
    work_time = tempo em "In Progress"
    wait_time = lead_time - work_time
    flow_efficiency = work_time / lead_time
    
    Se status_cache for fornecido, usa os dados pré-carregados.
    """
    setup_table(conn)
    cursor = conn.cursor()

    # Busca issues Done com lead time
    if only_keys:
        placeholders = ",".join(["?" for _ in only_keys])
        cursor.execute(f"""
            SELECT m.issue_key, m.project_key, m.lead_time_ms
            FROM metrics m
            INNER JOIN issues i ON m.issue_key = i.key
            WHERE i.status = 'Done' AND m.lead_time_ms > 0
              AND m.issue_key IN ({placeholders})
        """, only_keys)
    else:
        cursor.execute("""
            SELECT m.issue_key, m.project_key, m.lead_time_ms
            FROM metrics m
            INNER JOIN issues i ON m.issue_key = i.key
            WHERE i.status = 'Done' AND m.lead_time_ms > 0
        """)
    issues = cursor.fetchall()

    count = 0
    for issue_key, project_key, lead_time_ms in issues:
        # Calcula tempo em "In Progress" (apenas — sem Blocked)
        if status_cache is not None:
            transitions = status_cache.get(issue_key, [])
        else:
            cursor.execute('''
                SELECT event_date, from_value, to_value
                FROM parsed_changelogs
                WHERE issue_key = ? AND field = 'status'
                ORDER BY event_date ASC
            ''', (issue_key,))
            transitions = cursor.fetchall()

        work_time_ms = 0
        in_progress_start = None

        for event_date_str, from_value, to_value in transitions:
            if not event_date_str:
                continue
            try:
                event_dt = datetime.fromisoformat(event_date_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            if to_value == "In Progress":
                in_progress_start = event_dt

            if from_value == "In Progress" and in_progress_start:
                interval_ms = int((event_dt - in_progress_start).total_seconds() * 1000)
                work_time_ms += interval_ms
                in_progress_start = None

        wait_time_ms = max(0, lead_time_ms - work_time_ms)
        efficiency = (work_time_ms / lead_time_ms * 100) if lead_time_ms > 0 else 0.0

        cursor.execute('''
            INSERT OR REPLACE INTO metrics_flow 
            (issue_key, project_key, work_time_ms, wait_time_ms, lead_time_ms, flow_efficiency)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (issue_key, project_key, work_time_ms, wait_time_ms, lead_time_ms, round(efficiency, 2)))
        count += 1

    conn.commit()
    return count
